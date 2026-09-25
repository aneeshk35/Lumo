/* Deployment config, loaded before app.js.

   LUMO_API_BASE: where the game server lives.
     ''  -> same origin. Correct for local dev and for a single-host deploy
             (Render/Railway/Fly), where this file needs no change.
     'https://your-server.onrender.com'
         -> use when the frontend is hosted separately, e.g. static on Vercel.
            That server must list this site in its ALLOWED_ORIGINS env var,
            otherwise the browser blocks the cross-origin calls.  */
// The static copy on Vercel talks to the Render server; anywhere else (local
// dev, or the Render server serving the page itself) the API is same-origin.
window.LUMO_API_BASE = location.hostname.endsWith('.vercel.app') ? 'https://lumo-3vut.onrender.com' : '';
