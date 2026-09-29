/* Applied in <head>, before the first paint, so a stored theme never flashes the
 * default first. Everything else lives in retplan.js at the end of <body>. */
(function () {
  try {
    var t = localStorage.getItem('retplan.theme');
    if (['light', 'dark', 'blue', 'green'].indexOf(t) >= 0) {
      document.documentElement.setAttribute('data-theme', t);
      document.documentElement.setAttribute('data-bs-theme', t === 'dark' ? 'dark' : 'light');
    }
  } catch (e) { /* storage blocked: the OS preference decides */ }
}());
