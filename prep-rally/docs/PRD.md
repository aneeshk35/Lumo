# PrepRally — Product Requirements Document

**Version:** 1.0 · **Date:** August 11, 2026 · **Author:** Aneesh Kolluri

## 1. Overview

PrepRally is a multiplayer SAT practice game. One person hosts a "rally," gets a short join code, and friends enter the code to play the exact same set of real-SAT-style questions at the same time — Kahoot-style, with a countdown timer, points for speed and accuracy, streak bonuses, a live leaderboard between questions, and a podium at the end.

**One-liner:** *Kahoot for the SAT — real Bluebook-style questions, played live with your friends.*

**Platforms:** Web app (primary), iOS app (secondary, later phase).

## 2. Problem

- SAT prep is lonely and boring. Students grind question banks (OnePrep, Bluebook, Khan Academy) alone, and motivation dies fast.
- Quiz-game platforms (Kahoot, Blooket, Gimkit) are fun and social, but their SAT content is user-generated trivia — short, low-quality questions that don't look or feel like the real Digital SAT.
- There is no product that combines **authentic Digital SAT question format** with **live multiplayer play**.

## 3. Target users

| Segment | Description | Why they come |
|---|---|---|
| Primary | High school juniors/seniors (US) prepping for the Digital SAT, studying with friends | Make prep social; friendly competition |
| Secondary | Study groups, clubs, tutoring classes | Teacher/tutor hosts a rally as a class activity |
| Tertiary | Solo grinders | Practice alone, chase the high-score board |

Initial go-to-market: the founder's own school — friend groups, then classes/clubs. Word of mouth via join codes is the built-in growth loop (every game invites non-users).

## 4. Core user stories

1. As a host, I can create a rally, pick section (Math / Reading & Writing / Mixed), topic domains, difficulty, and question count, and get a 5-letter join code.
2. As a player, I enter the code and a nickname and land in the lobby; I see who else is in.
3. As a player, everyone sees the **same question at the same time** with a countdown; I lock in an answer (A–D).
4. After each question, I see the correct answer, a short explanation, what I picked, and the live leaderboard.
5. At the end, I see a podium, my accuracy, and per-topic breakdown; top scores go to the all-time high-score board.
6. As a solo player, I can start a rally alone and just practice against the clock.

## 5. Functional requirements (MVP)

### Party system
- Host creates a rally → server generates a unique 5-character code (no ambiguous characters like O/0, I/1).
- Players join via code + nickname (no accounts in MVP). Nickname collisions get auto-suffixed.
- Lobby shows connected players in real time; host starts the game.
- Everyone in a rally receives **identical questions in identical order** (server picks once per rally).
- Disconnect handling: a player who drops keeps their score; the rally continues. If the host drops, the rally ends gracefully.

### Question engine
- Question bank tagged with: section, domain, skill, difficulty (easy/medium/hard).
- Domains mirror the real Digital SAT:
  - **Math:** Algebra · Advanced Math · Problem-Solving & Data Analysis · Geometry & Trigonometry
  - **Reading & Writing:** Information & Ideas · Craft & Structure · Expression of Ideas · Standard English Conventions
- Host filters by section, domain(s), and difficulty; server samples matching questions.
- Question presentation modeled on Bluebook/OnePrep: passage/stimulus above or beside the stem, four lettered choices in bordered boxes, cross-out (strike-through) tool on choices, per-question timer.
- MVP is multiple-choice only. Math grid-in (student-produced response) questions are a fast-follow.

### Game & scoring
- Timer per question (longer than trivia apps because SAT questions need real reading): easy 60s, medium 75s, hard 90s.
- Question ends when all players have answered or the timer expires.
- Scoring (server-authoritative):
  - Base points by difficulty: easy 500, medium 750, hard 1000.
  - Speed bonus: score scales from 50% → 100% of base with remaining time.
  - Streak bonus: +100 per consecutive correct answer from the 2nd onward, capped at +500.
  - Wrong/no answer: 0 points, streak resets.
- Between questions: answer reveal + explanation + leaderboard with rank deltas.
- End of game: podium (top 3), full standings, per-player accuracy and topic breakdown.
- All-time high scores persisted server-side (name, score, section, date).

