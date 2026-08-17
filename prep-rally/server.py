#!/usr/bin/env python3
"""PrepRally — multiplayer SAT practice game server.

Zero dependencies: Python 3 standard library only.
Real-time updates via Server-Sent Events (SSE); actions via JSON POST.
"""

import json
import mimetypes
import os
import queue
import random
import string
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(BASE_DIR, "public")
DATA_DIR = os.path.join(BASE_DIR, "data")
HIGHSCORES_FILE = os.path.join(DATA_DIR, "highscores.json")

PORT = int(os.environ.get("PORT", 3000))

with open(os.path.join(DATA_DIR, "questions.json"), encoding="utf-8") as f:
    QUESTIONS = json.load(f)

TIMER_MS = {"easy": 60000, "medium": 75000, "hard": 90000}
BASE_POINTS = {"easy": 500, "medium": 750, "hard": 1000}
STREAK_BONUS = 100
STREAK_CAP = 500
MAX_PLAYERS = 20
CODE_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

LOCK = threading.RLock()
PARTIES = {}
MATCH_QUEUE = []  # waiting tickets: {ticket, name, section, count, created, result}
QUEUE_TTL = 120  # seconds before an unpolled ticket is dropped
DUEL_REVEAL_SECS = 7


def now_ms():
    return int(time.time() * 1000)


