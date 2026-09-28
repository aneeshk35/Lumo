#!/usr/bin/env python3
"""Stress tests for the game server: answer keys, grading, matchmaking, and
whole games played concurrently. Talks to a running server over HTTP.

    python3 tests/fake_supabase.py &
    SUPABASE_URL=http://127.0.0.1:54321 SUPABASE_SERVICE_KEY=test-secret \\
        LUMO_BOT_PACE=0.05 LUMO_BOT_WAIT=6 python3 server.py &
    python3 tests/stress.py [rounds]

Each round repeats the server-side checks with fresh random games.
"""

import json
import os
import random
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from fractions import Fraction

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import server  # noqa: E402  (the bank and grader, to know the right answers)

BASE = os.environ.get("LUMO_URL", "http://localhost:3000")
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail and not ok else ""))
    return ok


def post(action, body, timeout=30):
    req = urllib.request.Request(f"{BASE}/api/{action}", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as err:
        try:
            return json.loads(err.read())
        except ValueError:
            return {"error": f"HTTP {err.code}"}


class Listener(threading.Thread):
    """Reads one player's event stream into a list."""

    def __init__(self, code, pid):
        super().__init__(daemon=True)
        self.url = f"{BASE}/api/events?code={code}&player={pid}"
        self.events = []
        self.lock = threading.Lock()
        self.stopped = False

    def run(self):
        try:
            with urllib.request.urlopen(self.url, timeout=300) as s:
                ev = None
                for raw in s:
                    if self.stopped:
                        return
                    line = raw.decode().strip()
                    if line.startswith("event:"):
                        ev = line[6:].strip()
                    elif line.startswith("data:"):
                        with self.lock:
                            self.events.append((ev, json.loads(line[5:])))
                        if ev == "game_over":
                            return
        except Exception:
            pass

    def wait_for(self, name, after=0, timeout=60, pred=None):
        end = time.time() + timeout
        while time.time() < end:
            with self.lock:
                for i, (ev, data) in enumerate(self.events[after:], after):
                    if ev == name and (pred is None or pred(data)):
                        return i, data
            time.sleep(0.05)
        return None, None


def right_answer(qid):
    q = server.find_question(qid)
    if q.get("type") == "spr":
        return {"response": q["answers"][0]}
    return {"choice": q["answer"]}


def wrong_answer(qid):
    q = server.find_question(qid)
    if q.get("type") == "spr":
        return {"response": "-9999"}
    return {"choice": (q["answer"] + 1) % 4}


# ---------------------------------------------------------------- 1. the bank
def check_bank():
    print("\n1. Every answer key in the bank")
    bad_mcq, bad_spr, spr_forms = [], [], 0
    for q in server.QUESTIONS:
        if q.get("type") == "spr":
            key = q["answers"][0]
            val = server.parse_number(key)
            forms = {key, f"  {key} ", key.replace("-", "−")}
            if val is not None:
                if val.denominator != 1:
                    forms.add(f"{val.numerator}/{val.denominator}")
                    dec = float(val)
                    if (val.denominator & (val.denominator - 1) == 0) or val.denominator in (5, 10, 20, 25, 50):
                        forms.add(str(dec).rstrip("0").rstrip("."))
                    else:
                        # a long decimal counts when rounded to at least 3 places and it fits the box
                        form = f"{dec:.3f}"
                        if len(form) <= 7:
                            forms.add(form)
                else:
                    forms.add(f"{val.numerator * 2}/2" if abs(val.numerator) < 999 else key)
            ok = all(server.grade_response(q, f) for f in forms if len(f.strip()) <= 8)
            spr_forms += len(forms)
            wrong = str(val + 1) if val is not None else "0"
            if not ok or val is None or server.grade_response(q, wrong.replace("/1", "")):
                bad_spr.append(q["id"])
        else:
            ch = q.get("choices") or []
            if len(ch) != 4 or len(set(ch)) != 4 or not 0 <= q.get("answer", -1) <= 3:
                bad_mcq.append(q["id"])
    n_spr = sum(1 for q in server.QUESTIONS if q.get("type") == "spr")
    check(f"all {len(server.QUESTIONS) - n_spr} multiple-choice questions have 4 distinct choices and a valid key",
          not bad_mcq, str(bad_mcq[:10]))
    check(f"all {n_spr} typed-answer keys grade correct in every equivalent form ({spr_forms} forms), and key+1 grades wrong",
          not bad_spr, str(bad_spr[:10]))
    q = {"answers": ["2/3"]}
    check("2/3 accepts .666, .667, 0.666 and 2/3; rejects .66 and .67",
          all(server.grade_response(q, f) for f in (".666", ".667", "0.666", "2/3", "4/6"))
          and not any(server.grade_response(q, f) for f in (".66", ".67", "0.6")))
    q = {"answers": ["-7/2"]}
    check("−7/2 accepts -3.5, −3.5 and -7/2; rejects 3.5",
          all(server.grade_response(q, f) for f in ("-3.5", "−3.5", "-7/2"))
          and not server.grade_response(q, "3.5"))
    check("junk input never crashes the grader",
          all(server.grade_response({"answers": ["5"]}, j) is False
              for j in ("", "abc", "1/0", "--5", "5/", "/5", "1e3", "99999999", ".", "-")))


# --------------------------------------------------------- 2. solo answering
def solo_session(settings, correct, log):
    res = post("create", {"name": "Stress", "settings": dict(settings, practice=True)})
    if not res.get("ok"):
        log.append(("create failed", res))
        return
    code, pid = res["code"], res["playerId"]
    lis = Listener(code, pid)
    lis.start()
    time.sleep(0.3)
    post("start", {"code": code, "player": pid})
    seen = 0
    while True:
        i, qd = lis.wait_for("question", seen, timeout=20)
        if qd is None:
            log.append(("no question", code))
            return
        seen = i + 1
        ans = right_answer(qd["id"]) if correct else wrong_answer(qd["id"])
        r = post("answer", dict(ans, code=code, player=pid))
        j, rev = lis.wait_for("reveal", seen, timeout=20)
        if rev is None or not r.get("ok"):
            log.append(("no reveal / answer refused", qd["id"], r))
            return
        seen = j + 1
        you = rev.get("you") or {}
        kind = qd.get("type", "mcq")
        log.append((kind, qd["id"], you.get("correct") == correct, you.get("points", 0) > 0 if correct else you.get("points") == 0))
        if rev.get("isLast"):
            lis.stopped = True
            return
        post("next", {"code": code, "player": pid})


def check_solo(rng, sessions=24):
    print(f"\n2. Answering through the server ({sessions} sessions, right and wrong, typed and multiple choice)")
    log = []
    threads = []
    for n in range(sessions):
        section = rng.choice(["math", "math", "rw", "mixed"])
        diff = rng.choice(["easy", "medium", "hard"])
        t = threading.Thread(target=solo_session,
                             args=({"section": section, "difficulties": [diff], "count": 10}, n % 2 == 0, log))
        t.start()
        threads.append(t)
        time.sleep(0.05)
    for t in threads:
        t.join(120)
    answers = [row for row in log if row[0] in ("mcq", "spr")]
    problems = [row for row in log if row[0] not in ("mcq", "spr") or not (row[2] and row[3])]
    kinds = Counter(row[0] for row in answers)
    check(f"{len(answers)} answers graded exactly as expected ({kinds['spr']} typed, {kinds['mcq']} multiple choice)",
          answers and not problems, str(problems[:5]))
    check("every session ran all 10 questions", len(answers) == sessions * 10, f"{len(answers)} of {sessions * 10}")


# ------------------------------------------------------------ 3. matchmaking
def queue_player(name, mode, section, difficulty, elo, out):
    r = post("queue", {"name": name, "mode": mode, "section": section, "difficulty": difficulty, "elo": elo})
    if not r.get("matched"):
        ticket = r.get("ticket")
        for _ in range(40):
            time.sleep(0.5)
            r = post("queue_status", {"ticket": ticket})
            if r.get("matched") or r.get("expired"):
                break
    out.append((name, mode, section, difficulty, r))


def check_matchmaking(rng, per_ladder=4):
    print(f"\n3. Crowded matchmaking ({per_ladder} players on each of 9 ladders at once, plus 2v2)")
    out = []
    threads = []
    ladders = [(s, d) for s in ("math", "rw", "mixed") for d in ("easy", "medium", "hard")]
    n = 0
    for s, d in ladders:
        for _ in range(per_ladder):
            n += 1
            t = threading.Thread(target=queue_player, args=(f"p{n}", "1v1", s, d, rng.randint(900, 1600), out))
            threads.append(t)
    for _ in range(8):
        n += 1
        threads.append(threading.Thread(target=queue_player, args=(f"t{n}", "2v2", "mixed", "medium", 1200, out)))
    rng.shuffle(threads)
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)

    matched = [row for row in out if row[4].get("matched")]
    check(f"all {len(threads)} players got matched", len(matched) == len(threads),
          f"{len(matched)} of {len(threads)}; unmatched: {[r[0] for r in out if not r[4].get('matched')][:6]}")
    by_code = {}
    for name, mode, s, d, r in matched:
        by_code.setdefault(r["code"], []).append((name, mode, s, d, r["playerId"]))
    ok_ladder = all(len({(m, s, d) for _, m, s, d, _ in group}) == 1 for group in by_code.values())
    check("everyone in a game picked the same mode, subject, and difficulty", ok_ladder)
    ids = [pid for group in by_code.values() for *_, pid in group]
    check("nobody was seated twice", len(ids) == len(set(ids)))

    sizes_ok, teams_ok = True, True
    for code, group in by_code.items():
        lis = Listener(code, group[0][4])
        lis.start()
        _, lobby = lis.wait_for("lobby_update", 0, timeout=10)
        lis.stopped = True
        if not lobby:
            sizes_ok = False
            continue
        players = lobby["players"]
        want = 4 if group[0][1] == "2v2" else 2
        humans = [p for p in players if not p["bot"]]
        if len(players) != want or len(humans) != len(group):
            sizes_ok = False
        if want == 4:
            teams = Counter(p["team"] for p in players)
            roles = Counter((p["team"], p["role"]) for p in players)
            if teams != Counter({"A": 2, "B": 2}) or len(roles) != 4:
                teams_ok = False
    check("every game has the right number of seats (2 or 4), people first", sizes_ok)
    check("2v2 games split into two teams, each with a Reading and a Math specialist", teams_ok)
    humans_2v2 = sum(1 for row in matched if row[1] == "2v2")
    check("8 players queueing 2v2 together make two all-human games",
          sum(1 for g in by_code.values() if g[0][1] == "2v2" and len(g) == 4) == 2, f"{humans_2v2} matched")


