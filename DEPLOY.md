# Deploying Lumo

Three services, each doing the part it is good at.

| Service | Hosts | Needed for |
|---|---|---|
| **Render** (or Railway / Fly) | the Python game server | parties, duels, matchmaking, live scoring |
| **Vercel** | the static frontend | fast global delivery, a real URL |
| **Supabase** | Postgres + Auth | accounts, progress that follows you across devices |

You can stop after Render and have a working, shareable app. Vercel and
Supabase are additive.

## Why the game server is not on Vercel

`server.py` keeps parties, duels, and the matchmaking queue in memory, streams
Server-Sent Events to every player in a party, and runs background timers for
question clocks. Serverless functions are stateless, short-lived, and cannot
keep those connections or threads, so multiplayer would break. Render runs one
long-lived process, which is exactly what this design needs.

Keep it to **one instance**. Scaling out would split the in-memory state and
players would land on different copies of the same party.

## 1. Game server on Render

1. Sign in at [render.com](https://render.com) with GitHub.
2. **New → Blueprint**, pick the `Lumo` repo. It reads `render.yaml`.
3. Set the env vars it asks for:
   - `DESMOS_API_KEY` — your key from https://www.desmos.com/api
   - `ALLOWED_ORIGINS` — leave empty for now; fill in after step 2.
4. Deploy. You get a URL like `https://lumo.onrender.com`.

The free tier sleeps when idle, so the first request after a quiet spell takes
a few seconds to wake.

## 2. Frontend on Vercel (optional)

1. Sign in at [vercel.com](https://vercel.com) with GitHub and import the repo.
2. It reads `vercel.json` and publishes `prep-rally/public` as a static site.
3. Point the frontend at the game server: edit `prep-rally/public/config.js`

   ```js
   window.LUMO_API_BASE = 'https://lumo.onrender.com';
   ```

4. Back on Render, set `ALLOWED_ORIGINS` to your Vercel URL, no trailing slash:

   ```
   https://lumo.vercel.app
   ```

   The server only sends CORS headers for origins on that list, so this step is
   what makes the split deploy work.

If you skip Vercel, leave `config.js` as `''` and Render serves the frontend
itself. Simpler, one less moving part, and no CORS at all.

## 3. Accounts on Supabase (optional)

1. Create a project at [supabase.com](https://supabase.com).
2. Apply `supabase/schema.sql` in the SQL editor. It creates `profiles`,
   `attempts`, and `high_scores`, turns on row level security so players can
   only touch their own rows, and adds a trigger that creates a profile on
   signup.
3. Wire the client to it. This part is not written yet: today the profile lives
   in `localStorage` (see *Identity and sign-in* in the README). The schema is
   the target to migrate onto.

Scope the Supabase MCP server to this project once it exists by adding
`&project_ref=<id>` to the URL in `.mcp.json`, and add `&read_only=true`
whenever schema changes are not needed.

## Checks after deploying

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://YOUR-SERVER/            # 200
curl -s -X POST https://YOUR-SERVER/api/config \
  -H 'Content-Type: application/json' -d '{}'                           # desmosIsDemoKey: false
```

Then open the site, start a Question Rush, and have someone join a party code
from another device.
