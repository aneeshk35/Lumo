# Lumo security

Lumo follows the [OWASP Top 10 (2021)](https://owasp.org/Top10/). This page
says how each risk is handled and lists the rules every change has to keep.

## Rules for every change

1. **All saved data goes to Supabase. Nothing is stored on the server's disk.**
   The server writes no files; without `SUPABASE_URL` and
   `SUPABASE_SERVICE_KEY`, accounts, classes, tutoring, and high scores are off.
   Live game state (parties, the queue, presence) stays in memory only.
2. **Every new Supabase table gets row level security with no policies**, plus
   `revoke all ... from anon, authenticated`. Only the server's secret key
   touches data.
3. **The secret key lives only in Render's environment.** Never in
   `public/`, `config.js`, the repo, or chat.
4. **Never put user-controlled text into HTML without `esc()`**, and never add
   inline `<script>`, `on…=` attributes, `eval`, or `new Function`. The
   Content Security Policy blocks them.
5. **Validate every request field on the server**: `clip()` for strings,
   `clean_int()` for numbers, `sanitize_name()` for names, `player_id()` for
   player keys. Never trust a number, rating, or score from the browser.
6. **Anything that needs `eval` or looser rules goes in its own sandboxed
   frame** (`sandbox="allow-scripts"`, never `allow-same-origin`), like
   `desmos-frame.html`.
7. **Pin third-party scripts to an exact version with an `integrity` hash**
   (see the GSAP tags in `index.html`), and add any new host to the CSP in
   `server.py` and `vercel.json`.
8. **Never log passwords, tokens, or player keys.** Use `log()` for security
   events.
9. **Run `tests/test_lumo.py` and `tests/audit_ui.py` before pushing.** The
   security group checks headers, the CSP, input handling, and access rules.

## OWASP Top 10

| Risk | How Lumo handles it |
|---|---|
| **A01 Broken access control** | Account data is reached only through a session token, checked on every call. Supabase tables have RLS on with no policies, and public roles have no grants. Class actions check teacher or student membership. Host-only party actions check the host. Ratings are server-owned. Static files are served only from `public/`, with `..`, symlinks, and dotfiles refused. |
| **A02 Cryptographic failures** | Passwords use PBKDF2-HMAC-SHA256 with 600,000 rounds and a random salt, and older hashes upgrade on sign-in. Session tokens are 256-bit random, and only their SHA-256 is stored. Player keys are stored as hashes. HTTPS runs everywhere, with HSTS. |
| **A03 Injection** | Every piece of dynamic HTML escapes player text. A strict CSP blocks inline and injected scripts and `eval`. Desmos needs `eval`, so it runs in `desmos-frame.html`, a sandboxed frame with an opaque origin and its own policy that can't reach the app's storage or page. Names are stripped of markup server-side. Supabase queries go through PostgREST with URL-encoded, validated values, so no SQL is built from input. |
| **A04 Insecure design** | Elo, wins, and losses are computed on the server from ranked results, and edits made in the browser are ignored. Stale devices can't overwrite newer progress (revision check). Saves are capped at 512 KB. Parties and the queue are capped. |
| **A05 Security misconfiguration** | Security headers: CSP, `X-Frame-Options: DENY`, `nosniff`, `no-referrer`, COOP, and Permissions-Policy. No server version banner. CORS is an explicit allowlist. API responses are `no-store`. Errors never include stack traces. |
| **A06 Vulnerable components** | The server uses only the Python standard library. Front-end libraries are pinned to exact versions with SRI hashes. |
| **A07 Identification and authentication failures** | Passwords must be 8+ characters, not a common password, and must not contain the username. Wrong-password lockout is per username (10 per 15 minutes) and per IP (60). Sign-ups are limited per IP and globally. A miss costs the same time for unknown usernames. Sessions expire after 30 days and are deleted on sign-out. |
| **A08 Software and data integrity failures** | SRI covers CDN scripts. The server decides ranked results. Every JSON body is checked for type, size, and shape. |
| **A09 Logging and monitoring failures** | Sign-ups, sign-ins, failures, lockouts, rate limiting, and storage errors are logged with timestamps to Render's logs, never with secrets. |
| **A10 Server-side request forgery** | The server makes outbound requests only to `SUPABASE_URL`, which comes from the environment and must be `https://`. No request goes to a URL taken from user input. |

## Known limits

- Guests keep progress in their own browser. That data is theirs to edit, so
  guest ratings are unverified; ranked ratings for accounts are not.
- The sign-in token lives in the browser's localStorage. The CSP and escaping
  are what keep scripts from reading it. HttpOnly cookies aren't used because
  the site (Vercel) and the server (Render) are on different domains, and
  browsers block those cookies.
- There's no password reset, since accounts have no email.
- The 60-per-IP and 30-sign-up limits are loose on purpose, because a school
  shares one IP.
