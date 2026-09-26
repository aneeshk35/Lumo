/* Applied before the first paint so a dark viewer never sees a white flash. */
try {
  var t = localStorage.getItem('lumo-theme');
  if (t === 'dark' || t === 'light') document.documentElement.dataset.theme = t;
} catch (e) { /* private mode: fall back to the OS preference */ }
