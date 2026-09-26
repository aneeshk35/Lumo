# Deploying Lumo

Three services, each doing the part it is good at.

| Service | Hosts | Needed for |
|---|---|---|
| **Render** (or Railway / Fly) | the Python game server | parties, duels, matchmaking, live scoring |
| **Vercel** | the static frontend | fast global delivery, a real URL |
| **Supabase** | Postgres | accounts, progress that follows you across devices |

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

## 3. Storage on Supabase (required for accounts)

Lumo saves nothing on the server's disk. Accounts, classes, tutor
applications, and high scores all live in Supabase. Until it's connected,
games work but those features show "the database isn't connected".

1. Open your project at [supabase.com](https://supabase.com).
2. **SQL Editor → New query**, paste all of `supabase/schema.sql`, **Run**.
   It creates the `lumo_*` tables with row level security on, no policies,
   and no grants for the public roles, so only the server's key can touch them.
   It's safe to run again after updates.
3. Collect two values:
   - **Project URL**: `https://<your-project-id>.supabase.co` (also under
     **Project Settings → Data API**, or the **Connect** button).
   - **Secret key**: **Project Settings → API Keys → Secret keys**, the
     `sb_secret_…` key. On older projects, use the `service_role` key under
     **Legacy API keys**.
4. On Render → your service → **Environment**, add:
   - `SUPABASE_URL` = the project URL
   - `SUPABASE_SERVICE_KEY` = the secret key

   The secret key bypasses row level security. Keep it only in Render: never
   in `config.js`, the repo, or a chat.
5. Render redeploys. The log should say `storage: Supabase` and
   `loaded … classes`, and `/api/config` returns `"accounts": true`.

Free Supabase projects pause after a week with no activity; open the dashboard
to wake one up.

## Checks after deploying

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://YOUR-SERVER/            # 200
curl -s -X POST https://YOUR-SERVER/api/config \
  -H 'Content-Type: application/json' -d '{}'   # desmosIsDemoKey: false, accounts: true
```

Then open the site, start a Question Rush, and have someone join a party code
from another device.
