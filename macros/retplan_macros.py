"""RetPlan macros for LibreOffice Calc.

Installed as a user-level Python script so the source stays readable and the
document itself carries no executable payload (CR-12).  Every entry point is a
thin wrapper: read the plan out of the sheet, run the engine in numpy, write the
results back in bulk, and report status into a cell.

Install with:  python3 tools/install_macros.py
"""
from __future__ import annotations

import os
import sys
import time
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

NPCT = 7
PCTS = [5, 10, 25, 50, 75, 90, 95]
N_SAMPLE = 20
N_BINS = 30
N_SWEEP = 21


# --------------------------------------------------------------- plumbing
def _doc():
    """The document the macro is acting on.

    XSCRIPTCONTEXT is injected by LibreOffice when a button fires; the fallback
    covers being driven headless by the test harness.
    """
    try:
        return XSCRIPTCONTEXT.getDocument()      # noqa: F821  (injected by LO)
    except NameError:
        pass
    import uno
    ctx = uno.getComponentContext()
    desktop = ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.frame.Desktop", ctx)
    return desktop.getCurrentComponent()


def _cells(doc, name):
    return doc.NamedRanges.getByName(name).ReferredCells


def _set(doc, name, value):
    c = _cells(doc, name).getCellByPosition(0, 0)
    if isinstance(value, str):
        c.setString(value)
    else:
        c.setValue(float(value))


def _set_block(doc, name, rows):
    """Bulk write - one UNO round trip instead of thousands."""
    rng = _cells(doc, name)
    h, w = rng.Rows.Count, rng.Columns.Count
    out = []
    for r in range(h):
        src = rows[r] if r < len(rows) else []
        out.append(tuple(float(src[c]) if c < len(src) and src[c] is not None else 0.0
                         for c in range(w)))
    rng.setDataArray(tuple(out))


def _set_text_block(doc, name, rows):
    rng = _cells(doc, name)
    h, w = rng.Rows.Count, rng.Columns.Count
    out = []
    for r in range(h):
        src = rows[r] if r < len(rows) else []
        out.append(tuple(src[c] if c < len(src) else "" for c in range(w)))
    rng.setDataArray(tuple(out))


def _status(doc, msg):
    try:
        _set(doc, "SIM_STATUS", msg)
        doc.calculateAll()
    except Exception:
        pass


def _is_doc(obj):
    try:
        return bool(obj.supportsService("com.sun.star.sheet.SpreadsheetDocument"))
    except Exception:
        return False


def _guard(fn):
    def wrapper(*args):
        # A button passes an ActionEvent; the CLI runner passes the document
        # itself.  Never fall back to the desktop when a document was handed in:
        # doing that from outside LibreOffice builds the service in the wrong
        # process and takes the bridge down with it.
        doc = args[0] if args and _is_doc(args[0]) else _doc()
        try:
            auto = doc.isAutomaticCalculationEnabled()
            doc.enableAutomaticCalculation(False)
            doc.addActionLock()
            try:
                return fn(doc)
            finally:
                doc.removeActionLock()
                doc.enableAutomaticCalculation(auto)
                doc.calculateAll()
        except Exception as exc:
            _status(doc, f"FAILED: {exc.__class__.__name__}: {exc}")
            sys.stderr.write(traceback.format_exc())
    wrapper.__name__ = fn.__name__
    return wrapper


def _load():
    import numpy  # noqa: F401  - fail early with a clear message if missing
    from retplan.engine import Projection
    from retplan.reader import read_plan
    return Projection, read_plan


