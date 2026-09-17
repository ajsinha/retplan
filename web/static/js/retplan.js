/* RetPlan front-end behaviour.
 *
 * Deliberately small and dependency-free: theme persistence, the simulation
 * runner, and chart hover. Everything the page needs to *show* is rendered
 * server-side, so this file only adds interaction - if it fails to load, every
 * number is still on the page.
 *
 * Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
 */
(function () {
    'use strict';

    // ---------- theme ----------
    var THEME_KEY = 'retplan.theme';
    function applyTheme(name) {
        var light = (name !== 'dark');
        document.documentElement.setAttribute('data-theme', name);
        document.documentElement.setAttribute('data-bs-theme', light ? 'light' : 'dark');
    }
    var stored = null;
    try { stored = localStorage.getItem(THEME_KEY); } catch (e) { /* private mode */ }
    applyTheme(stored || 'light');
    document.addEventListener('DOMContentLoaded', function () {
        var sel = document.getElementById('themeSelect');
        if (!sel) { return; }
        sel.value = stored || 'light';
        sel.addEventListener('change', function () {
            applyTheme(sel.value);
            try { localStorage.setItem(THEME_KEY, sel.value); } catch (e) { /* ignore */ }
        });
    });

    // ---------- number formatting ----------
    function pct(v, dp) { return (100 * v).toFixed(dp === undefined ? 1 : dp) + '%'; }
    function money(v) {
        var a = Math.abs(v), s = v < 0 ? '-' : '';
        if (a >= 1e9) { return s + (a / 1e9).toFixed(1) + 'B'; }
        if (a >= 1e6) { return s + (a / 1e6).toFixed(1) + 'M'; }
        if (a >= 1e3) { return s + Math.round(a / 1e3) + 'k'; }
        return s + Math.round(a).toLocaleString();
    }

    // ---------- simulation ----------
    function setStatus(text, kind) {
        var el = document.getElementById('simStatus');
        if (!el) { return; }
        el.textContent = text;
        el.className = 'pill ' + (kind || 'pill-warn');
    }

    function run(endpoint, button) {
        var trialsEl = document.getElementById('simTrials');
        var trials = trialsEl ? parseInt(trialsEl.value, 10) : 2000;
        var buttons = document.querySelectorAll('[data-sim]');
        buttons.forEach(function (b) { b.disabled = true; });
        var label = button ? button.textContent : 'Running';
        if (button) { button.dataset.label = label; button.textContent = 'Running...'; }
        setStatus('running ' + trials.toLocaleString() + ' trials...', 'pill-warn');

        fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ trials: trials })
        }).then(function (r) { return r.json(); }).then(function (d) {
            if (!d.ok) { throw new Error(d.error || 'the run failed'); }
            setStatus('done - ' + d.trials.toLocaleString() + ' trials in '
                + d.seconds + 's', 'pill-good');
            // The server holds the results; reload so every chart and table on
            // the page comes from one consistent render rather than a patchwork.
            window.location.reload();
        }).catch(function (err) {
            setStatus('failed: ' + err.message, 'pill-bad');
            buttons.forEach(function (b) { b.disabled = false; });
            if (button && button.dataset.label) { button.textContent = button.dataset.label; }
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('[data-sim]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                run(btn.getAttribute('data-sim'), btn);
            });
        });

        // ---------- chart hover ----------
        // A tooltip enhances; it never gates a value - each chart also ships a
        // table view below it.
        var tip = document.createElement('div');
        tip.className = 'viz-tip';
        tip.style.cssText = 'position:fixed;z-index:1090;pointer-events:none;display:none;'
            + 'background:var(--bg-card);color:var(--text-primary);border:1px solid var(--border-color);'
            + 'border-radius:7px;padding:.3rem .5rem;font-size:.76rem;box-shadow:var(--card-shadow);'
            + 'font-variant-numeric:tabular-nums;';
        document.body.appendChild(tip);
        document.querySelectorAll('[data-tip]').forEach(function (el) {
            el.addEventListener('mouseenter', function () {
                tip.textContent = el.getAttribute('data-tip');
                tip.style.display = 'block';
            });
            el.addEventListener('mousemove', function (ev) {
                tip.style.left = (ev.clientX + 14) + 'px';
                tip.style.top = (ev.clientY - 10) + 'px';
            });
            el.addEventListener('mouseleave', function () { tip.style.display = 'none'; });
        });

        // ---------- row deletion ----------
        document.querySelectorAll('[data-delete-row]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var row = btn.closest('tr');
                var box = row.querySelector('input[type=checkbox][name^=delete-]');
                if (!box) { return; }
                box.checked = !box.checked;
                row.style.opacity = box.checked ? '.4' : '1';
                btn.querySelector('i').className = box.checked
                    ? 'bi bi-arrow-counterclockwise' : 'bi bi-trash';
            });
        });
    });

    window.RetPlan = { money: money, pct: pct };
}());
