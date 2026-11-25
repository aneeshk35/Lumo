# Lumo

**SAT practice you play with friends.** Lumo turns Digital SAT prep into a
multiplayer game: ranked 1v1 duels, party rooms for up to 20 players, and solo
drills against the clock, all built on a bank of more than 3,000 original
SAT-style questions.

**Try it:** [lumosat.vercel.app](https://lumosat.vercel.app)

## Why I built it

SAT prep is usually a solo grind through question banks, and motivation drops
off fast. Quiz games like Kahoot are fun, but their SAT content doesn't look or
feel like the real test. Lumo puts both together: questions written in the
Digital SAT format, played live against people you know.

## Features

- **Ranked duels and 2v2.** Queue by subject and difficulty, get matched with
  someone near your rating, and climb a separate Elo ladder for each
  difficulty. If no one else is waiting, a labeled bot that plays like someone
  at your rating takes the seat.
- **Party mode.** The host gets a 5-letter code, up to 20 friends join, and
  everyone answers the same question at the same time with a live leaderboard.
- **Solo practice.** Question Rush, a hard-only Challenge mode, and a Question
  Bank you can drill by domain, difficulty, and length.
- **Mistake review.** Every missed question is saved with its explanation and
  the answer you picked. Get it right on a retry and it leaves the list.
- **Masterclass lessons.** 27 short lessons covering the official SAT domains.
  Each ends with a worked example to answer and a drill.
- **Ask Lumo.** A study coach that answers only from Lumo's own lessons,
  questions, vocab, and your stats, so it can't make anything up.
- **Classes and friends.** Teachers can run a class with a live roster and
  assignments. Friend codes show who's online and let you send duel invites.
- **The real calculator.** Math questions open the Desmos graphing calculator,
  the same one the Digital SAT uses, with a built-in offline calculator as a
  fallback.
- **Study tools.** A weekly study planner built from the domains you miss,
  vocab flashcards, an SAT countdown, and analytics by domain.
- **Light and dark mode**, and it works on phones.

## The question bank

All questions are original. None are copied from the College Board, Bluebook,
or other prep sites. They cover all 8 official Digital SAT domains:

| Section | Domains | Questions |
|---|---|---|
| Math | Algebra · Advanced Math · Problem-Solving & Data Analysis · Geometry & Trigonometry | ~1,700 |
| Reading & Writing | Information & Ideas · Craft & Structure · Expression of Ideas · Standard English Conventions | ~1,300 |

Each question is tagged by section, domain, skill, and difficulty, and comes
with an explanation.

## How it's built

| Part | What it uses |
|---|---|
| Game server | Python standard library only (no dependencies). HTTP plus Server-Sent Events for live games, with in-memory parties, matchmaking, and server-side scoring |
| Frontend | A single-page app in plain JavaScript, HTML, and CSS. No framework, no build step |
| Storage | Supabase (Postgres) for accounts, classes, and friends |
| Hosting | Render for the game server, Vercel for the frontend |

Scoring and ratings happen on the server, so they can't be edited from the
browser. Passwords are hashed with PBKDF2. The site uses a strict Content
Security Policy and runs Desmos in a sandboxed frame. See
[SECURITY.md](SECURITY.md) for details.

## Run it locally

You only need Python 3.

```bash
git clone https://github.com/aneeshk35/Lumo.git
cd Lumo/prep-rally
python3 server.py
```

Then open http://localhost:3000. Friends on the same Wi-Fi can join at
`http://<your-local-ip>:3000`.

Games work right away. Accounts, classes, and saved friends need a Supabase
project. [DEPLOY.md](DEPLOY.md) explains how to connect one and deploy the
whole app.

## Project layout

```
prep-rally/
  server.py      game server: parties, duels, matchmaking, scoring
  accounts.py    sign-up, sign-in, sessions
  bots.py        bots that fill empty duel seats
  public/        the frontend
  data/          the question bank
  tools/         scripts that generate and check questions
  tests/         end-to-end, stress, and UI audit tests
supabase/        database schema
```

For details on game modes, scoring, adding questions, and running the tests,
see [prep-rally/README.md](prep-rally/README.md).
