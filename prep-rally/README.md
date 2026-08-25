# Lumo — SAT Prep

Multiplayer SAT practice, played like a game. The UI implements the "Lumo SAT Prep" Claude Design project: navy sidebar shell, purple/white system, Inter, and the Lumo blob mascot.

**128 original Digital-SAT-style questions**, 16 in each of the 8 official College Board domains, tagged by skill and difficulty.

## Run it

Zero dependencies — just Python 3 (already on every Mac):

```bash
python3 server.py
```

Then open http://localhost:3000. To play with friends on your Wi-Fi, they visit `http://<your-local-ip>:3000` (find yours with `ipconfig getifaddr en0`).

## What's in it

| Screen | What it does |
|---|---|
| **Home** | Greeting, live analytics tiles, today's study plan, SAT countdown with an editable test date |
| **Question Bank** | All 8 domains with question counts, difficulty spread, skill lists, and your per-domain mastery. Set a difficulty and length, then drill any domain |
| **Question Rush** | Solo practice against the clock, per-subject progress, and a real session history |
| **Challenge Questions** | Hard-only mixed drill straight from the bank |
| **Play** | 1v1 ranked duels with matchmaking, plus party codes for up to 20 players |
| **Saved & Mistakes** | Every missed question saved with the full explanation and your wrong answer. Retry one or review them all; answering correctly retires it. Tracks retry accuracy and your weakest domain |
| **Study Planner** | A weekly plan generated from the domains you actually miss, with persistent checkboxes and a live sidebar badge |
| **Vocab** | 40 high-frequency SAT words as flip cards; mark words known to pull them from rotation |
| **Analytics** | Attempts, accuracy, duel wins, best streak, accuracy by domain, and the all-time high score board |

## How the game modes work

- **Solo / Rush / Bank / Challenge / Review** — single-player sessions; you control the pace.
- **Party** — host gets a 5-letter code, friends join, host advances each question. Up to 20 players.
- **1v1 Duel** — queue by subject, get matched with another waiting player, both ready up, then questions auto-advance 7 seconds after each reveal. Winner takes +24 ELO, loser −18.

Scoring is server-authoritative: base points by difficulty (500/750/1000), scaled up to 2× by answer speed, plus a streak bonus of +100 per consecutive correct answer, capped at +500.

## Project layout

| Path | What it is |
|---|---|
| `server.py` | Whole backend: HTTP + Server-Sent Events, party/duel state, matchmaking queue, scoring, high-score persistence. Python stdlib only |
| `public/` | Frontend: single-page vanilla JS app, self-hosted Inter, CSS-only mascot |
| `public/vocab.json` | Vocab flashcard deck |
| `data/questions.json` | The question bank, tagged by section, domain, skill, and difficulty |
| `data/highscores.json` | Persisted all-time top 50 scores |
| `docs/PRD.md` | Product requirements document |
| `docs/MARKET_RESEARCH.md` | Market research and competitive analysis |

## Adding questions

Append objects to `data/questions.json`:

```json
{
  "id": "alg-017",
  "section": "math",
  "domain": "Algebra",
  "skill": "Linear equations in one variable",
  "difficulty": "medium",
  "passage": "(optional — Reading & Writing questions)",
  "question": "…",
  "choices": ["A text", "B text", "C text", "D text"],
  "answer": 1,
  "explanation": "Why the answer is right."
}
```

Restart the server to pick them up. Validate a batch with:

```bash
python3 -c "import json;qs=json.load(open('data/questions.json'));assert all(len(q['choices'])==4 and 0<=q['answer']<=3 for q in qs);print(len(qs),'questions OK')"
```

⚠️ Write **original** questions only. Real SAT questions (Bluebook, the College Board question bank, OnePrep) are copyrighted — matching the style and format is fine, copying text is not. Also make sure exactly one choice is defensible; two workable options is the most common authoring bug.

## Deploying

See [DEPLOY.md](../DEPLOY.md) for the full walkthrough. Short version:

- **Render / Railway / Fly** run the game server. It holds party and duel state
  in memory, streams SSE, and runs question timers on background threads, so it
  needs one long-lived process. `render.yaml` at the repo root is ready to use.
- **Vercel** can host `public/` as a static site. Set `LUMO_API_BASE` in
  `public/config.js` to the game server URL, and list the Vercel origin in the
  server's `ALLOWED_ORIGINS` env var so CORS lets the calls through. Skip this
  and the game server serves the frontend itself, which is simpler.
- **Supabase** is for accounts. `supabase/schema.sql` creates profiles,
  attempts, and high scores with row level security. The client still needs
  wiring to it; profiles live in localStorage today.

Serverless alone cannot host the game server: stateless functions lose the
in-memory parties between requests and cannot hold SSE connections or timers.

## Running the tests

The Playwright end-to-end suite covers every screen, both multiplayer modes, the
mistake review loop, the calculator engine, and the mobile layout.

```bash
python3 -m pip install --user playwright && python3 -m playwright install chromium
```

Start the server in one terminal, then in another:

```bash
python3 tests/test_lumo.py
```

It prints PASS/FAIL per check and exits non-zero if anything fails.

## Interface

The left rail is icons only, ten destinations, uniform spacing. Hovering an
icon reveals its label; the labels stay in the DOM for screen readers and the
buttons carry `aria-label`, so the rail is readable without being cluttered.

Motion is handled by GSAP, loaded from a CDN:

- **Flip** moves the purple selection pill between nav icons. It measures the
  pill's old box, moves it into the new button, and animates the difference.
- **MorphSVG** morphs the mascot between three blob outlines, idling slowly and
  reacting when you change page.
- Icons grow slightly on hover and settle on click; page content fades up.

All of it is optional. If the GSAP bundles fail to load, CSS handles hover and
the active state and every animation helper becomes a no-op. Motion is also
skipped entirely when the OS requests reduced motion.

## The calculator

Math questions get a **real Desmos graphing calculator**, the same tool the
Digital SAT provides. It is loaded from Desmos's API on first open (the script
is about 4MB, so it is not fetched at page load) and hidden on Reading and
Writing questions, matching the real test.

The API key is supplied by the server, never hardcoded in the client. It is
resolved in this order: the `DESMOS_API_KEY` environment variable, then
`data/desmos_key.txt`, then Desmos's public demo key as a last resort. The key
file is gitignored, so a deployment's own key never lands in the repo.

```bash
echo "YOUR_KEY" > data/desmos_key.txt     # local
DESMOS_API_KEY=YOUR_KEY python3 server.py # or per-process, for hosts
```

Check which one is live with `curl -s -X POST localhost:3000/api/config -H
'Content-Type: application/json' -d '{}'`; `"desmosIsDemoKey": false` means your
own key is in use. Free keys come from https://www.desmos.com/api.

If Desmos cannot load (no connection, blocked, or slow), the panel falls back to
a built-in calculator in `public/calc.js`: its own tokenizer and shunting-yard
parser supporting arithmetic, powers, parentheses, implicit multiplication
(`3(4+1)`, `2x`), `sin/cos/tan/sqrt/abs/ln/log`, `pi`/`e`, and canvas graphing
with zoom. That fallback has no dependencies and works offline.

## Identity and sign-in

Lumo has no accounts or passwords. On first visit you pick a nickname, which is
stored in your browser's localStorage along with your ELO, mistakes, study plan,
and vocab progress. Click your name at the bottom of the nav to change it.

Consequences worth knowing:
- Progress is per-browser. A different browser or device is a different profile.
- Two tabs on the same origin share one profile, so testing multiplayer locally
  gives both players the same name (the server auto-suffixes the second one).
- Clearing site data resets progress.

Real accounts (email sign-in, progress that follows you across devices, and
server-side ELO) are the next step; they need a user table and sessions on the
server, which the current in-memory design does not have.