# --------------------------------------------------------------- 4. duels
def play_duel(section, difficulty, skill_a, skill_b, report):
    """Two simulated people queue, ready up, and answer every question."""
    rs = {}

    def join(tag, elo):
        r = post("queue", {"name": tag, "mode": "1v1", "section": section, "difficulty": difficulty, "elo": elo})
        ticket = r.get("ticket")
        for _ in range(100):
            if r.get("matched"):
                break
            time.sleep(0.3)
            r = post("queue_status", {"ticket": ticket})
        rs[tag] = r

    tag_a, tag_b = f"A{random.randint(1000, 9999)}", f"B{random.randint(1000, 9999)}"
    ta = threading.Thread(target=join, args=(tag_a, 1200))
    tb = threading.Thread(target=join, args=(tag_b, 1200))
    ta.start(); time.sleep(0.1); tb.start(); ta.join(30); tb.join(30)
    if tag_a not in rs or tag_b not in rs or rs[tag_a]["code"] != rs[tag_b]["code"]:
        report.append(("pairing failed", section, difficulty))
        return
    code = rs[tag_a]["code"]
    players = {tag_a: (rs[tag_a]["playerId"], skill_a), tag_b: (rs[tag_b]["playerId"], skill_b)}
    listeners = {t: Listener(code, pid) for t, (pid, _) in players.items()}
    for lis in listeners.values():
        lis.start()
    time.sleep(0.4)
    for t, (pid, _) in players.items():
        post("ready", {"code": code, "player": pid})
    rng = random.Random()
    expect_correct = {tag_a: 0, tag_b: 0}
    pos = {t: 0 for t in players}
    questions_seen = []
    for qn in range(10):
        qs = {}
        for t, lis in listeners.items():
            i, qd = lis.wait_for("question", pos[t], timeout=40)
            if qd is None:
                report.append(("question never arrived", code, qn))
                return
            pos[t] = i + 1
            qs[t] = qd
        if qs[tag_a]["id"] != qs[tag_b]["id"]:
            report.append(("players got different questions", code, qn))
        questions_seen.append(qs[tag_a]["id"])
        if qs[tag_a]["difficulty"] != difficulty or (section != "mixed" and qs[tag_a]["section"] != section):
            report.append(("wrong ladder question", qs[tag_a]["id"], section, difficulty))
        want_ms = {"easy": 90000, "medium": 120000, "hard": 180000}[difficulty]
        if qs[tag_a].get("durationMs") != want_ms:
            report.append(("wrong clock length", difficulty, qs[tag_a].get("durationMs")))
        for t, (pid, skill) in players.items():
            good = rng.random() < skill
            ans = right_answer(qs[t]["id"]) if good else wrong_answer(qs[t]["id"])
            time.sleep(rng.uniform(0.05, 0.4))
            r = post("answer", dict(ans, code=code, player=pid))
            if r.get("ok"):
                expect_correct[t] += good
        for t, lis in listeners.items():
            i, rev = lis.wait_for("reveal", pos[t], timeout=40)
            if rev is None:
                report.append(("reveal never arrived", code, qn))
                return
            pos[t] = i + 1
    over = {}
    for t, lis in listeners.items():
        _, over[t] = lis.wait_for("game_over", pos[t], timeout=40)
    if not all(over.values()):
        report.append(("game_over never arrived", code))
        return
    board = {p["name"]: p for p in over[tag_a]["leaderboard"]}
    ratings = over[tag_a].get("ratings") or {}
    for t in players:
        if board[t]["correct"] != expect_correct[t]:
            report.append(("score doesn't match answers", t, board[t]["correct"], expect_correct[t]))
        if (board[t]["score"] > 0) != (expect_correct[t] > 0):
            report.append(("points don't match", t))
    a, b = board[tag_a]["score"], board[tag_b]["score"]
    if a != b:
        win, lose = (tag_a, tag_b) if a > b else (tag_b, tag_a)
        if not (ratings.get(win, {}).get("delta", 0) > 0 > ratings.get(lose, {}).get("delta", 0)):
            report.append(("Elo went the wrong way", ratings))
    if len(set(questions_seen)) != 10:
        report.append(("a question repeated inside one duel", code))
    report.append(("ok", code))


