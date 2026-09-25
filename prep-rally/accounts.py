"""Accounts: username + password, with each player's progress saved server-side.

Storage is pluggable and standard-library only:
- SupabaseStore talks to Postgres through Supabase's REST API when
  SUPABASE_URL and SUPABASE_SERVICE_KEY are set. Use this on Render, whose free
  disk is wiped on every restart.
- SqliteStore keeps everything in data/lumo.db. Used for local development and
  tests, or on a host with a persistent disk.

The table layout for both lives in supabase/schema.sql.
"""

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,20}$")
PASSWORD_MIN = 8
PASSWORD_MAX = 128
PROFILE_MAX_BYTES = 512 * 1024
SESSION_DAYS = 60
PBKDF2_ROUNDS = 200_000

# Limits inside a rolling 15-minute window. Per-IP limits are loose because a
# whole school on one Wi-Fi shares an IP; per-username is what stops guessing.
FAIL_WINDOW = 15 * 60
LIMITS = {
    "user": 10,     # wrong passwords for one username
    "ip": 60,       # wrong passwords from one address
    "signup": 30,   # new accounts from one address
    "signups": 300, # new accounts from everywhere (a backstop if IPs are spoofed)
}


class Conflict(Exception):
    """The saved profile moved on since this client last synced."""


# ---------- passwords and tokens ----------
def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt.hex()}${digest.hex()}"


def check_password(password, stored):
    try:
        algo, rounds, salt, digest = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        test = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds))
        return hmac.compare_digest(test.hex(), digest)
    except (ValueError, AttributeError):
        return False


# Spent on unknown usernames so a miss takes as long as a wrong password.
_DUMMY_HASH = hash_password(secrets.token_hex(8))


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


# ---------- storage backends ----------
class SqliteStore:
    durable = True
    kind = "sqlite"

    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with self._db() as db:
            db.executescript("""
                create table if not exists lumo_accounts (
                  username text primary key, display text not null,
                  pass_hash text not null, profile text not null default '{}',
                  rev integer not null default 0,
                  created_at real not null, updated_at real not null);
                create table if not exists lumo_sessions (
                  token_hash text primary key, username text not null,
                  expires_at real not null);
            """)

    def _db(self):
        return sqlite3.connect(self.path, timeout=10)

    def get_account(self, username):
        with self.lock, self._db() as db:
            row = db.execute("select username, display, pass_hash, profile, rev from lumo_accounts"
                             " where username = ?", (username,)).fetchone()
        if not row:
            return None
        return {"username": row[0], "display": row[1], "pass_hash": row[2],
                "profile": json.loads(row[3] or "{}"), "rev": row[4]}

    def create_account(self, username, display, pass_hash, profile):
        now = time.time()
        try:
            with self.lock, self._db() as db:
                db.execute("insert into lumo_accounts values (?, ?, ?, ?, 0, ?, ?)",
                           (username, display, pass_hash, json.dumps(profile), now, now))
            return True
        except sqlite3.IntegrityError:
            return False

    def save_profile(self, username, profile, rev):
        with self.lock, self._db() as db:
            cur = db.execute("update lumo_accounts set profile = ?, rev = rev + 1, updated_at = ?"
                             " where username = ? and rev = ?",
                             (json.dumps(profile), time.time(), username, rev))
            if cur.rowcount != 1:
                raise Conflict()
        return rev + 1

    def create_session(self, thash, username, expires_at):
        with self.lock, self._db() as db:
            db.execute("delete from lumo_sessions where expires_at < ?", (time.time(),))
            db.execute("insert into lumo_sessions values (?, ?, ?)", (thash, username, expires_at))

    def get_session(self, thash):
        with self.lock, self._db() as db:
            row = db.execute("select username, expires_at from lumo_sessions where token_hash = ?",
                             (thash,)).fetchone()
        return {"username": row[0], "expires_at": row[1]} if row else None

    def delete_session(self, thash):
        with self.lock, self._db() as db:
            db.execute("delete from lumo_sessions where token_hash = ?", (thash,))


