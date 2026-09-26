/* Runs inside the sandboxed Desmos frame. The parent passes the (public) API
   key in the URL hash; this frame reports back only "ready" or "failed". */
(function () {
  function tell(type) { parent.postMessage({ lumoDesmos: type }, '*'); }
  // A sandboxed frame has no storage, and Desmos reads localStorage on start.
  // Give it a throwaway in-memory one so it doesn't throw.
  try { window.localStorage; } catch (e) {
    var mem = {};
    var shim = {
      getItem: function (k) { return Object.prototype.hasOwnProperty.call(mem, k) ? mem[k] : null; },
      setItem: function (k, v) { mem[k] = String(v); },
      removeItem: function (k) { delete mem[k]; },
      clear: function () { mem = {}; },
      key: function (i) { return Object.keys(mem)[i] || null; },
      get length() { return Object.keys(mem).length; },
    };
    try {
      Object.defineProperty(window, 'localStorage', { value: shim, configurable: true });
      Object.defineProperty(window, 'sessionStorage', { value: shim, configurable: true });
    } catch (e2) { /* Desmos copes without it, just noisily */ }
  }
  var key = (location.hash.match(/key=([A-Za-z0-9]+)/) || [])[1];
  if (!key) return tell('failed');
  var script = document.createElement('script');
  script.src = 'https://www.desmos.com/api/v1.11/calculator.js?apiKey=' + key;
  script.onerror = function () { tell('failed'); };
  script.onload = function () {
    try {
      var calc = Desmos.GraphingCalculator(document.getElementById('calc'), {
        keypad: true, expressions: true, settingsMenu: false,
        zoomButtons: true, border: false, lockViewport: false,
        expressionsCollapsed: false,
      });
      window.addEventListener('resize', function () { calc.resize(); });
      tell('ready');
    } catch (e) {
      tell('failed');
    }
  };
  document.head.appendChild(script);
})();