### Non-functional
- Latency: question broadcast within ~250ms across a rally; server timestamps are the source of truth for the timer.
- Up to ~20 players per rally in MVP.
- Mobile-responsive web UI (players will join from phones).
- No accounts and no PII beyond a self-chosen nickname in MVP.

## 6. Out of scope for MVP (roadmap)

| Phase | Items |
|---|---|
| v1.1 | Math grid-in questions, Desmos-style calculator, larger question bank, host "kick player" |
| v1.2 | Accounts + personal progress tracking, per-skill analytics, question review history |
| v1.3 | Async challenge mode (send a code, friends play on their own time, shared leaderboard), power-ups |
| v2.0 | iOS app (wrap web app via Capacitor first; native SwiftUI later if traction), adaptive difficulty, teacher dashboards |

## 6b. Shipped in v1 (August 2026)

Beyond the original MVP scope, the built app also includes:
- **Question Bank browser** — all 8 domains with counts, difficulty spread, skill lists, and per-domain mastery; drill any domain at a chosen difficulty and length.
- **Saved & Mistakes** — missed questions persist with explanations; correct answers on review retire them. Tracks retry accuracy and weakest domain.
- **Study Planner** — a weekly plan generated from the user's actual weak domains, with persistent checkboxes and a live sidebar badge.
- **Vocab** — 40-word flip-card deck with a "known" list.
- **Challenge Questions** — hard-only mixed drill.
- **1v1 ranked duels** — subject-based matchmaking queue, VS lobby with ready-up, auto-advancing questions, client-side ELO.

## 7. Content strategy (important)

Real SAT questions are **College Board copyright** — the app must not copy questions from Bluebook, the official question bank, or OnePrep. Strategy:
- Author **original questions in the authentic Digital SAT style** (same domains, skills, difficulty calibration, question-stem phrasing conventions, four-choice format).
- Use College Board's public *Assessment Framework* domain/skill taxonomy for tagging (the taxonomy itself is fine to mirror).
- MVP ships with ~50 original questions; grow the bank continuously (target 500+ within 3 months). Question quality is the moat.

## 8. Monetization (later — do not gate the fun early)

Freemium once there's traction, never before product-market fit:
- **Free:** full multiplayer, core question bank, high scores.
- **Plus (~$4–5/mo, student-priced):** full question bank, per-skill analytics, async challenges, custom rally settings, ad-free forever.
- School/tutor licenses are the real long-term revenue path (Kahoot's actual business model).

## 9. Success metrics

- **Activation:** % of joiners who finish a full rally (target >80%).
- **Growth loop:** average players per rally (target ≥3) — every rally recruits.
- **Retention:** % of players who play a 2nd rally within 7 days (target >30%).
- **North star:** weekly questions answered in multiplayer rallies.

## 10. Technical architecture (MVP)

- **Backend:** Python 3 standard library only (zero dependencies) — HTTP server with Server-Sent Events for real-time play and JSON POST endpoints for actions. In-memory rally state, JSON-file persistence for high scores. Server-authoritative timing and scoring (clients can't cheat by editing JS).
- **Frontend:** Single-page vanilla JS/HTML/CSS (`EventSource` + `fetch`), mobile-first, Bluebook-inspired question rendering.
- **Question bank:** JSON, tagged per §5.
- **Deploy target:** any Python host (Render/Railway/Fly free tier is enough for launch).
- **iOS later:** Capacitor wrapper of the same web app — one codebase, App Store presence.

## 11. Risks

| Risk | Mitigation |
|---|---|
| Copyright (copying real SAT questions) | Original content only; mirror format, never text (§7) |
| Question quality/accuracy errors | Peer review each question; in-game "report question" button (v1.1) |
| Cheating (second device, answer sharing) | Server-side scoring, speed bonus makes lookup costly; it's a practice game, not a certification |
| Kahoot/Blooket adds SAT content | Speed + authenticity: purpose-built Bluebook-style rendering and SAT taxonomy are hard to bolt onto a trivia engine |
| Empty-room problem (multiplayer needs friends) | Solo mode works day one; async challenges (v1.3) remove the "same time" constraint |