# ------------------------------------------------------------ simulation
def _simulate(doc, trials=None, with_extras=False):
    import numpy as np
    from retplan.metrics import bands, kpis
    from retplan.markets import MarketModel
    Projection, read_plan = _load()

    t0 = time.time()
    plan = read_plan(doc)
    n = int(trials or _cells(doc, "IN_MKT_TRIALS").getCellByPosition(0, 0).getValue())
    n = max(100, min(50000, n))
    if plan.market.mode == "fixed":
        plan.market.mode = "mc"          # the sheet already covers the fixed case
    _status(doc, f"running {n:,} trials ...")

    proj = Projection(plan)
    res = proj.run(n, seed=plan.seed)
    k = kpis(res, plan.policy.legacy_target, plan.policy.confidence)

    nw = bands(res.net_worth, PCTS)                      # (7, T+1)
    sp = bands(res.spend, PCTS)
    T1 = nw.shape[1]
    fan = np.vstack([nw[0], np.diff(nw, axis=0)])        # base + positive bands
    sample = res.net_worth[:N_SAMPLE].T if len(res.net_worth) >= N_SAMPLE \
        else np.zeros((T1, N_SAMPLE))

    _set_block(doc, "SIMP_NW", nw.T.tolist())
    _set_block(doc, "SIMP_FAN", fan.T.tolist())
    _set_block(doc, "SIMP_SPEND", sp.T.tolist())
    _set_block(doc, "SIMP_SAMPLE", np.asarray(sample).tolist())

    term = res.terminal
    lo, hi = float(np.percentile(term, 1)), float(np.percentile(term, 99))
    hi = max(hi, lo + 1.0)
    counts, edges = np.histogram(np.clip(term, lo, hi), bins=N_BINS, range=(lo, hi))
    _set_block(doc, "SIMR_HIST",
               [[float(0.5 * (edges[i] + edges[i + 1])), float(counts[i])]
                for i in range(N_BINS)])

    dep = res.depleted_period
    rows = []
    for i in range(T1):
        share = float((dep >= 0).mean() and ((dep >= 0) & (dep <= i)).mean())
        rows.append([float(res.ages[i]), share])
    _set_block(doc, "SIMR_DEP", rows)

    for key, value in (("SIMK_TRIALS", n), ("SIMK_SUCCESS", k["success_probability"]),
                       ("SIMK_SE", k["success_se"]),
                       ("SIMK_CILO", k["success_ci95"][0]),
                       ("SIMK_CIHI", k["success_ci95"][1]),
                       ("SIMK_TERM5", k["terminal_real_p5"]),
                       ("SIMK_TERM50", k["terminal_real_p50"]),
                       ("SIMK_TERM95", k["terminal_real_p95"]),
                       ("SIMK_FAILRATE", k["failure_rate"]),
                       ("SIMK_DD", k["worst_drawdown"]),
                       ("SIMK_SHORT", k["total_shortfall_p50"])):
        _set(doc, key, value)
    for key, val in (("SIMK_DEPAGE10", k["depletion_age_p10"]),
                     ("SIMK_DEPAGE50", k["depletion_age_p50"])):
        _set(doc, key, 0.0 if val != val else val)          # NaN -> 0

    mm = MarketModel(plan.market)
    em = mm.effective_moments(seed=plan.seed, n=min(4000, max(500, n)), T=plan.horizon)
    eff = []
    for j in range(len(plan.market.assets)):
        mean = float(em["mean"][j])
        sd = float(em["sd"][j])
        eff.append([mean, mean - 0.5 * sd * sd, float(plan.market.assets[j].sigma), sd])
    _set_block(doc, "SIM_EFF", eff)
    _set_block(doc, "SIM_REGMIX", [[float(x)] for x in em["regime_mix"]])
    _set(doc, "SIMK_SHRINK", float(mm.shrinkage[0] if mm.shrinkage else 0.0))

    if with_extras:
        _extras(doc, plan, n)

    _set(doc, "SIMK_SECONDS", time.time() - t0)
    _set(doc, "SIM_RUNHASH", _cells(doc, "SIM_LIVEHASH").getCellByPosition(0, 0).getValue())
    _status(doc, f"done - {n:,} trials in {time.time() - t0:.1f}s "
                 f"(seed {plan.seed})")


