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
DESMOS_KEY_FILE = os.path.join(DATA_DIR, "desmos_key.txt")

# Desmos's publicly documented demo key. Fine for local development; a real
# deployment should supply its own via DESMOS_API_KEY or data/desmos_key.txt.
DESMOS_DEMO_KEY = "dcb31709b452b1cf9dc26972add0fda6"


def desmos_api_key():
    key = (os.environ.get("DESMOS_API_KEY") or "").strip()
    if key:
        return key
    try:
        with open(DESMOS_KEY_FILE, encoding="utf-8") as f:
            key = f.read().strip()
            if key:
                return key
    except OSError:
        pass
    return DESMOS_DEMO_KEY

PORT = int(os.environ.get("PORT", 3000))

# When the frontend is hosted separately (e.g. on Vercel) the browser calls this
# server cross-origin. List those origins in ALLOWED_ORIGINS, comma separated.
# Same-origin deploys need nothing: the header is only sent for listed origins.
# The production frontend is always allowed so it works even without the env var.
ALLOWED_ORIGINS = ["https://lumosat.vercel.app"] + [
    o.strip().rstrip("/") for o in (os.environ.get("ALLOWED_ORIGINS") or "").split(",") if o.strip()
]

with open(os.path.join(DATA_DIR, "questions.json"), encoding="utf-8") as f:
    QUESTIONS = json.load(f)
# Generated grammar and transition drills (tools/gen_grammar.py builds this file).
GRAMMAR_FILE = os.path.join(DATA_DIR, "grammar.json")
if os.path.exists(GRAMMAR_FILE):
    with open(GRAMMAR_FILE, encoding="utf-8") as f:
        QUESTIONS += json.load(f)
# Generated math drills, about a quarter of them typed-answer (tools/gen_math.py).
MATH_FILE = os.path.join(DATA_DIR, "math.json")
if os.path.exists(MATH_FILE):
    with open(MATH_FILE, encoding="utf-8") as f:
        QUESTIONS += json.load(f)
# Hand-written reading passages (tools/gen_reading.py builds this file).
READING_FILE = os.path.join(DATA_DIR, "reading.json")
if os.path.exists(READING_FILE):
    with open(READING_FILE, encoding="utf-8") as f:
        QUESTIONS += json.load(f)
# Figures (tools/gen_figures.py): SVGs for existing questions plus questions
# that are answered from a graph, diagram, chart, or table.
FIGURES_FILE = os.path.join(DATA_DIR, "figures.json")
if os.path.exists(FIGURES_FILE):
    with open(FIGURES_FILE, encoding="utf-8") as f:
        _figures = json.load(f)
    for _q in QUESTIONS:
        if _q["id"] in _figures["attach"]:
            _q["figure"] = _figures["attach"][_q["id"]]
    QUESTIONS += _figures["questions"]

QUESTIONS_BY_ID = {q["id"]: q for q in QUESTIONS}
# "More like this": math templates can build fresh copies of a question on
# demand. Those copies live here (not in the bank) so a session can serve them.
VARIANTS = {}
VARIANTS_MAX = 5000
# The template that writes each math skill, so a hand-written question can get
# generated copies of the same kind.
SKILL_TPL = {}
for _q in QUESTIONS:
    if _q.get("tpl"):
        SKILL_TPL.setdefault(_q["skill"], _q["tpl"])


def find_question(qid):
    return QUESTIONS_BY_ID.get(qid) or VARIANTS.get(qid)


