"""Storage and accounts. Everything Lumo keeps lives in Supabase.

The server talks to Postgres through Supabase's REST API (PostgREST) with the
secret key from SUPABASE_URL / SUPABASE_SERVICE_KEY. Nothing is written to the
server's disk. Without those variables storage is off: games still run, but
accounts, classes, tutor applications, and high scores are unavailable.

Tables are in supabase/schema.sql. Every table has row level security on and
no policies, so Supabase's public keys can read nothing; only this server can.
"""

import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,20}$")
PASSWORD_MIN = 8
PASSWORD_MAX = 128
PROFILE_MAX_BYTES = 512 * 1024
SESSION_DAYS = 30
# OWASP's 2023 recommendation for PBKDF2-HMAC-SHA256.
PBKDF2_ROUNDS = 600_000
# Hashing is deliberately slow; cap how many run at once so a burst of sign-ins
# can't starve the game threads of CPU.
HASH_SLOTS = threading.BoundedSemaphore(2)

# Profile fields the server owns. Ratings only change through ranked results
# computed on the server, so a player can't edit their way up the ladder.
PROTECTED = ("elos", "elo", "wins", "losses")
DIFFICULTIES = ("easy", "medium", "hard")

# Limits inside a rolling 15-minute window. Per-IP limits are loose because a
# whole school on one Wi-Fi shares an IP; per-username is what stops guessing.
FAIL_WINDOW = 15 * 60
LIMITS = {
    "user": 10,     # wrong passwords for one username
    "ip": 60,       # wrong passwords from one address
    "signup": 30,   # new accounts from one address
    "signups": 300, # new accounts from everywhere (a backstop if IPs are spoofed)
}

# The most common passwords in breach lists. Anything here is refused.
COMMON_PASSWORDS = set("""
password password1 password12 password123 password1234 passw0rd p@ssw0rd p@ssword
12345678 123456789 1234567890 12341234 11111111 00000000 88888888 87654321
qwertyui qwerty12 qwerty123 qwertyuiop 1q2w3e4r 1qaz2wsx zaq12wsx asdfghjk
iloveyou iloveyou1 sunshine princess football baseball basketball superman
batman123 whatever trustno1 letmein1 welcome1 welcome123 monkey123 dragon123
starwars abcd1234 abc12345 aa123456 computer internet sat12345 satprep1
lumo1234 lumosat1 michael1 jennifer charlie1 master12 shadow12 12qwaszx
""".split())


class Conflict(Exception):
    """The saved profile moved on since this client last synced."""


class StorageError(IOError):
    """Supabase couldn't be reached or refused the request."""


# ---------- passwords and tokens ----------
def hash_password(password, rounds=PBKDF2_ROUNDS):
    salt = secrets.token_bytes(16)
    with HASH_SLOTS:
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, rounds)
    return f"pbkdf2_sha256${rounds}${salt.hex()}${digest.hex()}"


def check_password(password, stored):
    try:
        algo, rounds, salt, digest = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        with HASH_SLOTS:
            test = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds))
        return hmac.compare_digest(test.hex(), digest)
    except (ValueError, AttributeError):
        return False


def hash_rounds(stored):
    try:
        return int(stored.split("$")[1])
    except (IndexError, ValueError, AttributeError):
        return 0


# Spent on unknown usernames so a miss takes as long as a wrong password.
_DUMMY_HASH = hash_password(secrets.token_hex(8))


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def password_problem(username, password):
    if not PASSWORD_MIN <= len(password) <= PASSWORD_MAX:
        return f"Use a password of at least {PASSWORD_MIN} characters."
    lowered = password.lower()
    if username.lower() in lowered:
        return "Your password can't contain your username."
    if lowered in COMMON_PASSWORDS or len(set(password)) < 4:
        return "That password is too easy to guess. Try a short phrase instead."
    return None