def check_duels(rng, games=6):
    print(f"\n4. Whole duels played at the same time ({games} games, 10 questions each)")
    report = []
    threads = []
    ladders = [(s, d) for s in ("math", "rw", "mixed") for d in ("easy", "medium", "hard")]
    for g in range(games):
        s, d = ladders[g % len(ladders)] if g < len(ladders) else rng.choice(ladders)
        t = threading.Thread(target=play_duel, args=(s, d, rng.uniform(0.2, 0.9), rng.uniform(0.2, 0.9), report))
        threads.append(t)
        t.start()
        time.sleep(0.25)
    for t in threads:
        t.join(300)
    done = sum(1 for r in report if r[0] == "ok")
    problems = [r for r in report if r[0] != "ok"]
    check(f"{done} of {games} duels finished with correct scores, questions, and Elo", done == games and not problems,
          str(problems[:4]))


def play_bot_game(mode, section, difficulty, report):
    r = post("queue", {"name": f"Solo{random.randint(100, 999)}", "mode": mode, "section": section,
                       "difficulty": difficulty, "elo": 1200})
    ticket = r.get("ticket")
    for _ in range(80):
        if r.get("matched"):
            break
        time.sleep(0.5)
        r = post("queue_status", {"ticket": ticket})
    if not r.get("matched"):
        report.append(("never matched with bots", mode))
        return
    code, pid = r["code"], r["playerId"]
    lis = Listener(code, pid)
    lis.start()
    _, lobby = lis.wait_for("lobby_update", 0, timeout=10)
    want = 4 if mode == "2v2" else 2
    if not lobby or len(lobby["players"]) != want or sum(p["bot"] for p in lobby["players"]) != want - 1:
        report.append(("bot seats wrong", mode, lobby and len(lobby["players"])))
    post("ready", {"code": code, "player": pid})
    pos = 0
    for qn in range(10):
        i, qd = lis.wait_for("question", pos, timeout=40)
        if qd is None:
            report.append(("bot game stalled", mode, qn))
            return
        pos = i + 1
        post("answer", dict(right_answer(qd["id"]), code=code, player=pid))
        i, rev = lis.wait_for("reveal", pos, timeout=40)
        if rev is None:
            report.append(("bot reveal stalled", mode, qn))
            return
        pos = i + 1
        if not (rev.get("you") or {}).get("correct"):
            report.append(("right answer marked wrong in a bot game", qd["id"]))
    _, over = lis.wait_for("game_over", pos, timeout=40)
    if not over:
        report.append(("bot game never ended", mode))
        return
    report.append(("ok", mode))


