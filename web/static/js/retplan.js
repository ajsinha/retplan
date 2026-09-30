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
 *   a[data-dialog]            open the link's page in the #rp-dialog modal
 *   form[data-stepper]        one [data-step] at a time, with Back / Next
 *   input[data-reveal=<id>]   a checkbox shows #id when ticked (and disables its inputs when not)
 *   [data-strategy-job=<url>] poll a strategy search's progress; reload when it ends
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
  document.querySelectorAll('[data-print]').forEach(function (b) {
    b.addEventListener('click', function () { window.print(); });
  });
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

  // ---------- what-if sliders ----------
  (function () {
    var form = document.querySelector('form[data-whatif]');
    if (!form) { return; }
    var url = form.getAttribute('data-whatif'), saveUrl = form.getAttribute('data-whatif-save');
    var out = function (k) { return form.querySelector('[data-out="' + k + '"]'); };
    var panel = form.querySelector('.whatif-out');
    var keep = form.querySelector('[data-whatif-keep]');
    var timer = null, seq = 0, base = null;
    function label(input) {
      var o = form.querySelector('output[data-for="' + input.name + '"]');
      if (!o) { return; }
      var v = parseFloat(input.value), f = o.getAttribute('data-fmt');
      if (!v) { o.textContent = 'no change'; return; }
      var sign = v > 0 ? '+' : '−', a = Math.abs(v);
      if (f === 'years') { o.textContent = a + (a === 1 ? ' year ' : ' years ') + (v > 0 ? 'later' : 'earlier'); }
      else if (f === 'pct') { o.textContent = sign + Math.round(a * 100) + '%'; }
      else if (f === 'pctpts') { o.textContent = sign + Math.round(a * 100) + ' pts in shares'; }
      else if (f === 'feepts') { o.textContent = sign + (a * 100).toFixed(2) + ' pts a year'; }
      else if (f === 'money') { o.textContent = '+' + money(v) + ' a year'; }
    }
    function values() {
      var d = {};
      form.querySelectorAll('input[type=range]').forEach(function (i) { d[i.name] = parseFloat(i.value) || 0; });
      return d;
    }
    function show(d) {
      var a = d.adjusted, b = d.base; base = b;
      out('success').textContent = pct(a.success, 0);
      var dl = (a.success - b.success) * 100, noise = 2 * 1.96 * b.se * 100;
      var del = out('delta');
      if (Math.abs(dl) < 0.05) { del.textContent = ''; }
      else {
        del.textContent = (dl > 0 ? '+' : '−') + Math.abs(dl).toFixed(1) + ' pts' + (Math.abs(dl) < noise ? ' (within noise)' : '');
        del.className = 'delta tabular ' + (dl > 0 ? 'up' : 'down');
      }
      out('bar').style.width = (a.success * 100).toFixed(1) + '%';
      out('p50').textContent = money(a.p50);
      out('p5').textContent = money(a.p5);
      out('dep').textContent = a.depletion_age ? 'age ' + Math.round(a.depletion_age) : 'never, in the median failure';
      out('tax').textContent = money(a.tax);
      out('describe').textContent = d.describe === 'no change' ? 'Your plan as it is. Move a slider.' : 'If you ' + d.describe + '.';
      keep.disabled = d.describe === 'no change';
    }
    function go() {
      var mine = ++seq;
      panel.classList.add('busy');
      fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(values()) })
        .then(function (r) { return r.json(); })
        .then(function (d) { if (mine !== seq) { return; } panel.classList.remove('busy'); if (d.ok) { show(d); } })
        .catch(function () { panel.classList.remove('busy'); });
    }
    form.addEventListener('submit', function (ev) { ev.preventDefault(); });
    form.querySelectorAll('input[type=range]').forEach(function (i) {
      label(i);
      i.addEventListener('input', function () { label(i); clearTimeout(timer); timer = setTimeout(go, 280); });
    });
    form.querySelector('[data-whatif-reset]').addEventListener('click', function () {
      form.querySelectorAll('input[type=range]').forEach(function (i) { i.value = 0; label(i); });
      go();
    });
    keep.addEventListener('click', function () {
      keep.disabled = true;
      fetch(saveUrl, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(values()) })
        .then(function (r) { return r.json(); })
        .then(function (d) { if (d.ok) { window.location.reload(); } else { keep.disabled = false; } });
    });
    window.RetPlanWhatIf = function (adj) {
      form.querySelectorAll('input[type=range]').forEach(function (i) {
        i.value = adj[i.name] || 0; label(i);
      });
      go();
      form.scrollIntoView({ behavior: 'smooth', block: 'start' });
    };
    go();
  })();

  // ---------- the levers ----------
  (function () {
    var box = document.querySelector('[data-levers]');
    if (!box) { return; }
    var btn = box.querySelector('[data-levers-run]'), list = box.querySelector('[data-levers-list]');
    var note = box.querySelector('[data-levers-note]');
    btn.addEventListener('click', function () {
      btn.disabled = true;
      btn.innerHTML = '<i class="bi bi-arrow-repeat spin"></i> Trying each change…';
      fetch(box.getAttribute('data-levers'), { method: 'POST' })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          btn.disabled = false;
          btn.innerHTML = '<i class="bi bi-arrow-repeat"></i> Run again';
          if (!d.ok) { note.hidden = false; note.textContent = d.error || 'failed'; return; }
          var max = Math.max.apply(null, d.rows.map(function (r) { return Math.abs(r.delta); }).concat([0.01]));
          list.innerHTML = '';
          d.rows.forEach(function (r) {
            var li = document.createElement('li'), noise = Math.abs(r.delta) < d.noise;
            li.tabIndex = 0; li.setAttribute('role', 'button');
            li.title = 'Load into the sliders';
            if (noise) { li.className = 'noise'; }
            var name = document.createElement('span'); name.textContent = r.label;
            var bar = document.createElement('span'); bar.className = 'bar';
            var fill = document.createElement('span'), w = Math.abs(r.delta) / max * 50;
            fill.style.width = w + '%';
            fill.style.left = r.delta >= 0 ? '50%' : (50 - w) + '%';
            fill.style.background = r.delta >= 0 ? 'var(--rp-ok)' : 'var(--rp-bad)';
            bar.appendChild(fill);
            var v = document.createElement('span'); v.className = 'v ' + (r.delta > 0 ? 'up' : (r.delta < 0 ? 'down' : ''));
            v.textContent = (r.delta >= 0 ? '+' : '−') + Math.abs(r.delta * 100).toFixed(1);
            li.appendChild(name); li.appendChild(bar); li.appendChild(v);
            var pick = function () { if (window.RetPlanWhatIf) { window.RetPlanWhatIf(r.adjust); } };
            li.addEventListener('click', pick);
            li.addEventListener('keydown', function (ev) { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); pick(); } });
            list.appendChild(li);
          });
          list.hidden = false;
          note.hidden = false;
          note.textContent = 'Points of success probability against today\'s ' + pct(d.base.success, 0) +
            ', ' + d.trials.toLocaleString() + ' futures each on one seed. Faded rows (under ' +
            (d.noise * 100).toFixed(1) + ' pts) are within the noise. Click a row to load it into the sliders.';
        })
        .catch(function (e) { btn.disabled = false; note.hidden = false; note.textContent = String(e); });
    });
  })();

  // ---------- tick to reveal: without script every panel shows ----------
  document.querySelectorAll('input[data-reveal]').forEach(function (box) {
    var panel = document.getElementById(box.getAttribute('data-reveal'));
    if (!panel) { return; }
    function sync(focus) {
      panel.hidden = !box.checked;
      panel.querySelectorAll('input, select').forEach(function (i) { i.disabled = !box.checked; });
      if (focus && box.checked) {
        var first = panel.querySelector('input');
        panel.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        if (first) { first.focus({ preventScroll: true }); first.select(); }
      }
    }
    box.addEventListener('change', function () { sync(true); });
    sync(false);
  });

  // ---------- dialogs: a link's page in the modal, a step at a time ----------
  // Without script every [data-dialog] link is an ordinary page and every step
  // shows at once; with it, the page loads into #rp-dialog and the steps take turns.
  function initStepper(form) {
    var steps = Array.prototype.slice.call(form.querySelectorAll('[data-step]'));
    var dots = form.querySelectorAll('[data-step-dot]');
    var back = form.querySelector('[data-step-back]');
    var next = form.querySelector('[data-step-next]');
    var save = form.querySelector('[data-step-save]');
    var count = form.querySelector('[data-step-count]');
    var saveFrom = parseInt(form.getAttribute('data-save-from') || '0', 10);
    var cur = 0, last = steps.length - 1;

    function error(input, text) {
      var box = input.closest('.question');
      var slot = box && box.querySelector('[data-q-error]');
      if (slot) { slot.textContent = text || ''; slot.hidden = !text; }
      input.classList.toggle('is-invalid', !!text);
    }
    function valid(k) {
      var ok = true;
      steps[k].querySelectorAll('input, select').forEach(function (inp) {
        if (inp.disabled || inp.type === 'hidden' || inp.type === 'radio' || inp.type === 'checkbox') { return; }
        var msg = '';
        if (inp.required && inp.value.trim() === '') {
          msg = 'Please answer this one.';
        } else if (!inp.checkValidity()) {
          msg = inp.validationMessage;
        } else if (inp.hasAttribute('data-after') && inp.value !== '') {
          var other = form.querySelector('[name="' + inp.getAttribute('data-after') + '"]');
          if (other && other.value !== '' && parseFloat(inp.value) <= parseFloat(other.value)) {
            msg = 'This should be after ' + other.value + '.';
          }
        }
        error(inp, msg);
        if (msg && ok) { ok = false; inp.focus(); }
      });
      return ok;
    }
    function show(k) {
      cur = Math.max(0, Math.min(last, k));
      steps.forEach(function (st, n) { st.hidden = n !== cur; });
      dots.forEach(function (d, n) {
        d.classList.toggle('active', n === cur);
        d.classList.toggle('done', n < cur);
        var b = d.querySelector('button');
        if (b) { b.setAttribute('aria-current', n === cur ? 'step' : 'false'); }
      });
      back.hidden = cur === 0;
      next.hidden = cur === last;
      var nextOptional = steps[cur + 1] && steps[cur + 1].querySelector('.step-note');
      next.querySelector('span').textContent = nextOptional ? 'More options' : 'Next';
      next.classList.toggle('btn-primary', cur < saveFrom);
      next.classList.toggle('btn-outline-primary', cur >= saveFrom);
      save.hidden = cur < saveFrom;
      if (count) { count.textContent = steps.length > 1 ? 'Step ' + (cur + 1) + ' of ' + steps.length : ''; }
      var first = steps[cur].querySelector('input:not([type=hidden]):not([disabled]), select');
      if (first && form.closest('.modal.show')) { first.focus({ preventScroll: true }); }
    }
    back.addEventListener('click', function () { show(cur - 1); });
    next.addEventListener('click', function () { if (valid(cur)) { show(cur + 1); } });
    form.querySelectorAll('[data-step-go]').forEach(function (b) {
      b.addEventListener('click', function () {
        var k = parseInt(b.getAttribute('data-step-go'), 10);
        if (k <= cur || valid(cur)) { show(k); }
      });
    });
    // Enter moves on rather than saving half an answer.
    form.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter' && ev.target.tagName === 'INPUT' && cur < saveFrom) {
        ev.preventDefault();
        if (valid(cur)) { show(cur + 1); }
      }
    });
    form.addEventListener('submit', function (ev) {
      for (var k = 0; k < steps.length; k++) {
        if (!valid(k)) { ev.preventDefault(); show(k); valid(k); return; }
      }
      save.disabled = true;
    });
    form.querySelectorAll('input[data-life]').forEach(function (sw) {
      var target = document.getElementById(sw.getAttribute('data-life'));
      sw.addEventListener('change', function () {
        target.disabled = sw.checked;
        if (sw.checked) { error(target, ''); } else { target.focus(); }
      });
    });
    show(0);
  }
  document.querySelectorAll('form[data-stepper]').forEach(initStepper);

  (function () {
    var modalEl = document.getElementById('rp-dialog');
    if (!modalEl || !window.bootstrap) { return; }
    var body = modalEl.querySelector('[data-dialog-body]');
    var modal = window.bootstrap.Modal.getOrCreateInstance(modalEl);
    function open(href) {
      var url = href + (href.indexOf('?') < 0 ? '?' : '&') + 'partial=1';
      body.setAttribute('aria-busy', 'true');
      fetch(url, { credentials: 'same-origin', headers: { Accept: 'text/html' } })
        .then(function (r) { if (!r.ok) { throw new Error(r.status); } return r.text(); })
        .then(function (html) {
          body.innerHTML = html;
          body.removeAttribute('aria-busy');
          body.querySelectorAll('form[data-stepper]').forEach(initStepper);
          modal.show();
          var first = body.querySelector('.kind-tile, input:not([type=hidden]):not([disabled])');
          if (first && modalEl.classList.contains('show')) { first.focus(); }
        })
        .catch(function () { window.location.href = href; });
    }
    modalEl.addEventListener('shown.bs.modal', function () {
      var first = body.querySelector('.kind-tile, [data-step]:not([hidden]) input:not([type=hidden]):not([disabled]), [data-step]:not([hidden]) select');
      if (first) { first.focus(); }
    });
    document.addEventListener('click', function (ev) {
      var a = ev.target.closest('a[data-dialog]');
      if (!a || ev.ctrlKey || ev.metaKey || ev.shiftKey) { return; }
      ev.preventDefault();
      var dd = a.closest('.dropdown-menu');
      if (dd) {
        var t = dd.parentElement.querySelector('[data-bs-toggle="dropdown"]');
        if (t) { window.bootstrap.Dropdown.getOrCreateInstance(t).hide(); }
      }
      open(a.getAttribute('href'));
    });
  })();

  // ---------- a strategy search running in the background ----------
  document.querySelectorAll('[data-strategy-job]').forEach(function (box) {
    var url = box.getAttribute('data-strategy-job');
    var bar = box.querySelector('[data-strategy-bar]');
    var stage = box.querySelector('[data-strategy-stage]');
    var pctEl = box.querySelector('[data-strategy-pct]');
    function poll() {
      fetch(url, { credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d.status !== 'running') { window.location.reload(); return; }
          bar.style.width = (d.progress * 100).toFixed(1) + '%';
          stage.textContent = d.stage;
          pctEl.textContent = Math.round(d.progress * 100) + '%';
          setTimeout(poll, 1200);
        })
        .catch(function () { setTimeout(poll, 3000); });
    }
    setTimeout(poll, 800);
  });

  window.RetPlan = { money: money, pct: pct };
}());