# ---------- Supabase ----------
class Supabase:
    def __init__(self, url, key):
        if not url.startswith("https://") and not url.startswith("http://127.0.0.1"):
            raise ValueError("SUPABASE_URL must be an https:// URL")
        self.base = url.rstrip("/") + "/rest/v1/"
        self.headers = {"apikey": key, "Content-Type": "application/json"}
        # Legacy service_role keys are JWTs and go in Authorization too. The
        # newer sb_secret_ keys must only be sent as apikey.
        if key.startswith("eyJ"):
            self.headers["Authorization"] = f"Bearer {key}"

    def _call(self, method, table, query=None, body=None, prefer=None):
        url = self.base + table
        if query:
            url += "?" + urllib.parse.urlencode(query)
        headers = dict(self.headers)
        if prefer:
            headers["Prefer"] = prefer
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as res:
                raw = res.read()
                return res.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as err:
            return err.code, None
        except (urllib.error.URLError, OSError, ValueError) as err:
            raise StorageError(f"Supabase unreachable: {err.__class__.__name__}") from None

    @staticmethod
    def _eq(filters):
        return {k: f"eq.{v}" for k, v in (filters or {}).items()}

    def select(self, table, filters=None, columns="*", order=None, limit=None, extra=None):
        query = dict(self._eq(filters), select=columns)
        if order:
            query["order"] = order
        if limit:
            query["limit"] = str(limit)
        query.update(extra or {})
        status, rows = self._call("GET", table, query)
        if status != 200:
            raise StorageError(f"read {table} failed ({status})")
        return rows or []

    def insert(self, table, row):
        """False when the primary key already exists."""
        status, _ = self._call("POST", table, body=row, prefer="return=minimal")
        if status == 409:
            return False
        if status not in (200, 201, 204):
            raise StorageError(f"insert {table} failed ({status})")
        return True

    def upsert(self, table, row, key):
        status, _ = self._call("POST", table, {"on_conflict": key}, body=row,
                               prefer="resolution=merge-duplicates,return=minimal")
        if status not in (200, 201, 204):
            raise StorageError(f"upsert {table} failed ({status})")

    def update(self, table, filters, patch):
        """Returns the rows that matched, so a compare-and-set can tell if it landed."""
        status, rows = self._call("PATCH", table, self._eq(filters), body=patch,
                                  prefer="return=representation")
        if status != 200:
            raise StorageError(f"update {table} failed ({status})")
        return rows or []

    def delete(self, table, filters, extra=None):
        query = self._eq(filters)
        query.update(extra or {})
        status, _ = self._call("DELETE", table, query)
        if status not in (200, 204):
            raise StorageError(f"delete {table} failed ({status})")


def open_store():
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if url and key:
        return Supabase(url, key)
    return None


def iso_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------- the account service ----------
def default_ratings():
    return {"elos": {d: 1200 for d in DIFFICULTIES}, "wins": 0, "losses": 0}


def clean_ratings(raw):
    r = default_ratings()
    if isinstance(raw, dict):
        for d in DIFFICULTIES:
            try:
                r["elos"][d] = max(100, min(int((raw.get("elos") or {}).get(d, 1200)), 4000))
            except (TypeError, ValueError):
                pass
        for k in ("wins", "losses"):
            try:
                r[k] = max(0, int(raw.get(k) or 0))
            except (TypeError, ValueError):
                pass
    return r


def with_ratings(profile, ratings):
    """The profile as the client sees it: its own fields plus the server's ratings."""
    out = dict(profile or {})
    r = clean_ratings(ratings)
    out["elos"] = dict(r["elos"])
    out["elo"] = max(r["elos"].values())
    out["wins"] = r["wins"]
    out["losses"] = r["losses"]
    return out