def similar_questions(qid, count):
    """New questions like `qid`: generated copies for math, then other
    questions on the same skill, then the same domain and difficulty."""
    src = find_question(qid)
    if not src:
        return []
    out = []
    tpl = src.get("tpl") or SKILL_TPL.get(src["skill"])
    if tpl:
        try:
            import sys
            tools = os.path.join(BASE_DIR, "tools")
            if tools not in sys.path:
                sys.path.insert(0, tools)
            import gen_math
            with LOCK:   # the generator keeps module-level state
                made = gen_math.variants(tpl, src["skill"], count,
                                         avoid={q["question"] for q in QUESTIONS if q.get("tpl") == tpl})
            for q in made:
                VARIANTS[q["id"]] = q
                out.append(q)
            while len(VARIANTS) > VARIANTS_MAX:
                VARIANTS.pop(next(iter(VARIANTS)))
        except Exception as e:   # never block practice on the generator
            print("variant generation failed:", e)
    for same in (lambda q: q["skill"] == src["skill"],
                 lambda q: q["domain"] == src["domain"] and q["difficulty"] == src["difficulty"]):
        if len(out) >= count:
            break
        taken = {q["id"] for q in out} | {qid}
        pool = [q for q in QUESTIONS if same(q) and q["id"] not in taken]
        random.shuffle(pool)
        out += pool[: count - len(out)]
    return out[:count]


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

# 2v2: four players, two teams, one Reading specialist and one Math specialist
# per team. Answering inside your own specialty pays a bonus.
TEAM_SIZE = 2
TEAM_PLAYERS = 4
SPECIALIST_BONUS = 1.25

CLASSES_FILE = os.path.join(DATA_DIR, "classes.json")
TUTORS_FILE = os.path.join(DATA_DIR, "tutors.json")
CLASSES = {}   # code -> class dict
TUTORS = {}    # playerKey -> application dict
PRESENCE = {}  # playerKey -> {code, name, elo, activity, lastSeen, invites}
PRESENCE_TTL = 45      # seconds without a ping before a friend reads as offline
PRESENCE_SWEEP = 86400  # drop presence rows untouched for a day
INVITE_TTL = 90        # seconds an unaccepted duel invite survives
FRIEND_CODE_LEN = 6


def now_ms():
    return int(time.time() * 1000)