def load_highscores():
    try:
        with open(HIGHSCORES_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def save_highscores(scores):
    with open(HIGHSCORES_FILE, "w", encoding="utf-8") as f:
        json.dump(scores, f, indent=2)


def generate_code():
    while True:
        code = "".join(random.choice(CODE_CHARS) for _ in range(5))
        if code not in PARTIES:
            return code


def sanitize_name(name):
    return (str(name or "").strip()[:16]) or "Player"


class Party:
    def __init__(self, code, settings, questions, mode="party"):
        self.code = code
        self.host_id = None
        self.players = {}  # pid -> player dict
        self.settings = settings
        self.questions = questions
        self.q_index = 0
        self.phase = "lobby"
        self.current_answers = {}  # pid -> {choice, points, correct}
        self.ends_at = 0
        self.timer = None
        self.mode = mode  # "party" (host controls) or "duel" (ready-up + auto-advance)
        self.ready = set()  # pids that have readied up (duel mode)

    # ---- helpers ----
    def connected(self):
        return [p for p in self.players.values() if p["connected"]]

    def unique_name(self, name):
        taken = {p["name"] for p in self.players.values()}
        if name not in taken:
            return name
        i = 2
        while f"{name} {i}" in taken:
            i += 1
        return f"{name} {i}"

    def add_player(self, name):
        pid = uuid.uuid4().hex
        self.players[pid] = {
            "id": pid, "name": self.unique_name(sanitize_name(name)),
            "score": 0, "streak": 0, "correct": 0, "answers": [],
            "connected": True, "queues": [],
        }
        return pid

    def lobby_state(self):
        return {
            "code": self.code,
            "mode": self.mode,
            "settings": self.settings,
            "players": [
                {"name": p["name"], "isHost": p["id"] == self.host_id,
                 "connected": p["connected"], "ready": p["id"] in self.ready}
                for p in self.players.values()
            ],
            "questionCount": len(self.questions),
        }

    def leaderboard(self):
        board = [
            {"name": p["name"], "score": p["score"], "streak": p["streak"],
             "correct": p["correct"], "connected": p["connected"]}
            for p in self.players.values()
        ]
        board.sort(key=lambda p: -p["score"])
        return board

    def public_question(self):
        q = self.questions[self.q_index]
        return {
            "id": q["id"],
            "index": self.q_index,
            "total": len(self.questions),
            "section": q["section"], "domain": q["domain"], "skill": q["skill"],
            "difficulty": q["difficulty"],
            "passage": q.get("passage"),
            "question": q["question"], "choices": q["choices"],
            "basePoints": BASE_POINTS[q["difficulty"]],
            "durationMs": TIMER_MS[q["difficulty"]],
            "endsAt": self.ends_at,
            "serverNow": now_ms(),
        }

    def broadcast(self, event, data):
        payload = (event, json.dumps(data))
        for p in self.players.values():
            for q in list(p["queues"]):
                q.put(payload)

    # ---- game flow ----
    def start_question(self):
        q = self.questions[self.q_index]
        self.phase = "question"
        self.current_answers = {}
        self.ends_at = now_ms() + TIMER_MS[q["difficulty"]]
        if self.timer:
            self.timer.cancel()
        self.timer = threading.Timer(TIMER_MS[q["difficulty"]] / 1000 + 0.5, self.end_question)
        self.timer.daemon = True
        self.timer.start()
        self.broadcast("question", self.public_question())

    def end_question(self):
        with LOCK:
            if self.phase != "question":
                return
            if self.timer:
                self.timer.cancel()
            self.phase = "reveal"
            q = self.questions[self.q_index]
            counts = [0, 0, 0, 0]
            per_player = {}
            for p in self.players.values():
                ans = self.current_answers.get(p["id"])
                if ans is None:
                    p["streak"] = 0
                    p["answers"].append({"qId": q["id"], "choice": None, "correct": False, "points": 0})
                    per_player[p["name"]] = {"correct": False, "points": 0}
                else:
                    counts[ans["choice"]] += 1
                    per_player[p["name"]] = {"correct": ans["correct"], "points": ans["points"]}
            is_last = self.q_index >= len(self.questions) - 1
            self.broadcast("reveal", {
                "correctIndex": q["answer"],
                "explanation": q["explanation"],
                "counts": counts,
                "perPlayer": per_player,
                "leaderboard": self.leaderboard(),
                "isLast": is_last,
                "autoAdvanceSecs": DUEL_REVEAL_SECS if self.mode == "duel" else None,
            })
            if self.mode == "duel":
                self.timer = threading.Timer(DUEL_REVEAL_SECS, self.auto_advance)
                self.timer.daemon = True
                self.timer.start()

    def auto_advance(self):
        with LOCK:
            if self.phase != "reveal":
                return
            if self.q_index >= len(self.questions) - 1:
                self.end_game()
            else:
                self.q_index += 1
                self.start_question()

    def end_game(self):
        self.phase = "ended"
        board = self.leaderboard()
        total = len(self.questions)

        highscores = load_highscores()
        date = time.strftime("%Y-%m-%d")
        for p in board:
            if p["score"] > 0:
                highscores.append({
                    "name": p["name"], "score": p["score"], "correct": p["correct"],
                    "total": total, "section": self.settings["section"], "date": date,
                })
        highscores.sort(key=lambda h: -h["score"])
        top = highscores[:50]
        save_highscores(top)

        breakdowns = {}
        for p in self.players.values():
            by_domain = {}
            for i, a in enumerate(p["answers"]):
                if i >= len(self.questions):
                    break
                domain = self.questions[i]["domain"]
                d = by_domain.setdefault(domain, {"correct": 0, "total": 0})
                d["total"] += 1
                if a["correct"]:
                    d["correct"] += 1
            breakdowns[p["name"]] = by_domain

        self.broadcast("game_over", {
            "leaderboard": board, "total": total,
            "breakdowns": breakdowns, "highscores": top[:10],
        })


def pick_questions(settings):
    # An explicit id list (mistake review) overrides the filters.
    ids = settings.get("ids")
    if ids:
        wanted = set(ids)
        pool = [q for q in QUESTIONS if q["id"] in wanted]
        random.shuffle(pool)
        return pool[: max(1, min(int(settings.get("count") or len(pool)), len(pool)))]

    section = settings["section"]
    domains = settings["domains"]
    difficulties = settings["difficulties"]
    skills = settings.get("skills") or []
    pool = [
        q for q in QUESTIONS
        if (section == "mixed" or q["section"] == section)
        and (not domains or q["domain"] in domains)
        and (not difficulties or q["difficulty"] in difficulties)
        and (not skills or q["skill"] in skills)
    ]
    random.shuffle(pool)
    count = max(1, min(int(settings.get("count") or 10), len(pool)))
    return pool[:count]


def clean_settings(raw):
    raw = raw or {}
    section = raw.get("section")
    if section not in ("math", "rw", "mixed"):
        section = "mixed"
    domains = raw.get("domains") if isinstance(raw.get("domains"), list) else []
    difficulties = raw.get("difficulties") if isinstance(raw.get("difficulties"), list) else []
    skills = raw.get("skills") if isinstance(raw.get("skills"), list) else []
    ids = raw.get("ids") if isinstance(raw.get("ids"), list) else []
    ids = [str(i) for i in ids][:30]
    try:
        count = max(1, min(int(raw.get("count", 10)), 30))
    except (TypeError, ValueError):
        count = 10
    return {"section": section, "domains": domains, "difficulties": difficulties,
            "skills": skills, "ids": ids, "count": count}


def handle_disconnect(party, player):
    """Called when a player's last SSE stream dies."""
    player["connected"] = False
    if party.phase == "lobby":
        party.players.pop(player["id"], None)

    if player["id"] == party.host_id:
        remaining = party.connected()
        if remaining:
            party.host_id = remaining[0]["id"]
            party.broadcast("host_changed", {"hostName": remaining[0]["name"]})
            party.broadcast("lobby_update", party.lobby_state())
        else:
            if party.timer:
                party.timer.cancel()
            PARTIES.pop(party.code, None)
            return
    else:
        party.broadcast("lobby_update", party.lobby_state())

    still_connected = party.connected()
    if (party.phase == "question" and still_connected
            and len(party.current_answers) >= len(still_connected)):
        party.end_question()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass  # keep stdout clean

    # ---------- helpers ----------
    def send_json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, TypeError):
            return {}

    def get_party_player(self, body):
        party = PARTIES.get(str(body.get("code", "")).upper())
        if not party:
            return None, None
        player = party.players.get(body.get("player"))
        return party, player

    # ---------- routes ----------
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/events":
            return self.handle_events(parse_qs(parsed.query))
        self.serve_static(parsed.path)

    def do_POST(self):
        parsed = urlparse(self.path)
        body = self.read_json()
        route = parsed.path

        with LOCK:
            if route == "/api/create":
                return self.api_create(body)
            if route == "/api/join":
                return self.api_join(body)
            if route == "/api/highscores":
                return self.send_json({"scores": load_highscores()[:20]})
            if route == "/api/stats":
                return self.api_stats()
            if route == "/api/bank":
                return self.api_bank()
            if route == "/api/search":
                return self.api_search(body)
            if route == "/api/queue":
                return self.api_queue(body)
            if route == "/api/queue_status":
                return self.api_queue_status(body)
            if route == "/api/queue_cancel":
                return self.api_queue_cancel(body)

            party, player = self.get_party_player(body)
            if not party or not player:
                return self.send_json({"error": "Party not found."}, 404)

            if route == "/api/start":
                return self.api_start(party, player)
            if route == "/api/ready":
                return self.api_ready(party, player)
            if route == "/api/answer":
                return self.api_answer(party, player, body)
            if route == "/api/next":
                return self.api_next(party, player)
            if route == "/api/play_again":
                return self.api_play_again(party, player)

        self.send_json({"error": "Unknown endpoint."}, 404)

    # ---------- bank ----------
    def api_bank(self):
        """Summary of the question bank for the Question Bank screen."""
        domains = {}
        for q in QUESTIONS:
            d = domains.setdefault(q["domain"], {
                "domain": q["domain"], "section": q["section"],
                "total": 0, "easy": 0, "medium": 0, "hard": 0, "skills": {},
            })
            d["total"] += 1
            d[q["difficulty"]] += 1
            d["skills"][q["skill"]] = d["skills"].get(q["skill"], 0) + 1
        out = []
        for d in domains.values():
            d["skills"] = sorted(
                ({"skill": s, "count": c} for s, c in d["skills"].items()),
                key=lambda s: (-s["count"], s["skill"]),
            )
            out.append(d)
        out.sort(key=lambda d: (d["section"] != "rw", d["domain"]))
        return self.send_json({"domains": out, "total": len(QUESTIONS)})

    def api_search(self, body):
        """Free-text search over question text, domain, and skill."""
        q = str(body.get("q", "")).strip().lower()
        if len(q) < 2:
            return self.send_json({"results": [], "query": q})
        terms = [t for t in q.split() if t]
        hits = []
        for item in QUESTIONS:
            hay = " ".join([
                item["question"], item.get("passage") or "",
                item["domain"], item["skill"], item["difficulty"],
            ]).lower()
            if all(t in hay for t in terms):
                text = item["question"]
                hits.append({
                    "id": item["id"], "domain": item["domain"], "skill": item["skill"],
                    "difficulty": item["difficulty"], "section": item["section"],
                    "question": text[:150] + ("…" if len(text) > 150 else ""),
                })
            if len(hits) >= 40:
                break
        return self.send_json({"results": hits, "query": q})

    # ---------- stats & matchmaking ----------
    def api_stats(self):
        online = sum(
            1 for party in PARTIES.values() for p in party.players.values() if p["connected"]
        )
        by_section = {"math": 0, "rw": 0}
        for q in QUESTIONS:
            by_section[q["section"]] = by_section.get(q["section"], 0) + 1
        self.send_json({"bank": by_section, "online": online, "queued": len(MATCH_QUEUE)})

    def api_queue(self, body):
        now = time.time()
        # Keep matched tickets around until their owner polls and collects the result.
        MATCH_QUEUE[:] = [t for t in MATCH_QUEUE if now - t["polled"] < QUEUE_TTL]
        section = body.get("section") if body.get("section") in ("math", "rw", "mixed") else "mixed"
        name = sanitize_name(body.get("name"))
        count = max(3, min(int(body.get("count") or 10), 20))

        for t in MATCH_QUEUE:
            if t["section"] == section and not t["result"]:
                settings = {"section": section, "domains": [], "difficulties": [], "count": count}
                questions = pick_questions(settings)
                code = generate_code()
                party = Party(code, settings, questions, mode="duel")
                pid_a = party.add_player(t["name"])
                pid_b = party.add_player(name)
                party.host_id = pid_a
                PARTIES[code] = party
                t["result"] = {"code": code, "playerId": pid_a, "yourName": party.players[pid_a]["name"]}
                return self.send_json({"matched": True, "code": code, "playerId": pid_b,
                                       "yourName": party.players[pid_b]["name"]})

        ticket = uuid.uuid4().hex
        MATCH_QUEUE.append({"ticket": ticket, "name": name, "section": section,
                            "count": count, "polled": now, "result": None})
        return self.send_json({"matched": False, "ticket": ticket})

    def api_queue_status(self, body):
        ticket = body.get("ticket")
        for t in list(MATCH_QUEUE):
            if t["ticket"] == ticket:
                t["polled"] = time.time()
                if t["result"]:
                    MATCH_QUEUE.remove(t)
                    return self.send_json(dict({"matched": True}, **t["result"]))
                return self.send_json({"matched": False})
        return self.send_json({"matched": False, "expired": True})

    def api_queue_cancel(self, body):
        ticket = body.get("ticket")
        MATCH_QUEUE[:] = [t for t in MATCH_QUEUE if t["ticket"] != ticket]
        return self.send_json({"ok": True})

    def api_ready(self, party, player):
        if party.phase != "lobby":
            return self.send_json({"error": "Game already started."})
        party.ready.add(player["id"])
        party.broadcast("lobby_update", party.lobby_state())
        connected = party.connected()
        if party.mode == "duel" and len(connected) >= 2 and all(p["id"] in party.ready for p in connected):
            party.broadcast("game_started", {})
            party.start_question()
        return self.send_json({"ok": True})

    # ---------- API ----------
    def api_create(self, body):
        settings = clean_settings(body.get("settings"))
        questions = pick_questions(settings)
        if not questions:
            return self.send_json({"error": "No questions match those filters. Try widening them."})
        code = generate_code()
        party = Party(code, settings, questions)
        pid = party.add_player(body.get("name"))
        party.host_id = pid
        PARTIES[code] = party
        self.send_json({"ok": True, "code": code, "playerId": pid,
                        "yourName": party.players[pid]["name"], "state": party.lobby_state()})

    def api_join(self, body):
        code = str(body.get("code", "")).strip().upper()
        party = PARTIES.get(code)
        if not party:
            return self.send_json({"error": "Party not found. Check the code."})
        if party.phase != "lobby":
            return self.send_json({"error": "That game already started. Ask the host for a rematch!"})
        if len(party.connected()) >= MAX_PLAYERS:
            return self.send_json({"error": "This party is full (20 players max)."})
        pid = party.add_player(body.get("name"))
        party.broadcast("lobby_update", party.lobby_state())
        self.send_json({"ok": True, "code": code, "playerId": pid,
                        "yourName": party.players[pid]["name"], "state": party.lobby_state()})

    def api_start(self, party, player):
        if player["id"] != party.host_id or party.phase != "lobby":
            return self.send_json({"error": "Only the host can start."})
        party.broadcast("game_started", {})
        party.start_question()
        self.send_json({"ok": True})

    def api_answer(self, party, player, body):
        if party.phase != "question" or player["id"] in party.current_answers:
            return self.send_json({"ok": False})
        try:
            choice = int(body.get("choice"))
        except (TypeError, ValueError):
            return self.send_json({"ok": False})
        if not 0 <= choice <= 3:
            return self.send_json({"ok": False})

        q = party.questions[party.q_index]
        remaining = max(0, party.ends_at - now_ms())
        if remaining <= 0:
            return self.send_json({"ok": False, "error": "Time's up!"})
        frac = remaining / TIMER_MS[q["difficulty"]]
        correct = choice == q["answer"]

        points = 0
        if correct:
            player["streak"] += 1
            streak_bonus = min(STREAK_CAP, (player["streak"] - 1) * STREAK_BONUS)
            points = round(BASE_POINTS[q["difficulty"]] * (0.5 + 0.5 * frac)) + streak_bonus
            player["score"] += points
            player["correct"] += 1
        else:
            player["streak"] = 0
        player["answers"].append({"qId": q["id"], "choice": choice, "correct": correct, "points": points})
        party.current_answers[player["id"]] = {"choice": choice, "points": points, "correct": correct}

        party.broadcast("answer_progress", {
            "answered": len(party.current_answers),
            "total": len(party.connected()),
        })
        if len(party.current_answers) >= len(party.connected()):
            t = threading.Timer(0.6, party.end_question)
            t.daemon = True
            t.start()
        self.send_json({"ok": True})

    def api_next(self, party, player):
        if player["id"] != party.host_id or party.phase != "reveal":
            return self.send_json({"error": "Only the host can advance."})
        if party.q_index >= len(party.questions) - 1:
            party.end_game()
        else:
            party.q_index += 1
            party.start_question()
        self.send_json({"ok": True})

    def api_play_again(self, party, player):
        if player["id"] != party.host_id or party.phase != "ended":
            return self.send_json({"error": "Only the host can restart."})
        party.questions = pick_questions(party.settings)
        party.q_index = 0
        party.phase = "lobby"
        for pid in list(party.players):
            p = party.players[pid]
            if not p["connected"]:
                del party.players[pid]
            else:
                p.update(score=0, streak=0, correct=0, answers=[])
        party.broadcast("back_to_lobby", party.lobby_state())
        self.send_json({"ok": True})

    # ---------- SSE ----------
    def handle_events(self, params):
        code = (params.get("code", [""])[0]).upper()
        pid = params.get("player", [""])[0]
        with LOCK:
            party = PARTIES.get(code)
            player = party.players.get(pid) if party else None
            if not player:
                return self.send_json({"error": "Unknown party or player."}, 404)
            q = queue.Queue()
            player["queues"].append(q)
            player["connected"] = True

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        with LOCK:
            party.broadcast("lobby_update", party.lobby_state())

        try:
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()
            while True:
                try:
                    event, data = q.get(timeout=10)
                    msg = f"event: {event}\ndata: {data}\n\n".encode()
                    self.wfile.write(msg)
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            with LOCK:
                if q in player["queues"]:
                    player["queues"].remove(q)
                if not player["queues"] and PARTIES.get(code) is party:
                    handle_disconnect(party, player)

    # ---------- static files ----------
    def serve_static(self, path):
        if path == "/":
            path = "/index.html"
        safe = os.path.normpath(path).lstrip("/\\")
        full = os.path.join(PUBLIC_DIR, safe)
        if not full.startswith(PUBLIC_DIR) or not os.path.isfile(full):
            return self.send_json({"error": "Not found"}, 404)
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        with open(full, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"PrepRally running on http://localhost:{PORT}")
    server.serve_forever()