class SupabaseStore:
    """Postgres through PostgREST. The service key stays on the server; the
    tables have row level security on and no policies, so the public anon key
    can't read them."""
    durable = True
    kind = "supabase"

    def __init__(self, url, key):
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

    def get_account(self, username):
        status, rows = self._call("GET", "lumo_accounts", {
            "username": f"eq.{username}", "select": "username,display,pass_hash,profile,rev"})
        if status != 200:
            raise IOError(f"Supabase read failed ({status})")
        return rows[0] if rows else None

    def create_account(self, username, display, pass_hash, profile):
        status, _ = self._call("POST", "lumo_accounts", body={
            "username": username, "display": display, "pass_hash": pass_hash,
            "profile": profile, "rev": 0}, prefer="return=minimal")
        if status == 409:
            return False
        if status not in (200, 201, 204):
            raise IOError(f"Supabase insert failed ({status})")
        return True

    def save_profile(self, username, profile, rev):
        # Compare-and-set on rev: the update only lands if nobody saved since.
        status, rows = self._call("PATCH", "lumo_accounts",
                                  {"username": f"eq.{username}", "rev": f"eq.{rev}"},
                                  body={"profile": profile, "rev": rev + 1,
                                        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                                  prefer="return=representation")
        if status != 200:
            raise IOError(f"Supabase update failed ({status})")
        if not rows:
            raise Conflict()
        return rev + 1

    def create_session(self, thash, username, expires_at):
        self._call("DELETE", "lumo_sessions", {"expires_at": f"lt.{int(time.time())}"})
        status, _ = self._call("POST", "lumo_sessions", body={
            "token_hash": thash, "username": username, "expires_at": int(expires_at)},
            prefer="return=minimal")
        if status not in (200, 201, 204):
            raise IOError(f"Supabase session insert failed ({status})")

    def get_session(self, thash):
        status, rows = self._call("GET", "lumo_sessions", {
            "token_hash": f"eq.{thash}", "select": "username,expires_at"})
        if status != 200:
            raise IOError(f"Supabase read failed ({status})")
        return rows[0] if rows else None

    def delete_session(self, thash):
        self._call("DELETE", "lumo_sessions", {"token_hash": f"eq.{thash}"})


def open_store(data_dir):
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if url and key:
        return SupabaseStore(url, key)
    store = SqliteStore(os.path.join(data_dir, "lumo.db"))
    # Render's free disk resets on every restart and deploy, so a local
    # database there loses accounts. The client warns players when this is off.
    store.durable = not os.environ.get("RENDER")
    return store


# ---------- the account service ----------
class Accounts:
    def __init__(self, store):
        self.store = store
        self.fails = {}   # key -> [timestamps of failed sign-ins]
        self.lock = threading.Lock()

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
        self.store.create_session(token_hash(token), username, time.time() + SESSION_DAYS * 86400)
        return token

    @staticmethod
    def _clean_profile(profile):
        if not isinstance(profile, dict):
            return None
        if len(json.dumps(profile)) > PROFILE_MAX_BYTES:
            return None
        return profile

    def signup(self, username, password, profile, ip):
        username = str(username or "").strip()
        password = str(password or "")
        if not USERNAME_RE.match(username):
            return {"error": "Usernames are 3–20 letters, numbers, dots, dashes, or underscores."}
        if not PASSWORD_MIN <= len(password) <= PASSWORD_MAX:
            return {"error": f"Use a password of at least {PASSWORD_MIN} characters."}
        if password.lower() == username.lower():
            return {"error": "Your password can't be your username."}
        budget = [f"signup:{ip}", "signups:all"]
        if ip and self._limited(budget):
            return {"error": "Too many new accounts from here. Try again later.", "status": 429}
        profile = self._clean_profile(profile or {})
        if profile is None:
            return {"error": "That progress is too large to save."}
        key = username.lower()
        if not self.store.create_account(key, username, hash_password(password), profile):
            return {"error": "That username is taken."}
        # Signups count against the same budget so one browser can't mint hundreds.
        if ip:
            self._fail(budget)
        return {"token": self._new_session(key), "username": username, "profile": profile, "rev": 0}

    def login(self, username, password, ip):
        key = str(username or "").strip().lower()
        password = str(password or "")
        keys = [f"user:{key}"] + ([f"ip:{ip}"] if ip else [])
        if self._limited(keys):
            return {"error": "Too many attempts. Wait 15 minutes and try again.", "status": 429}
        acct = self.store.get_account(key) if USERNAME_RE.match(key) else None
        if not check_password(password, acct["pass_hash"] if acct else _DUMMY_HASH) or not acct:
            self._fail(keys)
            return {"error": "Wrong username or password."}
        return {"token": self._new_session(key), "username": acct["display"],
                "profile": acct["profile"], "rev": acct["rev"]}

    def _session_user(self, token):
        if not token or not isinstance(token, str) or len(token) > 100:
            return None
        row = self.store.get_session(token_hash(token))
        if not row or float(row["expires_at"]) < time.time():
            return None
        return row["username"]

    def me(self, token):
        key = self._session_user(token)
        acct = self.store.get_account(key) if key else None
        if not acct:
            return {"error": "Signed out.", "signedOut": True}
        return {"username": acct["display"], "profile": acct["profile"], "rev": acct["rev"]}

    def save(self, token, profile, rev):
        key = self._session_user(token)
        if not key:
            return {"error": "Signed out.", "signedOut": True}
        profile = self._clean_profile(profile)
        if profile is None:
            return {"error": "That progress is too large to save."}
        try:
            rev = int(rev)
        except (TypeError, ValueError):
            return {"error": "Bad revision."}
        try:
            return {"ok": True, "rev": self.store.save_profile(key, profile, rev)}
        except Conflict:
            acct = self.store.get_account(key)
            return {"conflict": True, "profile": acct["profile"], "rev": acct["rev"]}

    def logout(self, token):
        if token and isinstance(token, str):
            self.store.delete_session(token_hash(token))
        return {"ok": True}