def load_json_file(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json_file(path, data):
    """Write via a temp file so a crash mid-write cannot truncate the real one."""
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except OSError:
        pass


def save_classes():
    save_json_file(CLASSES_FILE, CLASSES)


def save_tutors():
    save_json_file(TUTORS_FILE, TUTORS)


def clip(value, limit, fallback=""):
    """Trim any client-supplied string to a sane length."""
    text = str(value if value is not None else "").strip()
    return text[:limit] or fallback


def load_highscores():
    try:
        with open(HIGHSCORES_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def save_highscores(scores):
    with open(HIGHSCORES_FILE, "w", encoding="utf-8") as f:
        json.dump(scores, f, indent=2)


def generate_code(taken=None, length=5):
    """A short, human-readable code that avoids look-alike characters."""
    taken = PARTIES if taken is None else taken
    while True:
        code = "".join(random.choice(CODE_CHARS) for _ in range(length))
        if code not in taken:
            return code


def friend_codes():
    return {p["code"] for p in PRESENCE.values() if p.get("code")}


def sanitize_name(name):
    return (str(name or "").strip()[:16]) or "Player"


def clean_elo(elo):
    """Ratings are kept on the client; the server only relays them for pairing."""
    try:
        return max(100, min(int(elo), 4000))
    except (TypeError, ValueError):
        return 1200


DIFFICULTIES = ("easy", "medium", "hard")


def parse_number(text):
    """A typed answer as an exact Fraction, or None. Accepts 7, -3, 3.5, .5, 7/2."""
    from fractions import Fraction
    t = str(text or "").strip().replace("\u2212", "-").replace(" ", "")
    if not t or len(t) > 8:
        return None
    try:
        if t.count("/") == 1:
            num, den = t.split("/")
            if not num or not den or "." in den:
                return None
            return Fraction(Fraction(num), Fraction(den))
        return Fraction(t)
    except (ValueError, ZeroDivisionError):
        return None


def grade_response(q, text):
    """Grade a typed answer the way the digital SAT does: any equivalent form
    counts (7/2 = 3.5), and a long decimal counts if it is the true value
    rounded or cut off to at least three decimal places (2/3 as .666 or .667)."""
    got = parse_number(text)
    if got is None:
        return False
    raw = str(text).strip()
    places = len(raw.split(".", 1)[1]) if "." in raw and "/" not in raw else 0
    for ans in q["answers"]:
        want = parse_number(ans)
        if want is None:
            continue
        if got == want:
            return True
        if places >= 3 and abs(float(got) - float(want)) < 10 ** -places:
            return True
    return False


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
        # "party" (host controls), "duel" (1v1 ready-up + auto-advance), or
        # "team" (2v2: same ready-up and auto-advance, scores summed per team).
        self.mode = mode
        self.ready = set()  # pids that have readied up (duel and team modes)
        self.teams = {}     # pid -> "A" or "B"      (team mode only)
        self.roles = {}     # pid -> "rw" or "math"  (team mode only)
        # Practice has no per-question clock and no speed bonus; ranked duels,
        # 2v2, and multiplayer parties keep both.
        self.untimed = bool(settings.get("practice")) and mode == "party"

    def auto_advances(self):
        return self.mode in ("duel", "team")

    def assign_team(self, pid):
        """Seat the next arrival: A/B alternating, Reading then Math per team."""
        seat = sum(1 for x in self.teams if x in self.players and x != pid)
        self.teams[pid] = "A" if seat % 2 == 0 else "B"
        self.roles[pid] = "rw" if seat < TEAM_SIZE else "math"

    def team_scores(self):
        totals = {"A": {"team": "A", "score": 0, "correct": 0, "members": []},
                  "B": {"team": "B", "score": 0, "correct": 0, "members": []}}
        for pid, p in self.players.items():
            side = self.teams.get(pid)
            if side not in totals:
                continue
            totals[side]["score"] += p["score"]
            totals[side]["correct"] += p["correct"]
            totals[side]["members"].append(p["name"])
        return [totals["A"], totals["B"]]

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

    def add_player(self, name, elo=None):
        pid = uuid.uuid4().hex
        self.players[pid] = {
            "id": pid, "name": self.unique_name(sanitize_name(name)),
            "score": 0, "streak": 0, "correct": 0, "answers": [],
            "connected": True, "queues": [], "elo": clean_elo(elo),
        }
        return pid

    def lobby_state(self):
        return {
            "code": self.code,
            "mode": self.mode,
            "settings": self.settings,
            "players": [
                {"name": p["name"], "isHost": p["id"] == self.host_id, "elo": p["elo"],
                 "connected": p["connected"], "ready": p["id"] in self.ready,
                 "team": self.teams.get(p["id"]), "role": self.roles.get(p["id"])}
                for p in self.players.values()
            ],
            "questionCount": len(self.questions),
            "teamSize": TEAM_SIZE if self.mode == "team" else None,
        }

    def leaderboard(self):
        board = [
            {"name": p["name"], "score": p["score"], "streak": p["streak"], "elo": p["elo"],
             "correct": p["correct"], "connected": p["connected"],
             "team": self.teams.get(p["id"]), "role": self.roles.get(p["id"])}
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
            "figure": q.get("figure"),
            "type": q.get("type", "mcq"),
            "question": q["question"], "choices": q.get("choices") or [],
            "basePoints": BASE_POINTS[q["difficulty"]],
            "untimed": self.untimed,
            "durationMs": None if self.untimed else TIMER_MS[q["difficulty"]],
            "endsAt": None if self.untimed else self.ends_at,
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
        if self.timer:
            self.timer.cancel()
            self.timer = None
        if self.untimed:
            self.ends_at = 0
        else:
            self.ends_at = now_ms() + TIMER_MS[q["difficulty"]]
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
                    if ans["choice"] is not None:
                        counts[ans["choice"]] += 1
                    per_player[p["name"]] = {"correct": ans["correct"], "points": ans["points"]}
            is_last = self.q_index >= len(self.questions) - 1
            spr = q.get("type") == "spr"
            self.broadcast("reveal", {
                "type": q.get("type", "mcq"),
                "correctIndex": None if spr else q["answer"],
                "correctAnswer": q["answers"][0] if spr else None,
                "correctCount": sum(1 for a in self.current_answers.values() if a["correct"]),
                "explanation": q["explanation"],
                "counts": counts,
                "perPlayer": per_player,
                "leaderboard": self.leaderboard(),
                "isLast": is_last,
                "autoAdvanceSecs": DUEL_REVEAL_SECS if self.auto_advances() else None,
                "teamScores": self.team_scores() if self.mode == "team" else None,
            })
            if self.auto_advances():
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
            "teamScores": self.team_scores() if self.mode == "team" else None,
        })


def pick_questions(settings):
    if settings.get("similar"):
        return similar_questions(settings["similar"], settings.get("count") or 5)
    # An explicit id list (mistake review) overrides the filters.
    ids = settings.get("ids")
    if ids:
        wanted = set(ids)
        pool = [q for q in QUESTIONS if q["id"] in wanted] + [VARIANTS[i] for i in ids if i in VARIANTS]
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
    # Deal round-robin across domains so the thousand generated grammar drills
    # can't crowd everything else out of a mixed or whole-section session.
    by_domain = {}
    for q in pool:
        by_domain.setdefault(q["domain"], []).append(q)
    decks = list(by_domain.values())
    random.shuffle(decks)
    picked = []
    while len(picked) < count:
        for deck in decks:
            if deck and len(picked) < count:
                picked.append(deck.pop())
    random.shuffle(picked)
    return picked


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
            "skills": skills, "ids": ids, "count": count,
            # Solo practice: no clock and no speed scoring. Ranked play stays timed.
            "practice": bool(raw.get("practice")),
            "similar": str(raw.get("similar") or "")[:48]}


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
    def send_cors(self):
        """Echo the origin only when it is explicitly allowed."""
        origin = self.headers.get("Origin")
        if origin and origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def send_json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_cors()
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
            if route == "/api/config":
                key = desmos_api_key()
                return self.send_json({
                    "desmosKey": key,
                    "desmosIsDemoKey": key == DESMOS_DEMO_KEY,
                })
            if route == "/api/presence":
                return self.api_presence(body)
            if route == "/api/friend_lookup":
                return self.api_friend_lookup(body)
            if route == "/api/invite":
                return self.api_invite(body)
            if route == "/api/class_create":
                return self.api_class_create(body)
            if route == "/api/class_join":
                return self.api_class_join(body)
            if route == "/api/class_list":
                return self.api_class_list(body)
            if route == "/api/class_get":
                return self.api_class_get(body)
            if route == "/api/class_report":
                return self.api_class_report(body)
            if route == "/api/class_assign":
                return self.api_class_assign(body)
            if route == "/api/class_leave":
                return self.api_class_leave(body)
            if route == "/api/tutor_apply":
                return self.api_tutor_apply(body)
            if route == "/api/tutor_status":
                return self.api_tutor_status(body)
            if route == "/api/tutor_withdraw":
                return self.api_tutor_withdraw(body)
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

    # ---------- friends & presence ----------
    def api_presence(self, body):
        """Heartbeat. Registers this player, then reports back on their friends.

        Identity is the browser-generated playerKey, the same one the rest of the
        social features use. There are no passwords, so a key is a claim rather
        than proof; it is enough for a friends list and deliberately not enough
        for anything destructive.
        """
        key = clip(body.get("playerKey"), 64)
        if not key:
            return self.send_json({"error": "Missing player key."}, 400)
        now = time.time()

        # Drop rows nobody has touched in a day so the dict cannot grow forever.
        for stale in [k for k, v in PRESENCE.items() if now - v["lastSeen"] > PRESENCE_SWEEP]:
            PRESENCE.pop(stale, None)

        me = PRESENCE.get(key)
        if not me:
            me = {"code": generate_code(friend_codes(), FRIEND_CODE_LEN),
                  "name": "", "elo": 1200, "activity": "", "lastSeen": now, "invites": []}
            PRESENCE[key] = me
        me["name"] = sanitize_name(body.get("name"))
        me["activity"] = clip(body.get("activity"), 40)
        me["lastSeen"] = now
        try:
            me["elo"] = max(0, min(int(body.get("elo") or 1200), 9999))
        except (TypeError, ValueError):
            pass

        wanted = [clip(c, FRIEND_CODE_LEN).upper()
                  for c in (body.get("friends") or [])][:50]
        by_code = {v["code"]: v for v in PRESENCE.values()}
        friends = []
        for code in wanted:
            row = by_code.get(code)
            if not row:
                friends.append({"code": code, "name": "", "online": False,
                                "activity": "", "elo": None, "unknown": True})
                continue
            friends.append({
                "code": code, "name": row["name"], "elo": row["elo"],
                "online": now - row["lastSeen"] < PRESENCE_TTL,
                "activity": row["activity"],
                "lastSeen": int(row["lastSeen"] * 1000),
            })

        me["invites"] = [i for i in me["invites"] if now - i["when"] < INVITE_TTL]
        invites, me["invites"] = me["invites"], []
        return self.send_json({"code": me["code"], "friends": friends, "invites": invites})

    def api_friend_lookup(self, body):
        code = clip(body.get("code"), FRIEND_CODE_LEN).upper()
        for row in PRESENCE.values():
            if row["code"] == code:
                return self.send_json({"found": True, "code": code, "name": row["name"]})
        return self.send_json({"found": False})

    def api_invite(self, body):
        """Push a duel invitation into a friend's next presence poll."""
        key = clip(body.get("playerKey"), 64)
        target = clip(body.get("toCode"), FRIEND_CODE_LEN).upper()
        party_code = clip(body.get("partyCode"), 5).upper()
        if party_code not in PARTIES:
            return self.send_json({"error": "That game no longer exists."}, 404)
        me = PRESENCE.get(key)
        for row in PRESENCE.values():
            if row["code"] == target:
                if len(row["invites"]) >= 10:
                    return self.send_json({"error": "That player has too many pending invites."})
                row["invites"].append({
                    "fromName": me["name"] if me else "A player",
                    "fromCode": me["code"] if me else "",
                    "partyCode": party_code,
                    "mode": clip(body.get("mode"), 12, "duel"),
                    "when": time.time(),
                })
                return self.send_json({"ok": True})
        return self.send_json({"error": "That friend is not online right now."})

    # ---------- classes ----------
    def class_view(self, cls, key):
        """A class as the caller is allowed to see it."""
        is_teacher = cls["teacherKey"] == key
        students = sorted(cls["students"].values(),
                          key=lambda st: (-st.get("points", 0), st.get("name", "")))
        return {
            "code": cls["code"], "name": cls["name"], "teacherName": cls["teacherName"],
            "isTeacher": is_teacher, "created": cls["created"],
            "assignment": cls.get("assignment"),
            "students": [{
                "name": st.get("name", ""),
                "attempted": st.get("attempted", 0),
                "correct": st.get("correct", 0),
                "points": st.get("points", 0),
                "accuracy": (round(100 * st["correct"] / st["attempted"])
                             if st.get("attempted") else None),
                "weakest": st.get("weakest", ""),
                "assignmentDone": st.get("assignmentDone") == (cls.get("assignment") or {}).get("id"),
                "lastSeen": st.get("lastSeen", 0),
                "isMe": st.get("key") == key,
            } for st in students],
        }

    def api_class_create(self, body):
        key = clip(body.get("playerKey"), 64)
        name = clip(body.get("className"), 40)
        if not key:
            return self.send_json({"error": "Missing player key."}, 400)
        if len(name) < 2:
            return self.send_json({"error": "Give the class a name of at least 2 characters."})
        mine = [c for c in CLASSES.values() if c["teacherKey"] == key]
        if len(mine) >= 10:
            return self.send_json({"error": "You already run 10 classes, which is the limit."})
        code = generate_code(CLASSES)
        CLASSES[code] = {
            "code": code, "name": name, "teacherKey": key,
            "teacherName": sanitize_name(body.get("name")),
            "created": int(time.time() * 1000), "assignment": None, "students": {},
        }
        save_classes()
        return self.send_json({"ok": True, "class": self.class_view(CLASSES[code], key)})

    def api_class_join(self, body):
        key = clip(body.get("playerKey"), 64)
        code = clip(body.get("code"), 5).upper()
        cls = CLASSES.get(code)
        if not cls:
            return self.send_json({"error": "No class with that code. Check it with your teacher."})
        if cls["teacherKey"] == key:
            return self.send_json({"error": "You teach this class already."})
        if key not in cls["students"] and len(cls["students"]) >= 60:
            return self.send_json({"error": "That class is full (60 students max)."})
        student = cls["students"].setdefault(key, {"key": key})
        student["name"] = sanitize_name(body.get("name"))
        student["lastSeen"] = int(time.time() * 1000)
        student.setdefault("attempted", 0)
        student.setdefault("correct", 0)
        student.setdefault("points", 0)
        save_classes()
        return self.send_json({"ok": True, "class": self.class_view(cls, key)})

    def api_class_list(self, body):
        key = clip(body.get("playerKey"), 64)
        out = []
        for cls in CLASSES.values():
            if cls["teacherKey"] == key or key in cls["students"]:
                out.append({
                    "code": cls["code"], "name": cls["name"],
                    "teacherName": cls["teacherName"],
                    "isTeacher": cls["teacherKey"] == key,
                    "size": len(cls["students"]),
                    "hasAssignment": bool(cls.get("assignment")),
                })
        out.sort(key=lambda c: (not c["isTeacher"], c["name"]))
        return self.send_json({"classes": out})

    def api_class_get(self, body):
        key = clip(body.get("playerKey"), 64)
        cls = CLASSES.get(clip(body.get("code"), 5).upper())
        if not cls:
            return self.send_json({"error": "Class not found."}, 404)
        if cls["teacherKey"] != key and key not in cls["students"]:
            return self.send_json({"error": "You are not in this class."}, 403)
        return self.send_json({"class": self.class_view(cls, key)})

    def api_class_report(self, body):
        """Students push their own totals up after finishing a session."""
        key = clip(body.get("playerKey"), 64)
        cls = CLASSES.get(clip(body.get("code"), 5).upper())
        if not cls or key not in cls["students"]:
            return self.send_json({"ok": False})
        stats = body.get("stats") or {}
        student = cls["students"][key]
        student["name"] = sanitize_name(body.get("name"))
        student["lastSeen"] = int(time.time() * 1000)
        for field in ("attempted", "correct", "points"):
            try:
                student[field] = max(0, min(int(stats.get(field) or 0), 10 ** 7))
            except (TypeError, ValueError):
                student[field] = 0
        student["weakest"] = clip(stats.get("weakest"), 48)
        done = clip(stats.get("assignmentDone"), 40)
        if done:
            student["assignmentDone"] = done
        save_classes()
        return self.send_json({"ok": True})

    def api_class_assign(self, body):
        key = clip(body.get("playerKey"), 64)
        cls = CLASSES.get(clip(body.get("code"), 5).upper())
        if not cls:
            return self.send_json({"error": "Class not found."}, 404)
        if cls["teacherKey"] != key:
            return self.send_json({"error": "Only the teacher can set an assignment."}, 403)
        raw = body.get("assignment")
        if raw is None:
            cls["assignment"] = None
        else:
            settings = clean_settings(raw.get("settings"))
            if not pick_questions(settings):
                return self.send_json({"error": "No questions match those filters."})
            cls["assignment"] = {
                "id": uuid.uuid4().hex[:12],
                "title": clip(raw.get("title"), 60, "Practice set"),
                "settings": settings,
                "set": int(time.time() * 1000),
            }
            for student in cls["students"].values():
                student.pop("assignmentDone", None)
        save_classes()
        return self.send_json({"ok": True, "class": self.class_view(cls, key)})

    def api_class_leave(self, body):
        key = clip(body.get("playerKey"), 64)
        code = clip(body.get("code"), 5).upper()
        cls = CLASSES.get(code)
        if not cls:
            return self.send_json({"ok": True})
        if cls["teacherKey"] == key:
            CLASSES.pop(code, None)  # the teacher leaving closes the class
        else:
            cls["students"].pop(key, None)
        save_classes()
        return self.send_json({"ok": True})

    # ---------- tutor applications ----------
    def api_tutor_apply(self, body):
        key = clip(body.get("playerKey"), 64)
        if not key:
            return self.send_json({"error": "Missing player key."}, 400)
        name = clip(body.get("applicantName"), 40)
        email = clip(body.get("email"), 80)
        subjects = [clip(x, 40) for x in (body.get("subjects") or [])][:4]
        about = clip(body.get("about"), 800)
        if len(name) < 2:
            return self.send_json({"error": "Enter your full name."})
        if "@" not in email or "." not in email.split("@")[-1] or len(email) < 6:
            return self.send_json({"error": "Enter a valid email address."})
        if not subjects:
            return self.send_json({"error": "Pick at least one subject you can tutor."})
        if len(about) < 40:
            return self.send_json({"error": "Tell us a little more — 40 characters minimum."})
        app = {
            "playerKey": key, "name": name, "email": email,
            "grade": clip(body.get("grade"), 24),
            "score": clip(body.get("score"), 12),
            "subjects": subjects, "availability": clip(body.get("availability"), 40),
            "about": about, "status": "submitted",
            "submitted": int(time.time() * 1000),
            "stats": {
                "attempted": int(body.get("attempted") or 0),
                "accuracy": int(body.get("accuracy") or 0),
            },
        }
        TUTORS[key] = app
        save_tutors()
        return self.send_json({"ok": True, "application": app})

    def api_tutor_status(self, body):
        key = clip(body.get("playerKey"), 64)
        return self.send_json({"application": TUTORS.get(key)})

    def api_tutor_withdraw(self, body):
        key = clip(body.get("playerKey"), 64)
        TUTORS.pop(key, None)
        save_tutors()
        return self.send_json({"ok": True})

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
        """Join the ladder queue. 1v1 fills at two players, 2v2 at four."""
        now = time.time()
        # Keep matched tickets around until their owner polls and collects the result.
        MATCH_QUEUE[:] = [t for t in MATCH_QUEUE if now - t["polled"] < QUEUE_TTL]
        section = body.get("section") if body.get("section") in ("math", "rw", "mixed") else "mixed"
        # Each difficulty is its own ladder: players only meet others who picked
        # the same subject and difficulty, closest rating first.
        difficulty = body.get("difficulty") if body.get("difficulty") in DIFFICULTIES else "medium"
        elo = clean_elo(body.get("elo"))
        name = sanitize_name(body.get("name"))
        count = max(3, min(int(body.get("count") or 10), 20))
        mode = "2v2" if body.get("mode") == "2v2" else "1v1"
        needed = TEAM_PLAYERS if mode == "2v2" else 2

        waiting = [t for t in MATCH_QUEUE
                   if t["mode"] == mode and t["section"] == section
                   and t["difficulty"] == difficulty and not t["result"]]
        waiting.sort(key=lambda t: abs(t["elo"] - elo))
        if len(waiting) >= needed - 1:
            joining = waiting[: needed - 1]
            settings = {"section": section, "domains": [], "difficulties": [difficulty], "count": count}
            questions = pick_questions(settings)
            code = generate_code()
            party = Party(code, settings, questions, mode="team" if mode == "2v2" else "duel")

            # Seat everyone who was waiting, then the caller last.
            for t in joining:
                pid = party.add_player(t["name"], t["elo"])
                if mode == "2v2":
                    party.assign_team(pid)
                t["result"] = {"code": code, "playerId": pid,
                               "yourName": party.players[pid]["name"]}
            mine = party.add_player(name, elo)
            if mode == "2v2":
                party.assign_team(mine)
            party.host_id = joining[0]["result"]["playerId"]
            PARTIES[code] = party
            return self.send_json({"matched": True, "code": code, "playerId": mine,
                                   "yourName": party.players[mine]["name"], "mode": mode})

        ticket = uuid.uuid4().hex
        MATCH_QUEUE.append({"ticket": ticket, "name": name, "section": section, "mode": mode,
                            "difficulty": difficulty, "elo": elo,
                            "count": count, "polled": now, "result": None})
        return self.send_json({"matched": False, "ticket": ticket, "mode": mode,
                               "waiting": len(waiting) + 1, "needed": needed})

    def api_queue_status(self, body):
        ticket = body.get("ticket")
        for t in list(MATCH_QUEUE):
            if t["ticket"] == ticket:
                t["polled"] = time.time()
                if t["result"]:
                    MATCH_QUEUE.remove(t)
                    return self.send_json(dict({"matched": True, "mode": t["mode"]}, **t["result"]))
                peers = sum(1 for o in MATCH_QUEUE
                            if o["mode"] == t["mode"] and o["section"] == t["section"]
                            and o["difficulty"] == t["difficulty"] and not o["result"])
                needed = TEAM_PLAYERS if t["mode"] == "2v2" else 2
                return self.send_json({"matched": False, "waiting": peers, "needed": needed})
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
        needed = TEAM_PLAYERS if party.mode == "team" else 2
        if (party.auto_advances() and len(connected) >= needed
                and all(p["id"] in party.ready for p in connected)):
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
        pid = party.add_player(body.get("name"), body.get("elo"))
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
        pid = party.add_player(body.get("name"), body.get("elo"))
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
        q = party.questions[party.q_index]
        response = None
        if q.get("type") == "spr":
            response = str(body.get("response") or "").strip()[:8]
            if not response:
                return self.send_json({"ok": False})
            choice = None
            correct = grade_response(q, response)
        else:
            try:
                choice = int(body.get("choice"))
            except (TypeError, ValueError):
                return self.send_json({"ok": False})
            if not 0 <= choice <= 3:
                return self.send_json({"ok": False})
            correct = choice == q["answer"]

        if party.untimed:
            frac = 1.0   # practice: full points however long it takes
        else:
            remaining = max(0, party.ends_at - now_ms())
            if remaining <= 0:
                return self.send_json({"ok": False, "error": "Time's up!"})
            frac = remaining / TIMER_MS[q["difficulty"]]

        points = 0
        if correct:
            player["streak"] += 1
            streak_bonus = min(STREAK_CAP, (player["streak"] - 1) * STREAK_BONUS)
            points = round(BASE_POINTS[q["difficulty"]] * (0.5 + 0.5 * frac)) + streak_bonus
            # 2v2: answering inside the section you were assigned pays extra.
            if party.mode == "team" and party.roles.get(player["id"]) == q["section"]:
                points = round(points * SPECIALIST_BONUS)
            player["score"] += points
            player["correct"] += 1
        else:
            player["streak"] = 0
        player["answers"].append({"qId": q["id"], "choice": choice, "response": response,
                                  "correct": correct, "points": points})
        party.current_answers[player["id"]] = {"choice": choice, "response": response,
                                               "points": points, "correct": correct}

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
        self.send_cors()
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
    CLASSES.update(load_json_file(CLASSES_FILE, {}))
    TUTORS.update(load_json_file(TUTORS_FILE, {}))
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"PrepRally running on http://localhost:{PORT}")
    server.serve_forever()
