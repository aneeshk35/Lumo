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

Any host that runs Python works (Render / Railway / Fly.io free tiers). Set the `PORT` env var if the host requires it. Rally state lives in memory and high scores in a JSON file, which is right for one small instance; move to Redis or SQLite before scaling past that. Player profiles (name, ELO, mistakes, plan, vocab progress) live in each browser's localStorage — accounts are the next step if you want progress to follow users across devices.
