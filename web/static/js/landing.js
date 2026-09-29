/*
 * landing.js - the three drawn figures on the landing page, after MAYA's.
 *
 *   #lpFutures   (hero)  the question - will the money last? - becomes a thousand
 *                        futures: they fan out from today, the ones that run dry turn
 *                        red, the middle 80% becomes a band, and the answer is a number
 *                        with its error bar, not a promise.
 *   #lpSequence          sequence risk: the same thirty yearly returns, in opposite
 *                        order, for two retirees drawing the same income. Same average,
 *                        different life.
 *   #lpLedger            the audit writing itself: each year's balance rolls forward
 *                        from the last, and is checked.
 *
 * Every path is computed here, from a seeded generator, with the same arithmetic the
 * engine uses - so the pictures are small, honest simulations, not illustrations.
 * Each figure plays once when it first comes into view and rests on its last frame; a
 * button replays it. Nothing loops, so the page stays a page. A reader who has asked
 * for less motion gets the last frame, drawn once. Colours come from the theme tokens
 * and follow a theme change.
 *
 * Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
 */
(function () {
  'use strict';

  var W = 800, DURATION = 9000, REST = 0.96;
  var SANS = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
  var MONO = 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function clamp(x) { return Math.min(1, Math.max(0, x)); }
  function seg(t, a, b) { return clamp((t - a) / (b - a)); }
  function ease(x) { return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2; }
  function lerp(a, b, u) { return a + (b - a) * u; }
  function money(v) {
    var a = Math.abs(v);
    if (a >= 1e6) { return (v / 1e6).toFixed(2).replace(/\.?0+$/, '') + 'M'; }
    if (a >= 1e3) { return Math.round(v / 1e3) + 'k'; }
    return String(Math.round(v));
  }

  var C = {};
  function readColours() {
    var css = getComputedStyle(document.documentElement);
    function tok(n, d) { return (css.getPropertyValue(n) || d).trim() || d; }
    C = {
      ink: tok('--rp-ink', '#1A1A1A'), slate: tok('--rp-slate', '#6B7480'),
      accent: tok('--rp-crimson', '#A51C30'), tint: tok('--rp-crimson-tint', '#FBEEF0'),
      ok: tok('--rp-ok', '#1E6B3A'), bad: tok('--rp-bad', '#8A1626'),
      line: tok('--rp-border', '#E3DED7'), card: tok('--rp-surface', '#FFFFFF'),
      indigo: tok('--rp-indigo', '#293352'), band: tok('--viz-seq-250', '#86b6ef'),
      band2: tok('--viz-seq-450', '#2a78d6'), median: tok('--viz-seq-650', '#104281')
    };
  }

  function text(c, s, x, y, font, colour, align) {
    c.font = font; c.fillStyle = colour; c.textAlign = align || 'left'; c.fillText(s, x, y);
  }
  function line(c, x0, y0, x1, y1) { c.beginPath(); c.moveTo(x0, y0); c.lineTo(x1, y1); c.stroke(); }
  function box(c, x, y, w, h, r) {
    c.beginPath(); c.moveTo(x + r, y); c.arcTo(x + w, y, x + w, y + h, r); c.arcTo(x + w, y + h, x, y + h, r);
    c.arcTo(x, y + h, x, y, r); c.arcTo(x, y, x + w, y, r); c.closePath();
  }

  /* -- a seeded generator, so every visitor sees the same futures --------------------- */
  function rng(seed) {
    var s = seed >>> 0;
    return function () {                                  // mulberry32
      s = (s + 0x6D2B79F5) >>> 0;
      var t = s;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function normal(r) {
    var u = Math.max(1e-12, r()), v = r();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  }

  /* -- the hero: a thousand futures ---------------------------------------------------- */
  // A 65-year-old with 1.0M, drawing 42k a year in today's money, 60/40 mix:
  // real return 4% arithmetic, 11% volatility, lognormal. Thirty years, to 95.
  var YEARS = 30, START = 1.0e6, DRAW = 42000, SHOWN = 48, TRIALS = 1000;
  var FUT = (function () {
    var r = rng(20260929), paths = [], i, k, mu = 0.04, sig = 0.11;
    var s2 = Math.log(1 + sig * sig / ((1 + mu) * (1 + mu))), m = Math.log(1 + mu) - 0.5 * s2;
    for (i = 0; i < TRIALS; i++) {
      var v = START, p = [v], dead = -1;
      for (k = 1; k <= YEARS; k++) {
        v = Math.max(0, v - DRAW);
        v *= Math.exp(m + Math.sqrt(s2) * normal(r));
        if (v <= 0 && dead < 0) { dead = k; }
        p.push(v);
      }
      paths.push({ v: p, dead: dead });
    }
    var bands = [];
    for (k = 0; k <= YEARS; k++) {
      var col = paths.map(function (q) { return q.v[k]; }).sort(function (a, b) { return a - b; });
      bands.push([col[Math.floor(0.1 * TRIALS)], col[Math.floor(0.5 * TRIALS)], col[Math.floor(0.9 * TRIALS)]]);
    }
    var ok = paths.filter(function (q) { return q.dead < 0; }).length / TRIALS;
    return { paths: paths.slice(0, SHOWN), bands: bands, ok: ok,
             se: Math.sqrt(ok * (1 - ok) / TRIALS) };
  }());

  function futures(c, t) {
    var x0 = 70, x1 = 740, y0 = 250, y1 = 40, top = 3.2e6;
    function X(k) { return x0 + (x1 - x0) * k / YEARS; }
    function Y(v) { return y0 - (y0 - y1) * Math.min(v, top) / top; }
    // axes
    c.globalAlpha = seg(t, 0, 0.06);
    c.strokeStyle = C.line; c.lineWidth = 1;
    [0, 1e6, 2e6, 3e6].forEach(function (v) {
      line(c, x0, Y(v), x1, Y(v));
      text(c, money(v), x0 - 8, Y(v) + 4, '11px ' + SANS, C.slate, 'right');
    });
    [0, 10, 20, 30].forEach(function (k) {
      text(c, 'age ' + (65 + k), X(k), y0 + 20, '11px ' + SANS, C.slate, 'center');
    });
    // today
    var a0 = ease(seg(t, 0.02, 0.1));
    c.globalAlpha = a0; c.fillStyle = C.accent; c.beginPath(); c.arc(X(0), Y(START), 5, 0, 7); c.fill();
    text(c, 'today: 1.0M, drawing 42k a year', X(0) + 10, Y(START) - 10, '600 12px ' + SANS, C.ink, 'left');
    // the band, once the futures have run
    var bandA = seg(t, 0.62, 0.74);
    if (bandA > 0) {
      c.globalAlpha = 0.28 * bandA; c.fillStyle = C.band;
      c.beginPath();
      FUT.bands.forEach(function (b, k) { if (k === 0) { c.moveTo(X(k), Y(b[2])); } else { c.lineTo(X(k), Y(b[2])); } });
      for (var k = YEARS; k >= 0; k--) { c.lineTo(X(k), Y(FUT.bands[k][0])); }
      c.closePath(); c.fill();
    }
    // the futures, drawn year by year
    var reach = seg(t, 0.1, 0.6) * YEARS;
    FUT.paths.forEach(function (q, i) {
      var stagger = (i % 8) * 0.25, upto = Math.max(0, Math.min(YEARS, reach - stagger));
      if (upto <= 0) { return; }
      var failed = q.dead > 0 && upto >= q.dead;
      c.globalAlpha = (failed ? 0.85 : 0.32) * (1 - 0.45 * bandA);
      c.strokeStyle = failed ? C.bad : C.band2; c.lineWidth = failed ? 1.6 : 1.1;
      c.beginPath(); c.moveTo(X(0), Y(q.v[0]));
      var whole = Math.floor(upto), k;
      for (k = 1; k <= whole; k++) { c.lineTo(X(k), Y(q.v[k])); if (q.v[k] <= 0) { break; } }
      if (k > whole && whole < YEARS) {
        var f = upto - whole; c.lineTo(X(whole + f), Y(lerp(q.v[whole], q.v[whole + 1], f)));
      }
      c.stroke();
      if (failed) {
        c.globalAlpha = 0.9; c.strokeStyle = C.bad; c.lineWidth = 1.6;
        var xd = X(q.dead), yd = Y(0); line(c, xd - 4, yd - 4, xd + 4, yd + 4); line(c, xd - 4, yd + 4, xd + 4, yd - 4);
      }
    });
    // the median, bold, over the band
    var medA = seg(t, 0.68, 0.8);
    if (medA > 0) {
      c.globalAlpha = medA; c.strokeStyle = C.median; c.lineWidth = 2.6; c.beginPath();
      FUT.bands.forEach(function (b, k) { if (k === 0) { c.moveTo(X(k), Y(b[1])); } else { c.lineTo(X(k), Y(b[1])); } });
      c.stroke();
      text(c, 'median ' + money(FUT.bands[YEARS][1]), X(YEARS) - 4, Y(FUT.bands[YEARS][1]) - 10,
           '600 12px ' + SANS, C.ink, 'right');
      c.globalAlpha = medA * 0.9;
      text(c, 'middle 80% of futures', X(YEARS) - 4, Y(FUT.bands[YEARS][2]) + 16, '11.5px ' + SANS, C.slate, 'right');
    }
    // the answer
    var ans = seg(t, 0.8, 0.9);
    if (ans > 0) {
      var pct = Math.round(FUT.ok * 100), pm = (1.96 * FUT.se * 100).toFixed(1);
      c.globalAlpha = ans;
      box(c, 250, 16, 300, 30, 15); c.fillStyle = C.card; c.fill(); c.strokeStyle = C.ok; c.lineWidth = 1.4; c.stroke();
      text(c, pct + '% of ' + TRIALS.toLocaleString() + ' futures last to 95  ·  ± ' + pm + ' pts',
           W / 2, 36, '600 13px ' + SANS, C.ok, 'center');
    }
  }

  /* -- sequence risk ------------------------------------------------------------------- */
  // Thirty yearly returns with an arithmetic mean of exactly 6%; the second retiree
  // gets them in the opposite order. Both start with 1.0M and draw 60k a year.
  var SEQ = (function () {
    var r = rng(1929), rets = [], i, sum = 0;
    for (i = 0; i < 30; i++) { rets.push(0.06 + 0.15 * normal(r)); sum += rets[i]; }
    var shift = 0.06 - sum / 30;
    rets = rets.map(function (x) { return x + shift; });
    // put the worst years first for the unlucky retiree
    var bad = rets.slice().sort(function (a, b) { return a - b; });
    var early = bad.slice(0, 6), rest = bad.slice(6);
    for (i = rest.length - 1; i > 0; i--) { var j = Math.floor(r() * (i + 1)), tmp = rest[i]; rest[i] = rest[j]; rest[j] = tmp; }
    var unlucky = early.concat(rest), lucky = unlucky.slice().reverse();
    function run(seq) {
      var v = 1.0e6, out = [v], dead = -1;
      seq.forEach(function (x, k) {
        v = Math.max(0, v - 60000) * (1 + x);
        if (v <= 0 && dead < 0) { dead = k + 1; }
        out.push(Math.max(0, v));
      });
      return { v: out, dead: dead };
    }
    return { unlucky: unlucky, lucky: lucky, a: run(unlucky), b: run(lucky) };
  }());

  var SEQ_TOP = Math.ceil(Math.max.apply(null, SEQ.b.v.concat(SEQ.a.v)) / 1e6) * 1e6;
  function sequence(c, t) {
    var x0 = 70, x1 = 740, y0 = 175, y1 = 30, top = SEQ_TOP;
    function X(k) { return x0 + (x1 - x0) * k / 30; }
    function Y(v) { return y0 - (y0 - y1) * Math.min(v, top) / top; }
    var ticks = [], step = top > 4e6 ? 2e6 : 1e6;
    for (var tv = 0; tv <= top + 1; tv += step) { ticks.push(tv); }
    c.globalAlpha = seg(t, 0, 0.06); c.strokeStyle = C.line; c.lineWidth = 1;
    ticks.forEach(function (v) {
      line(c, x0, Y(v), x1, Y(v)); text(c, money(v), x0 - 8, Y(v) + 4, '11px ' + SANS, C.slate, 'right');
    });
    var reach = seg(t, 0.08, 0.7) * 30;
    [[SEQ.b, C.ok, 'good years first'], [SEQ.a, C.bad, 'bad years first']].forEach(function (s) {
      var q = s[0], upto = Math.min(30, reach), k;
      c.globalAlpha = 1; c.strokeStyle = s[1]; c.lineWidth = 2.4; c.beginPath(); c.moveTo(X(0), Y(q.v[0]));
      for (k = 1; k <= Math.floor(upto); k++) { c.lineTo(X(k), Y(q.v[k])); if (q.v[k] <= 0) { break; } }
      c.stroke();
      if (upto >= 30 || (q.dead > 0 && upto >= q.dead)) {
        var end = q.dead > 0 ? q.dead : 30;
        text(c, s[2] + (q.dead > 0 ? ': runs out at ' + (65 + q.dead) : ': ' + money(q.v[30]) + ' at 95'),
             Math.min(X(end) + 6, 560), Y(q.v[end]) + (q.dead > 0 ? -8 : -10), '600 12px ' + SANS, s[1], 'left');
      }
    });
    // the returns, as bars, the second row the mirror of the first
    function bars(seq, yb, colour, label) {
      c.globalAlpha = 1; text(c, label, x0 - 8, yb + 4, '11px ' + SANS, C.slate, 'right');
      seq.forEach(function (x, k) {
        var p = seg(reach, k, k + 1); if (p <= 0) { return; }
        var h = Math.max(-18, Math.min(18, x * 70)) * p, xx = X(k) + 3, w = (x1 - x0) / 30 - 6;
        c.fillStyle = x < 0 ? C.bad : colour; c.globalAlpha = 0.75;
        c.fillRect(xx, h > 0 ? yb - h : yb, w, Math.abs(h));
      });
      c.globalAlpha = 0.6; c.strokeStyle = C.line; line(c, x0, yb, x1, yb);
    }
    bars(SEQ.lucky, 215, C.ok, 'returns');
    bars(SEQ.unlucky, 255, C.slate, 'reversed');
    c.globalAlpha = seg(t, 0.8, 0.9);
    text(c, 'the same thirty returns, averaging 6% - only the order differs', W / 2, 290, '500 12.5px ' + SANS,
         C.ink, 'center');
  }

  /* -- the ledger ---------------------------------------------------------------------- */
  var ROWS = (function () {
    var v = 1.0e6, out = [], rets = [0.071, -0.043, 0.112, 0.058, 0.024, 0.089], fee = 0.0025;
    rets.forEach(function (x, i) {
      var o = v, draw = 42000, fees = (o - draw) * fee, close = (o - draw - fees) * (1 + x);
      out.push({ year: 2027 + i, open: o, draw: draw, fees: fees, ret: x, close: close });
      v = close;
    });
    return out;
  }());
  function fmt(v) { return Math.round(v).toLocaleString('en-US'); }

  function ledger(c, t) {
    ROWS.forEach(function (r, i) {
      var s0 = 0.04 + i * 0.13, p = seg(t, s0, s0 + 0.1), y = 42 + i * 38;
      if (t < s0) { return; }
      var parts = [[r.year + '  ', C.slate, '12.5px '], ['open ' + fmt(r.open) + '  ', C.ink, '12.5px '],
                   ['− draw ' + fmt(r.draw) + '  ', C.ink, '12.5px '], ['− fees ' + fmt(r.fees) + '  ', C.ink, '12.5px '],
                   [(r.ret >= 0 ? '× ' : '× ') + (1 + r.ret).toFixed(3) + '  ', r.ret < 0 ? C.bad : C.ink, '12.5px '],
                   ['= ' + fmt(r.close), C.accent, '600 12.5px ']];
      var total = parts.reduce(function (n, q) { return n + q[0].length; }, 0), left = Math.floor(total * p), x = 70;
      parts.forEach(function (q) {
        if (left <= 0) { return; }
        var piece = q[0].slice(0, left); left -= q[0].length;
        c.globalAlpha = 1; c.font = q[2] + MONO; c.fillStyle = q[1]; c.textAlign = 'left'; c.fillText(piece, x, y);
        x += c.measureText(piece).width;
      });
      if (p < 1) { c.fillStyle = C.accent; c.fillRect(x + 2, y - 11, 7, 14); return; }
      // the tick: the closing balance is next year's opening, to the cent
      c.globalAlpha = 1; box(c, 712, y - 15, 58, 22, 11); c.fillStyle = C.tint; c.fill();
      c.strokeStyle = C.ok; c.lineWidth = 1.2; c.stroke();
      text(c, '✓ ties', 741, y + 1, '600 11.5px ' + SANS, C.ok, 'center');
      if (i > 0) { c.strokeStyle = C.ok; c.lineWidth = 1.2; line(c, 741, y - 31, 741, y - 15); }
    });
    c.globalAlpha = seg(t, 0.84, 0.94);
    text(c, 'every year of every future: closing = opening + flows + growth, checked', W / 2, 282,
         '12px ' + SANS, C.slate, 'center');
  }

  /* -- the runner (MAYA's) ------------------------------------------------------------- */
  var FIGURES = [
    { id: 'lpFutures', draw: futures, h: 280 },
    { id: 'lpSequence', draw: sequence, h: 300 },
    { id: 'lpLedger', draw: ledger, h: 295 }
  ].map(function (f) { f.canvas = document.getElementById(f.id); return f; })
   .filter(function (f) { return f.canvas && f.canvas.getContext; });
  if (!FIGURES.length) { return; }

  function size(f) {
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    f.canvas.width = W * dpr; f.canvas.height = f.h * dpr;
    f.ctx = f.canvas.getContext('2d'); f.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  function paint(f) {
    var c = f.ctx; c.save(); c.clearRect(0, 0, W, f.h); c.textBaseline = 'alphabetic';
    f.draw(c, f.t); c.restore();
  }
  function play(f) {
    if (reduce) { f.t = REST; paint(f); return; }
    var start = null;
    f.playing = true;
    function step(ts) {
      if (start === null) { start = ts; }
      f.t = Math.min(REST, (ts - start) / DURATION);
      paint(f);
      if (f.t < REST) { window.requestAnimationFrame(step); } else { f.playing = false; }
    }
    window.requestAnimationFrame(step);
  }

  readColours();
  FIGURES.forEach(function (f) {
    size(f); f.t = reduce ? REST : 0; f.played = false; paint(f);
    var replay = document.querySelector('[data-replay="' + f.id + '"]');
    if (replay) {
      if (reduce) { replay.hidden = true; }
      replay.addEventListener('click', function () { if (!f.playing) { play(f); } });
    }
  });
  function startWhenSeen(f) { if (f.played) { return; } f.played = true; play(f); }
  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { FIGURES.forEach(function (f) { if (f.canvas === e.target) { startWhenSeen(f); } }); }
      });
    }, { threshold: 0.4 });
    FIGURES.forEach(function (f) { io.observe(f.canvas); });
  } else {
    FIGURES.forEach(startWhenSeen);
  }
  function repaintAll() { readColours(); FIGURES.forEach(function (f) { if (!f.playing) { paint(f); } }); }
  window.addEventListener('resize', function () { FIGURES.forEach(function (f) { size(f); paint(f); }); });
  new MutationObserver(repaintAll).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
}());