def _extras(doc, plan, n):
    from retplan import solvers
    t = max(200, min(1500, n // 2))
    _status(doc, "solving for maximum sustainable spending ...")
    ms = solvers.max_sustainable_spend(plan, trials=t, seed=plan.seed)
    _set(doc, "SIMK_MAXSPEND", ms["spend"])
    first = max(1.0, ms["first_year_base"])
    port = sum(l.opening for l in plan.ledgers) or 1.0
    _set(doc, "SIMK_SWR", ms["spend"] / port)

    _status(doc, "solving for the earliest retirement age ...")
    er = solvers.earliest_retirement_age(plan, trials=t, seed=plan.seed)
    _set(doc, "SIMK_EARLIEST", er["age"])

    _status(doc, "solving for the saving needed ...")
    rq = solvers.required_extra_saving(plan, trials=t, seed=plan.seed)
    _set(doc, "SIMK_REQSAVE", rq["amount"])

    _status(doc, "sweeping spending levels ...")
    curve = solvers.success_curve(plan, trials=t, seed=plan.seed, n=N_SWEEP)
    _set_block(doc, "SIMR_SWEEP", [[a, b] for a, b in curve])

    _status(doc, "ranking the drivers ...")
    rows = solvers.tornado(plan, trials=t, seed=plan.seed)
    _set_text_block(doc, "SIMR_TORN",
                    [[r[0], "", ""] for r in rows] + [["", "", ""]] * (10 - len(rows)))
    rng = _cells(doc, "SIMR_TORN")
    for i, r in enumerate(rows[:10]):
        rng.getCellByPosition(1, i).setValue(float(r[1]))
        rng.getCellByPosition(2, i).setValue(float(r[2]))


# --------------------------------------------------------- entry points
@_guard
def run_simulation(doc=None, *_):
    """Run the Monte Carlo at the trial count on In-Markets."""
    _simulate(doc)


@_guard
def run_quick(doc=None, *_):
    """A fast 500-trial pass, for when you are still editing inputs."""
    _simulate(doc, trials=500)


@_guard
def run_full_analysis(doc=None, *_):
    """Simulation plus solvers, the spending sweep and the tornado."""
    _simulate(doc, with_extras=True)


@_guard
def clear_results(doc=None, *_):
    import numpy as np
    for name in ("SIMP_NW", "SIMP_FAN", "SIMP_SPEND", "SIMP_SAMPLE", "SIMR_HIST",
                 "SIMR_DEP", "SIMR_SWEEP", "SIM_EFF", "SIM_REGMIX"):
        rng = _cells(doc, name)
        _set_block(doc, name, np.zeros((rng.Rows.Count, rng.Columns.Count)).tolist())
    for key, _lab, _f in _KPI_KEYS:
        _set(doc, key, 0.0)
    _set(doc, "SIM_RUNHASH", 0.0)
    _status(doc, "results cleared")


_KPI_KEYS = [("SIMK_TRIALS", "", ""), ("SIMK_SUCCESS", "", ""), ("SIMK_SE", "", ""),
             ("SIMK_CILO", "", ""), ("SIMK_CIHI", "", ""), ("SIMK_TERM5", "", ""),
             ("SIMK_TERM50", "", ""), ("SIMK_TERM95", "", ""),
             ("SIMK_DEPAGE10", "", ""), ("SIMK_DEPAGE50", "", ""),
             ("SIMK_FAILRATE", "", ""), ("SIMK_DD", "", ""), ("SIMK_SHORT", "", ""),
             ("SIMK_MAXSPEND", "", ""), ("SIMK_SWR", "", ""),
             ("SIMK_EARLIEST", "", ""), ("SIMK_REQSAVE", "", ""),
             ("SIMK_SHRINK", "", ""), ("SIMK_SECONDS", "", "")]


SCEN_INPUTS = [
    "IN_P1_AGE", "IN_P1_RETIRE", "IN_P1_DEATH", "IN_P2_AGE", "IN_P2_RETIRE",
    "IN_P2_DEATH", "IN_HORIZON", "IN_INF_MEAN", "IN_INF_SD", "IN_FEE_PLATFORM",
    "IN_FEE_ADVISER", "IN_MKT_SEED", "IN_MKT_TRIALS", "IN_MKT_NU", "IN_CR_PROB",
    "IN_CR_MIN", "IN_CR_MODE", "IN_CR_MAX", "IN_CR_REC", "IN_POL_PCT", "IN_POL_VPW",
    "IN_POL_GUARD_UP", "IN_POL_GUARD_DN", "IN_POL_CUT", "IN_POL_RAISE",
    "IN_POL_LEGACY", "IN_POL_CONF", "IN_POL_DISC", "IN_TX_SUR_RATE", "IN_TX_CG_INCL",
]


def _slot(doc):
    n = int(_cells(doc, "SCEN_SLOT").getCellByPosition(0, 0).getValue())
    store = _cells(doc, "SCEN_STORE")
    return max(0, min(store.Columns.Count - 1, n - 1)), store


@_guard
def save_scenario(doc=None, *_):
    """Park the live assumptions in the active slot."""
    col, store = _slot(doc)
    for i, key in enumerate(SCEN_INPUTS):
        if i >= store.Rows.Count:
            break
        store.getCellByPosition(col, i).setValue(
            _cells(doc, key).getCellByPosition(0, 0).getValue())
    _set(doc, "SCEN_STATUS", f"saved to slot {col + 1}")


@_guard
def load_scenario(doc=None, *_):
    """Replace the live assumptions with the active slot's."""
    col, store = _slot(doc)
    written = 0
    for i, key in enumerate(SCEN_INPUTS):
        if i >= store.Rows.Count:
            break
        cell = store.getCellByPosition(col, i)
        if cell.getString() == "":
            continue                       # blank means "leave this one alone"
        _cells(doc, key).getCellByPosition(0, 0).setValue(cell.getValue())
        written += 1
    _set(doc, "SCEN_STATUS", f"loaded {written} assumptions from slot {col + 1}")


g_exportedScripts = (run_simulation, run_quick, run_full_analysis, clear_results,
                     save_scenario, load_scenario)