class Accounts:
    def __init__(self, db):
        self.db = db
        self.fails = {}   # key -> [timestamps of failed attempts]
        self.lock = threading.Lock()

    @property
    def enabled(self):
        return self.db is not None

    # rate limiting
    def _limited(self, keys):
        cutoff = time.time() - FAIL_WINDOW
        with self.lock:
            for k in keys:
                self.fails[k] = [t for t in self.fails.get(k, []) if t > cutoff]
                if len(self.fails[k]) >= LIMITS[k.split(":")[0]]:
                    return True
        return False

    def _fail(self, keys):
        with self.lock:
            for k in keys:
                self.fails.setdefault(k, []).append(time.time())

    def _new_session(self, username):
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        self.db.delete("lumo_sessions", None, {"expires_at": f"lt.{now}"})
        self.db.insert("lumo_sessions", {"token_hash": token_hash(token), "username": username,
                                          "expires_at": now + SESSION_DAYS * 86400})
        return token

    def _account(self, username):
        rows = self.db.select("lumo_accounts", {"username": username},
                              "username,display,pass_hash,profile,rev,ratings")
        return rows[0] if rows else None

    @staticmethod
    def _clean_profile(profile):
        if not isinstance(profile, dict):
            return None
        profile = {k: v for k, v in profile.items() if k not in PROTECTED}
        if len(json.dumps(profile)) > PROFILE_MAX_BYTES:
            return None
        return profile

    def signup(self, username, password, profile, ip):
        username = str(username or "").strip()
        password = str(password or "")
        if not USERNAME_RE.match(username):
            return {"error": "Usernames are 3–20 letters, numbers, dots, dashes, or underscores."}
        problem = password_problem(username, password)
        if problem:
            return {"error": problem}
        budget = [f"signup:{ip}", "signups:all"] if ip else []
        if self._limited(budget):
            return {"error": "Too many new accounts from here. Try again later.", "status": 429,
                    "event": "signup rate-limited"}
        profile = self._clean_profile(profile or {})
        if profile is None:
            return {"error": "That progress is too large to save."}
        key = username.lower()
        # Ratings earned as a guest can't be verified, so every account starts
        # its ladders fresh; from here on only ranked results move them.
        created = self.db.insert("lumo_accounts", {
            "username": key, "display": username, "pass_hash": hash_password(password),
            "profile": profile, "rev": 0, "ratings": default_ratings(), "ratings_rev": 0})
        if not created:
            return {"error": "That username is taken."}
        self._fail(budget)
        return {"token": self._new_session(key), "username": username, "rev": 0,
                "profile": with_ratings(profile, None), "event": f"signup {key}"}

    def login(self, username, password, ip):
        key = str(username or "").strip().lower()
        password = str(password or "")[:PASSWORD_MAX]
        keys = [f"user:{key}"] + ([f"ip:{ip}"] if ip else [])
        if self._limited(keys):
            return {"error": "Too many attempts. Wait 15 minutes and try again.", "status": 429,
                    "event": f"login rate-limited {key}"}
        acct = self._account(key) if USERNAME_RE.match(key) else None
        ok = check_password(password, acct["pass_hash"] if acct else _DUMMY_HASH)
        if not ok or not acct:
            self._fail(keys)
            return {"error": "Wrong username or password.", "event": f"login failed {key}"}
        # Hashes from before a rounds increase are upgraded on the next sign-in.
        if hash_rounds(acct["pass_hash"]) < PBKDF2_ROUNDS:
            self.db.update("lumo_accounts", {"username": key}, {"pass_hash": hash_password(password)})
        return {"token": self._new_session(key), "username": acct["display"], "rev": acct["rev"],
                "profile": with_ratings(acct["profile"], acct.get("ratings")), "event": f"login {key}"}

    def session_user(self, token):
        if not token or not isinstance(token, str) or len(token) > 100:
            return None
        rows = self.db.select("lumo_sessions", {"token_hash": token_hash(token)}, "username,expires_at")
        if not rows or int(rows[0]["expires_at"]) < time.time():
            return None
        return rows[0]["username"]

    def me(self, token):
        key = self.session_user(token)
        acct = self._account(key) if key else None
        if not acct:
            return {"error": "Signed out.", "signedOut": True}
        return {"username": acct["display"], "rev": acct["rev"],
                "profile": with_ratings(acct["profile"], acct.get("ratings"))}

    def save(self, token, profile, rev):
        key = self.session_user(token)
        if not key:
            return {"error": "Signed out.", "signedOut": True}
        profile = self._clean_profile(profile)
        if profile is None:
            return {"error": "That progress is too large to save."}
        try:
            rev = int(rev)
        except (TypeError, ValueError):
            return {"error": "Bad revision."}
        # Compare-and-set on rev: the write only lands if nobody saved since.
        rows = self.db.update("lumo_accounts", {"username": key, "rev": rev},
                              {"profile": profile, "rev": rev + 1, "updated_at": iso_now()})
        if rows:
            return {"ok": True, "rev": rev + 1}
        acct = self._account(key)
        return {"conflict": True, "rev": acct["rev"],
                "profile": with_ratings(acct["profile"], acct.get("ratings"))}

    def logout(self, token):
        if token and isinstance(token, str) and len(token) <= 100:
            self.db.delete("lumo_sessions", {"token_hash": token_hash(token)})
        return {"ok": True}

    # ranked play
    def ladder(self, token):
        """(username, ratings) for a signed-in player joining the ranked queue."""
        key = self.session_user(token)
        acct = self._account(key) if key else None
        return (key, clean_ratings(acct.get("ratings"))) if acct else (None, None)

    def record_result(self, username, difficulty, delta, result):
        """Apply a ranked result the server computed. ratings_rev makes it a
        compare-and-set, so two games finishing together both count."""
        for _ in range(5):
            rows = self.db.select("lumo_accounts", {"username": username}, "ratings,ratings_rev")
            if not rows:
                return
            n = rows[0].get("ratings_rev") or 0
            r = clean_ratings(rows[0].get("ratings"))
            r["elos"][difficulty] = max(100, r["elos"][difficulty] + delta)
            if result == "win":
                r["wins"] += 1
            elif result == "loss":
                r["losses"] += 1
            if self.db.update("lumo_accounts", {"username": username, "ratings_rev": n},
                              {"ratings": r, "ratings_rev": n + 1}):
                return
