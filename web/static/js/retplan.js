/* RetPlan front-end behaviour.
 *
 * Small and dependency-free (Bootstrap's bundle aside). Everything a page needs to
 * *show* is rendered on the server; this file only adds interaction, so if it
 * fails to load every number is still on the page. There is no inline script
 * anywhere - pages declare behaviour with data-* attributes:
 *
 *   [data-theme-choice]       the theme menu (MAYA's four themes)
 *   .rp-nav .mega             mega-menu panels open on hover on wide screens
 *   Ctrl-K / Cmd-K            focus the search box
 *   #help-q                   live filter over the help index
 *   form[data-confirm]        confirm before submitting
 *   [data-sim]                run the plan's Monte Carlo (POST, then reload)
 *   [data-tip]                chart tooltips; .viz-hit columns add a crosshair
 *   input[data-ticker]        symbol autocomplete from /api/tickers
 *   [data-add-row=<tpl>]      append a clone of <template id=tpl> to its target
 *   [data-delete-row]         toggle a row's delete checkbox
 *   [data-toggle-show]        show the element whose id matches a select's value
 *   form[data-busy]           disable the submit button and show a spinner
 *   [data-copy]               copy the <pre> in the same <figure>
 *
 * Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
 */
(function () {
  'use strict';

  // ---------- theme (key 'light' is Crimson, kept for continuity) ----------
  var THEMES = ['light', 'dark', 'blue', 'green'];
  var THEME_KEY = 'retplan.theme';
  function applyTheme(t) {
    if (THEMES.indexOf(t) < 0) { return; }
    var root = document.documentElement;
    root.setAttribute('data-theme', t);
    root.setAttribute('data-bs-theme', t === 'dark' ? 'dark' : 'light');
    document.querySelectorAll('[data-theme-choice]').forEach(function (b) {
      b.setAttribute('aria-checked', b.getAttribute('data-theme-choice') === t ? 'true' : 'false');
    });
  }
  var stored = null;
  try { stored = localStorage.getItem(THEME_KEY); } catch (e) { /* blocked */ }
  if (stored) { applyTheme(stored); }
  document.querySelectorAll('[data-theme-choice]').forEach(function (b) {
    b.addEventListener('click', function (ev) {
      ev.preventDefault();
      var t = b.getAttribute('data-theme-choice');
      applyTheme(t);
      try { localStorage.setItem(THEME_KEY, t); } catch (e) { /* blocked */ }
    });
  });

  // ---------- mega menu: hover on wide screens, click/keyboard everywhere ----------
  var wide = window.matchMedia('(min-width: 992px)');
  document.querySelectorAll('.rp-nav .mega').forEach(function (li) {
    var toggle = li.querySelector('[data-bs-toggle="dropdown"]');
    var timer = null;
    if (!toggle || !window.bootstrap) { return; }
    var dd = window.bootstrap.Dropdown.getOrCreateInstance(toggle);
    li.addEventListener('mouseenter', function () {
      if (!wide.matches) { return; }
      clearTimeout(timer);
      document.querySelectorAll('.rp-nav .mega .dropdown-toggle.show').forEach(function (t) {
        if (t !== toggle) { window.bootstrap.Dropdown.getOrCreateInstance(t).hide(); }
      });
      timer = setTimeout(function () { dd.show(); }, 90);
    });
    li.addEventListener('mouseleave', function () {
      if (!wide.matches) { return; }
      clearTimeout(timer);
      timer = setTimeout(function () { dd.hide(); }, 180);
    });
  });

  document.addEventListener('keydown', function (ev) {
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'k') {
      var s = document.getElementById('global-search');
      if (s) { ev.preventDefault(); s.focus(); s.select(); }
    }
  });

  // ---------- help index: live search over the topic cards ----------
  (function () {
    var box = document.getElementById('help-q');
    if (!box) { return; }
    var items = [].slice.call(document.querySelectorAll('.help-item'));
    var cats = [].slice.call(document.querySelectorAll('.help-cat'));
    var none = document.getElementById('help-none');
    box.addEventListener('input', function () {
      var q = box.value.trim().toLowerCase(), any = false;
      items.forEach(function (it) {
        var hit = !q || (it.getAttribute('data-search') || '').indexOf(q) !== -1;
        it.hidden = !hit; if (hit) { any = true; }
      });
      cats.forEach(function (cat) {
        var visible = [].some.call(cat.querySelectorAll('.help-item'), function (i) { return !i.hidden; });
        cat.hidden = !visible; if (q) { cat.open = true; }
      });
      if (none) { none.hidden = any; }
    });
    document.querySelectorAll('.cat-chips .chip').forEach(function (chip) {
      chip.addEventListener('click', function () {
        var el = document.querySelector(chip.getAttribute('href')); if (el) { el.open = true; }
      });
    });
  })();

  // On-page chips from the article's own h2s, so they never disagree with it.
  document.querySelectorAll('[data-toc-for]').forEach(function (nav) {
    var body = document.getElementById(nav.getAttribute('data-toc-for'));
    if (!body) { return; }
    var heads = body.querySelectorAll('h2');
    if (heads.length < 2) { return; }
    heads.forEach(function (h, i) {
      if (!h.id) { h.id = 'sec-' + (i + 1); }
      var a = document.createElement('a');
      a.className = 'chip'; a.href = '#' + h.id; a.textContent = h.textContent;
      nav.appendChild(a);
    });
  });

  document.querySelectorAll('[data-copy]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var code = btn.closest('figure').querySelector('pre');
      if (navigator.clipboard && code) {
        navigator.clipboard.writeText(code.innerText).then(function () {
          btn.innerHTML = '<i class="bi bi-check2"></i> Copied';
          setTimeout(function () { btn.innerHTML = '<i class="bi bi-clipboard"></i> Copy'; }, 1500);
        });
      }
    });
  });

  // ---------- forms ----------
  document.querySelectorAll('form[data-confirm]').forEach(function (f) {
    f.addEventListener('submit', function (ev) {
      if (!window.confirm(f.getAttribute('data-confirm'))) { ev.preventDefault(); }
    });
  });
  document.querySelectorAll('form[data-busy]').forEach(function (f) {
    f.addEventListener('submit', function () {
      var b = f.querySelector('[type=submit]:not([formnovalidate])');
      if (!b) { return; }
      setTimeout(function () {
        b.disabled = true;
        b.innerHTML = '<i class="bi bi-arrow-repeat spin"></i> ' + (f.getAttribute('data-busy') || 'Working…');
      }, 0);
    });
  });
  document.querySelectorAll('[data-toggle-show]').forEach(function (sel) {
    var group = sel.getAttribute('data-toggle-show');
    function sync() {
      document.querySelectorAll('[data-show-group="' + group + '"]').forEach(function (el) {
        var keys = (el.getAttribute('data-show-when') || '').split(' ');
        var v = sel.type === 'checkbox' ? (sel.checked ? 'on' : 'off') : sel.value;
        el.hidden = keys.indexOf(v) < 0;
      });
    }
    sel.addEventListener('change', sync); sync();
  });
  document.querySelectorAll('[data-add-row]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var tpl = document.getElementById(btn.getAttribute('data-add-row'));
      var target = document.querySelector(btn.getAttribute('data-target'));
      if (!tpl || !target) { return; }
      var n = target.querySelectorAll('[data-row]').length + Date.now() % 100000;
      var html = tpl.innerHTML.replace(/__i__/g, String(n));
      target.insertAdjacentHTML('beforeend', html);
      bindRow(target.lastElementChild);
    });
  });
  function bindRow(root) {
    (root || document).querySelectorAll('.remove-row').forEach(function (b) {
      if (b.dataset.bound) { return; }
      b.dataset.bound = '1';
      b.addEventListener('click', function () {
        var row = b.closest('[data-row]'); if (row) { row.remove(); }
      });
    });
    (root || document).querySelectorAll('input[data-ticker]').forEach(bindTicker);
  }
  document.querySelectorAll('[data-delete-row]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var row = btn.closest('tr');
      var box = row.querySelector('input[type=checkbox][name^=delete-]');
      if (!box) { return; }
      box.checked = !box.checked;
      row.style.opacity = box.checked ? '.4' : '1';
      btn.querySelector('i').className = box.checked ? 'bi bi-arrow-counterclockwise' : 'bi bi-trash';
    });
  });

  // ---------- advanced columns (remembered) ----------
  (function () {
    var KEY = 'retplan.showAdvanced';
    var on = false;
    try { on = localStorage.getItem(KEY) === '1'; } catch (e) { /* blocked */ }
    function sync() {
      document.body.classList.toggle('show-adv', on);
      document.querySelectorAll('[data-adv-toggle]').forEach(function (b) {
        b.setAttribute('aria-pressed', on ? 'true' : 'false');
        var span = b.querySelector('span');
        if (span) { span.textContent = on ? 'Hide advanced columns' : 'Show advanced columns'; }
      });
    }
    document.querySelectorAll('[data-adv-toggle]').forEach(function (b) {
      b.addEventListener('click', function () {
        on = !on;
        try { localStorage.setItem(KEY, on ? '1' : '0'); } catch (e) { /* blocked */ }
        sync();
      });
    });
    sync();
  })();

  // ---------- number formatting ----------
  function pct(v, dp) { return (100 * v).toFixed(dp === undefined ? 1 : dp) + '%'; }
  function money(v) {
    var a = Math.abs(v), s = v < 0 ? '-' : '';
    if (a >= 1e9) { return s + (a / 1e9).toFixed(1) + 'B'; }
    if (a >= 1e6) { return s + (a / 1e6).toFixed(1) + 'M'; }
    if (a >= 1e3) { return s + Math.round(a / 1e3) + 'k'; }
    return s + Math.round(a).toLocaleString();
  }

  // ---------- the plan's simulation runner ----------
  function setStatus(text, kind) {
    var el = document.getElementById('simStatus');
    if (!el) { return; }
    el.textContent = text;
    el.className = 'pill ' + (kind || 'warn');
  }
  function run(endpoint, button) {
    var trialsEl = document.getElementById('simTrials');
    var trials = trialsEl ? parseInt(trialsEl.value, 10) : 2000;
    var buttons = document.querySelectorAll('[data-sim]');
    buttons.forEach(function (b) { b.disabled = true; });
    var label = button ? button.innerHTML : '';
    if (button) { button.innerHTML = '<i class="bi bi-arrow-repeat spin"></i> Running…'; }
    setStatus('running ' + trials.toLocaleString() + ' trials…', 'warn');
    fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ trials: trials }) })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok) { throw new Error(d.error || 'the run failed'); }
        setStatus('done: ' + d.trials.toLocaleString() + ' trials in ' + d.seconds + 's', 'ok');
        // The server holds the results; reload so every chart and table comes
        // from one consistent render rather than a patchwork.
        window.location.reload();
      })
      .catch(function (err) {
        setStatus('failed: ' + err.message, 'bad');
        buttons.forEach(function (b) { b.disabled = false; });
        if (button) { button.innerHTML = label; }
      });
  }
  document.querySelectorAll('[data-sim]').forEach(function (btn) {
    btn.addEventListener('click', function () { run(btn.getAttribute('data-sim'), btn); });
  });

  // ---------- chart tooltips and crosshair ----------
  // A tooltip enhances; it never gates a value - every chart ships a table view.
  var tip = document.createElement('div');
  tip.className = 'viz-tip';
  tip.style.position = 'fixed';
  tip.style.display = 'none';
  tip.style.whiteSpace = 'pre-line';
  document.body.appendChild(tip);
  function showTip(el, ev) {
    var lines = (el.getAttribute('data-tip') || '').split('\n');
    tip.innerHTML = '';
    var head = document.createElement('div'); head.className = 't'; head.textContent = lines[0];
    tip.appendChild(head);
    if (lines.length > 1) {
      var body = document.createElement('div'); body.textContent = lines.slice(1).join('\n');
      tip.appendChild(body);
    }
    tip.style.display = 'block';
    moveTip(ev);
    var svg = el.ownerSVGElement;
    var line = svg && svg.querySelector('.viz-hover');
    if (line && el.hasAttribute('data-x')) {
      line.setAttribute('x1', el.getAttribute('data-x'));
      line.setAttribute('x2', el.getAttribute('data-x'));
      line.setAttribute('visibility', 'visible');
    }
  }
  function moveTip(ev) {
    var w = tip.offsetWidth, x = ev.clientX + 14;
    if (x + w > window.innerWidth - 8) { x = ev.clientX - w - 14; }
    tip.style.left = x + 'px';
    tip.style.top = Math.max(8, ev.clientY - 12) + 'px';
  }
  function hideTip(el) {
    tip.style.display = 'none';
    var svg = el.ownerSVGElement;
    var line = svg && svg.querySelector('.viz-hover');
    if (line) { line.setAttribute('visibility', 'hidden'); }
  }
  document.querySelectorAll('[data-tip]').forEach(function (el) {
    el.addEventListener('mouseenter', function (ev) { showTip(el, ev); });
    el.addEventListener('mousemove', moveTip);
    el.addEventListener('mouseleave', function () { hideTip(el); });
  });

  // ---------- ticker autocomplete ----------
  function bindTicker(input) {
    if (input.dataset.bound) { return; }
    input.dataset.bound = '1';
    var box = input.closest('.ticker-box') || input.parentNode;
    var menu = document.createElement('div');
    menu.className = 'ticker-menu'; menu.hidden = true; menu.setAttribute('role', 'listbox');
    box.appendChild(menu);
    var timer = null, active = -1, results = [];
    var nameEl = input.getAttribute('data-ticker-name') ?
      document.querySelector(input.getAttribute('data-ticker-name')) : null;
    function pick(r) {
      input.value = r.symbol;
      if (nameEl) { nameEl.textContent = r.name + (r.exchange ? ' · ' + r.exchange : ''); }
      menu.hidden = true;
      input.dispatchEvent(new Event('change'));
    }
    function render() {
      menu.innerHTML = '';
      results.forEach(function (r, i) {
        var b = document.createElement('button');
        b.type = 'button'; b.setAttribute('role', 'option');
        if (i === active) { b.className = 'active'; }
        var s = document.createElement('span'); s.className = 'sym'; s.textContent = r.symbol;
        var n = document.createElement('span'); n.className = 'nm'; n.textContent = r.name;
        var t = document.createElement('span'); t.className = 'ty';
        t.textContent = [r.type, r.exchange].filter(Boolean).join(' · ');
        b.appendChild(s); b.appendChild(n); b.appendChild(t);
        b.addEventListener('mousedown', function (ev) { ev.preventDefault(); pick(r); });
        menu.appendChild(b);
      });
      menu.hidden = results.length === 0;
    }
    input.addEventListener('input', function () {
      clearTimeout(timer);
      var q = input.value.trim();
      if (q.length < 1) { results = []; render(); return; }
      timer = setTimeout(function () {
        fetch('/api/tickers?q=' + encodeURIComponent(q))
          .then(function (r) { return r.json(); })
          .then(function (d) { results = d.results || []; active = -1; render(); })
          .catch(function () { results = []; render(); });
      }, 220);
    });
    input.addEventListener('keydown', function (ev) {
      if (menu.hidden) { return; }
      if (ev.key === 'ArrowDown') { active = Math.min(results.length - 1, active + 1); render(); ev.preventDefault(); }
      else if (ev.key === 'ArrowUp') { active = Math.max(0, active - 1); render(); ev.preventDefault(); }
      else if (ev.key === 'Enter' && active >= 0) { pick(results[active]); ev.preventDefault(); }
      else if (ev.key === 'Escape') { menu.hidden = true; }
    });
    input.addEventListener('blur', function () { setTimeout(function () { menu.hidden = true; }, 120); });
  }
  bindRow(document);

  window.RetPlan = { money: money, pct: pct };
}());