def check_bot_games(games=4):
    print(f"\n5. Games against bots at the same time ({games} games, 1v1 and 2v2)")
    report = []
    # A different ladder for each, so two lone players can't match each other.
    ladders = [("math", "easy"), ("rw", "hard"), ("math", "hard"), ("rw", "easy"), ("mixed", "hard"), ("mixed", "easy")]
    threads = [threading.Thread(target=play_bot_game, args=("2v2" if g % 2 else "1v1", *ladders[g % len(ladders)], report))
               for g in range(games)]
    for i, t in enumerate(threads):
        t.start()
        time.sleep(0.2)
    for t in threads:
        t.join(300)
    done = sum(1 for r in report if r[0] == "ok")
    check(f"{done} of {games} bot games ran to the end with every right answer marked right",
          done == games, str([r for r in report if r[0] != "ok"][:4]))


def check_ghosts():
    print("\n6. Ghost players: closed tabs never block a real player")
    # A player queues and closes the tab (never polls again).
    post("queue", {"name": "Ghost", "mode": "1v1", "section": "rw", "difficulty": "medium", "elo": 1200})
    time.sleep(9)
    r = post("queue", {"name": "Real", "mode": "1v1", "section": "rw", "difficulty": "medium", "elo": 1200})
    check("a real player isn't matched with a closed tab's old queue entry", not r.get("matched"), str(r)[:120])
    if r.get("ticket"):
        post("queue_cancel", {"ticket": r["ticket"]})

    # Two players match, but one never shows up: a bot takes that seat.
    out = []
    ta = threading.Thread(target=queue_player, args=("Shows", "1v1", "math", "medium", 1200, out))
    tb = threading.Thread(target=queue_player, args=("NoShow", "1v1", "math", "medium", 1200, out))
    ta.start(); time.sleep(0.2); tb.start(); ta.join(30); tb.join(30)
    me = next((row[4] for row in out if row[0] == "Shows" and row[4].get("matched")), None)
    if not check("the two players were matched", me is not None):
        return
    lis = Listener(me["code"], me["playerId"])
    lis.start()
    time.sleep(0.5)
    post("ready", {"code": me["code"], "player": me["playerId"]})
    _, q = lis.wait_for("question", 0, timeout=30)
    _, lobby = lis.wait_for("lobby_update", 0, timeout=1, pred=lambda d: any(p["bot"] for p in d["players"]))
    check("when a matched player never shows up, a bot takes the seat and the game starts",
          q is not None and lobby is not None)
    lis.stopped = True

    # A player leaves the lobby before readying: the one who stayed still gets a game.
    out = []
    ta = threading.Thread(target=queue_player, args=("Stays", "1v1", "rw", "hard", 1200, out))
    tb = threading.Thread(target=queue_player, args=("Leaves", "1v1", "rw", "hard", 1200, out))
    ta.start(); time.sleep(0.2); tb.start(); ta.join(30); tb.join(30)
    rows = {row[0]: row[4] for row in out}
    if not check("the second pair was matched", all(r.get("matched") for r in rows.values()) and len(rows) == 2):
        return
    stay, leave = rows["Stays"], rows["Leaves"]
    ls, ll = Listener(stay["code"], stay["playerId"]), Listener(leave["code"], leave["playerId"])
    ls.start(); ll.start()
    time.sleep(1)
    ll.stopped = True   # closes on the next event
    post("ready", {"code": stay["code"], "player": stay["playerId"]})
    _, q = ls.wait_for("question", 0, timeout=30)
    check("when the opponent leaves the lobby, a bot fills in and the game starts", q is not None)
    ls.stopped = True


def main():
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    rng = random.Random()
    check_bank()
    for n in range(rounds):
        print(f"\n===== round {n + 1} of {rounds} =====")
        check_solo(rng)
        check_matchmaking(rng)
        check_duels(rng)
        check_bot_games()
        check_ghosts()
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n{'=' * 60}\n{passed}/{len(results)} stress checks passed")
    for name, ok, detail in results:
        if not ok:
            print(f"  - {name}: {detail}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
