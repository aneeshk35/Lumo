#!/usr/bin/env python3
"""A tiny in-memory stand-in for Supabase's REST API, for tests only.

Lumo's server has no local storage of its own: it only speaks PostgREST to
Supabase. To run the test suite without touching a real project, start this
and point the server at it:

    python3 tests/fake_supabase.py &            # listens on 127.0.0.1:54321
    SUPABASE_URL=http://127.0.0.1:54321 SUPABASE_SERVICE_KEY=test-secret python3 server.py

It implements just what Lumo uses: eq/lt filters, select, order, limit,
insert (409 on a duplicate key), upsert, PATCH with return=representation,
and DELETE. Requests without the right apikey get 401, like the real thing.
"""

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

KEY = "test-secret"
PK = {"lumo_accounts": "username", "lumo_sessions": "token_hash", "lumo_classes": "code",
      "lumo_tutors": "player_id", "lumo_highscores": "id"}
DB = {t: [] for t in PK}
LOCK = threading.Lock()
SEQ = [0]


def matches(row, filters):
    for col, spec in filters.items():
        op, _, val = spec.partition(".")
        have = row.get(col)
        if op == "eq" and str(have) != val:
            return False
        if op == "lt" and not (have is not None and float(have) < float(val)):
            return False
    return True


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, status, data=None):
        body = json.dumps(data).encode() if data is not None else b""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_any(self):
        if self.headers.get("apikey") != KEY:
            return self.reply(401, {"message": "Invalid API key"})
        url = urlparse(self.path)
        table = url.path.rsplit("/", 1)[-1]
        if table not in DB:
            return self.reply(404, {"message": "relation does not exist"})
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        columns = q.pop("select", "*")
        order = q.pop("order", None)
        limit = q.pop("limit", None)
        on_conflict = q.pop("on_conflict", None)
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length)) if length else None
        prefer = self.headers.get("Prefer") or ""
        pk = PK[table]
        with LOCK:
            rows = DB[table]
            if self.command == "GET":
                out = [dict(r) for r in rows if matches(r, q)]
                if order:
                    col, _, direction = order.partition(".")
                    out.sort(key=lambda r: r.get(col) or 0, reverse=direction == "desc")
                if limit:
                    out = out[: int(limit)]
                if columns != "*":
                    out = [{c: r.get(c) for c in columns.split(",")} for r in out]
                return self.reply(200, out)
            if self.command == "POST":
                if pk == "id" and "id" not in body:
                    SEQ[0] += 1
                    body = dict(body, id=SEQ[0])
                existing = next((r for r in rows if r.get(on_conflict or pk) == body.get(on_conflict or pk)), None)
                if existing is not None:
                    if "merge-duplicates" in prefer:
                        existing.update(body)
                        return self.reply(201)
                    return self.reply(409, {"code": "23505", "message": "duplicate key"})
                rows.append(dict(body))
                return self.reply(201)
            if self.command == "PATCH":
                hit = [r for r in rows if matches(r, q)]
                for r in hit:
                    r.update(body)
                if "return=representation" in prefer:
                    return self.reply(200, [dict(r) for r in hit])
                return self.reply(204)
            if self.command == "DELETE":
                DB[table] = [r for r in rows if not matches(r, q)]
                return self.reply(204)
        self.reply(405)

    do_GET = do_POST = do_PATCH = do_DELETE = handle_any


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 54321
    print(f"fake Supabase on http://127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
