/* Deployment config, loaded before app.js.

   LUMO_API_BASE: where the game server lives.
     ''  -> same origin. Correct for local dev and for a single-host deploy
             (Render/Railway/Fly), where this file needs no change.
     'https://your-server.onrender.com'
         -> use when the frontend is hosted separately, e.g. static on Vercel.
            That server must list this site in its ALLOWED_ORIGINS env var,
            otherwise the browser blocks the cross-origin calls.  */
window.LUMO_API_BASE = '';
