"""Monte Carlo projection of a portfolio of securities.

The simulation runs on a quarterly clock whatever the reporting frequency, so
quarterly rebalancing, quarterly cash flows and quarter-granular drawdowns are
all real, and an annual report is just every fourth quarter.

**What each security is assumed to do**

- *Volatility* blends the last year's realised daily volatility with the long-run
  volatility of up to 20 years of monthly history (equal weight in variance), so
  one calm or one violent year does not set the risk of the next thirty.
- *Expected return* is never the last year's sample mean - a year of data says
  almost nothing about the mean. It is the asset class's long-run assumption,
  optionally moved towards the security's own long-run history in proportion to
  how much history there is (``return_source='blend'``, at most half weight at
  20 years), or taken from history alone (``'history'``) or from the class alone
  (``'assumption'``). Any holding can carry its own override.
- *Correlation* comes from the overlapping daily returns in the database,
  shrunk 30% towards long-run class correlations, and repaired to be positive
  semi-definite before its Cholesky factor is taken.

**Three return models**

- ``parametric``: correlated lognormal returns (geometric Brownian motion).
- ``fat_tails``: the same, with multivariate Student-t shocks (5 degrees of
  freedom, variance-matched). A shared chi-square draw means crashes hit every
  asset at once, which is how crashes behave.
- ``bootstrap``: 21-trading-day blocks of the stored daily returns, resampled on
  common dates so cross-asset correlation, fat tails and volatility clustering
  come from the data itself (volatility clustering only within a window, since
  windows are drawn independently); re-centred on the expected return and
  rescaled to the blended volatility.

A crisis replay (``portfolio.stress``) can open every trial.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import date

import numpy as np

from retplan.rng import cholesky_psd

from .assets import CASH_SYMBOL, CLASSES, class_corr
from .stress import SCENARIOS, class_path

Q = 4                     # simulation steps per year
DAYS_PER_YEAR = 252
BLOCK = 21                # bootstrap block, trading days
CORR_SHRINK = 0.30
MIN_DAYS = 60             # below this, a security's own daily data is not used
PCTS = (5, 10, 25, 50, 75, 90, 95)
METHODS = [("parametric", "Lognormal (correlated GBM)"),
           ("fat_tails", "Fat tails (Student-t, 5 df)"),
           ("bootstrap", "Bootstrap of last year's daily returns")]
RETURN_SOURCES = [("blend", "Class assumption, nudged by long-run history"),
                  ("assumption", "Class assumption only"),
                  ("history", "Security's own long-run history")]
REBALANCE = [("annual", "Annually"), ("quarterly", "Quarterly"), ("none", "Never (let it drift)")]


# --------------------------------------------------------------------------- #
# settings
# --------------------------------------------------------------------------- #
@dataclass
class CashFlow:
    kind: str = "contribution"        # contribution | withdrawal
    amount: float = 0.0               # per year
    start_year: int = 1               # 1 = the first projected year
    end_year: int = 10
    indexed: bool = True              # grows with inflation (today's money)
    growth: float = 0.0               # extra growth per year above that
    label: str = ""


@dataclass
class Settings:
    years: int = 10
    frequency: str = "annual"         # annual | quarterly
    trials: int = 5000
    method: str = "parametric"        # parametric | fat_tails | bootstrap
    return_source: str = "blend"      # blend | assumption | history
    inflation: float = 0.025
    fee: float = 0.0                  # annual advisory / platform fee
    rebalance: str = "annual"         # annual | quarterly | none
    target: float = 0.0               # goal, in today's money (0 = none)
    withdrawal_rate: float = 0.0      # % of the portfolio each year, on top of flows
    flows: list = field(default_factory=list)
    stress: str = ""                  # a portfolio.stress key opening every trial
    overrides: dict = field(default_factory=dict)   # symbol -> {mu, sigma}
    seed: int = 20260929

    @classmethod
    def from_dict(cls, d: dict | None) -> "Settings":
        d = dict(d or {})
        flows = [CashFlow(**{k: v for k, v in f.items()
                             if k in CashFlow.__dataclass_fields__})
                 for f in d.pop("flows", []) or [] if isinstance(f, dict)]
        s = cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
        s.flows = flows
        return s.clamped()

    def clamped(self) -> "Settings":
        self.years = int(min(60, max(1, int(self.years))))
        self.trials = int(min(50000, max(200, int(self.trials))))
        if self.frequency not in ("annual", "quarterly"):
            self.frequency = "annual"
        if self.method not in dict(METHODS):
            self.method = "parametric"
        if self.return_source not in dict(RETURN_SOURCES):
            self.return_source = "blend"
        if self.rebalance not in dict(REBALANCE):
            self.rebalance = "annual"
        if self.stress and self.stress not in SCENARIOS:
            self.stress = ""
        self.inflation = float(min(0.25, max(-0.05, self.inflation)))
        self.fee = float(min(0.05, max(0.0, self.fee)))
        self.withdrawal_rate = float(min(0.5, max(0.0, self.withdrawal_rate)))
        self.target = float(max(0.0, self.target))
        return self

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- #
# the assets the simulation sees
# --------------------------------------------------------------------------- #
@dataclass
class AssetInput:
    symbol: str
    name: str
    asset_class: str
    value: float
    daily: list = field(default_factory=list)       # [(date, adj_close)]
    lt_return: float | None = None
    lt_vol: float | None = None
    lt_years: float | None = None


@dataclass
class AssetModel:
    symbol: str
    name: str
    asset_class: str
    weight: float
    mu: float                 # expected simple return, per year
    sigma: float              # volatility, per year
    days: int                 # daily observations used
    mu_note: str = ""
    sigma_note: str = ""
    sigma_1y: float | None = None


def _daily_log_returns(daily):
    px = np.array([p for _, p in daily], dtype=float)
    if len(px) < 2:
        return {}
    r = np.log(px[1:] / px[:-1])
    return {d: v for (d, _), v in zip(daily[1:], r) if np.isfinite(v)}


def estimate(assets: list[AssetInput], settings: Settings):
    """Per-asset (mu, sigma) and the correlation matrix, with notes on each."""
    total = sum(a.value for a in assets) or 1.0
    rets = [_daily_log_returns(a.daily) if a.symbol != CASH_SYMBOL else {}
            for a in assets]
    models = []
    for a, r in zip(assets, rets):
        cls = CLASSES.get(a.asset_class, CLASSES["other"])
        # -- volatility
        s1y = None
        if len(r) >= MIN_DAYS:
            v = np.array(list(r.values()))
            s1y = float(v.std(ddof=1) * math.sqrt(DAYS_PER_YEAR))
        if a.symbol == CASH_SYMBOL:
            sigma, snote = cls["sigma"], "cash"
        elif s1y is not None and a.lt_vol:
            sigma = math.sqrt(0.5 * s1y ** 2 + 0.5 * a.lt_vol ** 2)
            snote = f"blend of 1y ({s1y:.1%}) and {a.lt_years:.0f}y ({a.lt_vol:.1%})"
        elif s1y is not None:
            sigma, snote = s1y, f"last year's daily data ({len(r)} days)"
        elif a.lt_vol:
            sigma, snote = a.lt_vol, f"{a.lt_years:.0f}y monthly history"
        else:
            sigma, snote = cls["sigma"], f"{cls['label']} assumption"
        # -- expected return
        prior = cls["mu"]
        src = settings.return_source
        has_lt = a.lt_return is not None and (a.lt_years or 0) >= 3
        if a.symbol == CASH_SYMBOL:
            mu, mnote = prior, "cash assumption"
        elif src == "history" and has_lt:
            mu, mnote = a.lt_return, f"{a.lt_years:.0f}y history"
        elif src == "blend" and has_lt:
            w = min(a.lt_years, 20.0) / 40.0
            mu = (1 - w) * prior + w * a.lt_return
            mnote = (f"{1 - w:.0%} {cls['label'].lower()} assumption ({prior:.1%}) + "
                     f"{w:.0%} {a.lt_years:.0f}y history ({a.lt_return:.1%})")
        else:
            mu, mnote = prior, f"{cls['label']} assumption"
        ov = (settings.overrides or {}).get(a.symbol) or {}
        if ov.get("mu") not in (None, ""):
            mu, mnote = float(ov["mu"]), "your override"
        if ov.get("sigma") not in (None, ""):
            sigma, snote = float(ov["sigma"]), "your override"
        models.append(AssetModel(a.symbol, a.name, a.asset_class, a.value / total,
                                 float(mu), float(max(sigma, 0.0)), len(r), mnote,
                                 snote, s1y))
    # -- correlation
    n = len(assets)
    corr = np.eye(n)
    for i in range(n):
        for j in range(i + 1, n):
            prior = class_corr(assets[i].asset_class, assets[j].asset_class)
            common = rets[i].keys() & rets[j].keys()
            if len(common) >= MIN_DAYS:
                x = np.array([rets[i][d] for d in common])
                y = np.array([rets[j][d] for d in common])
                if x.std() > 0 and y.std() > 0:
                    sample = float(np.corrcoef(x, y)[0, 1])
                    c = (1 - CORR_SHRINK) * sample + CORR_SHRINK * prior
                else:
                    c = prior
            else:
                c = prior
            corr[i, j] = corr[j, i] = c
    return models, corr, rets


# --------------------------------------------------------------------------- #
# the simulation
# --------------------------------------------------------------------------- #
def _lognormal_params(mu, sigma):
    """Per-quarter log-mean and log-sd for an arithmetic annual (mu, sigma)."""
    mu = np.maximum(np.asarray(mu), -0.95)
    s2 = np.log1p((np.asarray(sigma) / (1 + mu)) ** 2)
    m = np.log1p(mu) - 0.5 * s2
    return m / Q, np.sqrt(s2 / Q)


def _flow_schedule(settings: Settings, steps: int):
    """Nominal contribution and withdrawal per quarter, before any shortfall."""
    contrib, withdraw = np.zeros(steps), np.zeros(steps)
    for k in range(steps):
        year = k // Q + 1                       # 1-based projected year
        t = k / Q                               # years elapsed at quarter start
        for f in settings.flows:
            if not (int(f.start_year) <= year <= int(f.end_year)):
                continue
            amt = float(f.amount) / Q
            amt *= (1 + float(f.growth)) ** (year - int(f.start_year))
            if f.indexed:
                amt *= (1 + settings.inflation) ** t
            if f.kind == "withdrawal":
                withdraw[k] += amt
            else:
                contrib[k] += amt
    return contrib, withdraw


def simulate(assets: list[AssetInput], settings: Settings) -> dict:
    """Run the projection; returns plain JSON-able data for the page and the DB."""
    settings = settings.clamped()
    assets = [a for a in assets if a.value > 0]
    if not assets:
        raise ValueError("the portfolio has no priced holdings to project")
    models, corr, rets = estimate(assets, settings)
    n_a, n_t = len(models), settings.trials
    steps = settings.years * Q
    w = np.array([m.weight for m in models])
    mu = np.array([m.mu for m in models])
    sig = np.array([m.sigma for m in models])
    m_q, s_q = _lognormal_params(mu, sig)
    L, repair = cholesky_psd(corr)
    rng = np.random.default_rng(int(settings.seed))

    # bootstrap source: residual daily returns on dates every risky asset shares
    boot = None
    notes = []
    if settings.method == "bootstrap":
        risky = [i for i, m in enumerate(models) if m.symbol != CASH_SYMBOL]
        common = None
        for i in risky:
            keys = set(rets[i])
            common = keys if common is None else common & keys
        common = sorted(common or [])
        if len(common) >= 4 * BLOCK:
            D = np.zeros((len(common), n_a))
            for i in risky:
                D[:, i] = [rets[i][d] for d in common]
            # Every 21-day window sum, on the same dates for every asset. A year
            # holds only ~12 independent windows, so their raw spread is a very
            # noisy estimate of volatility; each column is therefore centred and
            # scaled so a quarter's shock has exactly the blended volatility.
            # The data supplies the *shape* - fat tails, cross-asset co-movement -
            # and the assumptions supply the level.
            C = np.vstack([np.zeros((1, n_a)), np.cumsum(D, axis=0)])
            W = C[BLOCK:] - C[:-BLOCK]
            n_blk = DAYS_PER_YEAR // Q // BLOCK
            for i in risky:
                col = W[:, i] - W[:, i].mean()
                sd = col.std()
                W[:, i] = col * (s_q[i] / math.sqrt(n_blk)) / sd if sd > 0 else 0.0
            boot = W
            notes.append(f"Bootstrap from {len(common)} common trading days: "
                         f"{len(W)} overlapping {BLOCK}-day windows, {n_blk} per quarter.")
        else:
            notes.append("Too few common trading days for a bootstrap "
                         f"({len(common)}); used the lognormal model instead.")
    if repair > 0:
        notes.append(f"Correlation matrix repaired with {repair:.0%} shrinkage to be "
                     "positive definite.")

    stress_q = []
    if settings.stress:
        stress_q = [np.array([class_path(settings.stress, m.asset_class)[k]
                              for m in models])
                    for k in range(len(SCENARIOS[settings.stress]["returns"]["equity"]))]
        stress_q = stress_q[:steps]

    contrib, withdraw_fixed = _flow_schedule(settings, steps)
    start = float(sum(a.value for a in assets))
    V = np.tile(w * start, (n_t, 1))
    total = np.full(n_t, start)
    peak = np.ones(n_t)
    max_dd = np.zeros(n_t)
    depleted_at = np.full(n_t, -1)
    growth_index = np.ones(n_t)             # time-weighted, fees included
    rec_total = np.empty((n_t, steps + 1))
    rec_total[:, 0] = start
    rec_twr = np.empty((n_t, steps))        # quarter returns
    rec_contrib = np.zeros((n_t, steps))
    rec_withdraw = np.zeros((n_t, steps))
    fee_q = 1 - (1 - settings.fee) ** (1 / Q)
    reb_every = {"quarterly": 1, "annual": Q, "none": 0}[settings.rebalance]
    nu = 5.0

    for k in range(steps):
        # 1. cash flows at the start of the quarter
        c = contrib[k]
        if c > 0:
            V += c * w                       # new money buys the target mix
            rec_contrib[:, k] = c
        total = V.sum(axis=1)
        want = withdraw_fixed[k] + settings.withdrawal_rate / Q * total
        if np.any(want > 0):
            take = np.minimum(want, total)
            frac = np.divide(take, total, out=np.zeros_like(total), where=total > 0)
            V *= (1 - frac)[:, None]
            rec_withdraw[:, k] = take
            short = (want - take > 1e-6) & (depleted_at < 0)
            depleted_at[short] = k
        base = V.sum(axis=1)
        # 2. returns for the quarter
        if k < len(stress_q):
            gross = np.tile(1 + stress_q[k], (n_t, 1))
        elif boot is not None:
            n_blk = DAYS_PER_YEAR // Q // BLOCK
            pick = rng.integers(0, boot.shape[0], size=(n_t, n_blk))
            shock = boot[pick].sum(axis=1)
            gross = np.exp(m_q + shock)
        else:
            z = rng.standard_normal((n_t, n_a)) @ L.T
            if settings.method == "fat_tails":
                chi = rng.chisquare(nu, size=(n_t, 1))
                z = z / np.sqrt(chi / nu) * math.sqrt((nu - 2) / nu)
            gross = np.exp(m_q + s_q * z)
        V *= gross
        if fee_q > 0:
            V *= (1 - fee_q)
        # 3. rebalance at the end of the quarter
        if reb_every and (k + 1) % reb_every == 0:
            V = V.sum(axis=1)[:, None] * w
        total = V.sum(axis=1)
        r = np.divide(total, base, out=np.ones_like(total), where=base > 1e-9) - 1
        rec_twr[:, k] = r
        growth_index *= (1 + r)
        peak = np.maximum(peak, growth_index)
        max_dd = np.minimum(max_dd, growth_index / peak - 1)
        rec_total[:, k + 1] = total

    return _summarise(settings, models, corr, start, rec_total, rec_twr, rec_contrib,
                      rec_withdraw, depleted_at, max_dd, notes, mu, sig, w)


# --------------------------------------------------------------------------- #
# results
# --------------------------------------------------------------------------- #
def _pct(a, axis=0):
    return {f"p{p}": v for p, v in zip(PCTS, np.percentile(a, PCTS, axis=axis))}


def _period_labels(settings: Settings, today: date):
    if settings.frequency == "quarterly":
        out = []
        y, q = today.year, (today.month - 1) // 3 + 1
        for _ in range(settings.years * Q):
            q += 1
            if q > 4:
                q, y = 1, y + 1
            out.append(f"{y} Q{q}")
        return out
    return [str(today.year + i) for i in range(1, settings.years + 1)]


def _summarise(settings, models, corr, start, tot, twr, contrib, withdraw,
               depleted_at, max_dd, notes, mu, sig, w):
    steps = twr.shape[1]
    n_t = tot.shape[0]
    per = 1 if settings.frequency == "quarterly" else Q
    idx = list(range(per, steps + 1, per))               # boundaries in quarters
    years_at = np.array([k / Q for k in idx])
    deflate = (1 + settings.inflation) ** years_at

    labels = _period_labels(settings, date.today())
    # flows land at the start of each quarter, so deflate them by that quarter's CPI
    q_deflate = (1 + settings.inflation) ** (np.arange(steps) / Q)
    contrib_real = contrib / q_deflate
    withdraw_real = withdraw / q_deflate
    periods = []
    growth = np.cumprod(1 + twr, axis=1)
    target_hits = None
    if settings.target > 0:
        real = tot[:, 1:] / (1 + settings.inflation) ** (np.arange(1, steps + 1) / Q)
        hit = real >= settings.target
        first = np.where(hit.any(axis=1), hit.argmax(axis=1), -1)
        target_hits = first
    prev = 0
    for j, k in enumerate(idx):
        end = tot[:, k]
        r = np.prod(1 + twr[:, prev:k], axis=1) - 1
        cum = growth[:, k - 1]
        yrs = k / Q
        row = dict(
            label=labels[j], years=yrs,
            nominal=_pct(end), real=_pct(end / deflate[j]),
            mean=float(end.mean()),
            ret=_pct(r), ret_mean=float(r.mean()),
            cagr_p50=float(np.median(cum) ** (1 / yrs) - 1),
            contrib=float(contrib[:, prev:k].sum(axis=1).mean()),
            withdraw=float(np.median(withdraw[:, prev:k].sum(axis=1))),
            contrib_real=float(contrib_real[:, prev:k].sum(axis=1).mean()),
            withdraw_real=float(np.median(withdraw_real[:, prev:k].sum(axis=1))),
            p_loss_period=float((r < 0).mean()),
            p_depleted=float(((depleted_at >= 0) & (depleted_at < k)).mean()),
            p_above_start=float((end / deflate[j] >= start).mean()),
        )
        if target_hits is not None:
            row["p_target"] = float(((target_hits >= 0) & (target_hits < k)).mean())
        periods.append(row)
        prev = k
    for row in periods:
        row["nominal"] = {k: float(v) for k, v in row["nominal"].items()}
        row["real"] = {k: float(v) for k, v in row["real"].items()}
        row["ret"] = {k: float(v) for k, v in row["ret"].items()}

    end = tot[:, -1]
    end_real = end / deflate[-1]
    cagr = growth[:, -1] ** (1 / settings.years) - 1
    net_in = start + contrib.sum(axis=1) - withdraw.sum(axis=1)
    annual = np.prod((1 + twr).reshape(n_t, settings.years, Q), axis=2) - 1
    worst_year = annual.min(axis=1)

    # portfolio-level analytics, for the "what you are assuming" panel
    cov = np.outer(sig, sig) * corr
    port_mu = float(w @ mu)
    port_sig = float(math.sqrt(max(w @ cov @ w, 0.0)))
    rc = (w * (cov @ w)) / (port_sig ** 2) if port_sig > 0 else w * 0

    # representative trials: the one nearest each percentile of real end value
    reps = {}
    for p in (10, 50, 90):
        target = np.percentile(end_real, p)
        i = int(np.argmin(np.abs(end_real - target)))
        path = []
        prev = 0
        for j, k in enumerate(idx):
            path.append(dict(label=labels[j], value=float(tot[i, k]),
                             real=float(tot[i, k] / deflate[j]),
                             ret=float(np.prod(1 + twr[i, prev:k]) - 1),
                             contrib=float(contrib[i, prev:k].sum()),
                             withdraw=float(withdraw[i, prev:k].sum())))
            prev = k
        reps[f"p{p}"] = path

    # expected path: every asset earns its expected return, no noise
    exp_path, v = [], start
    cq, wq = _flow_schedule(settings, steps)
    port_q = (1 + port_mu) ** (1 / Q) - 1
    fee_q = 1 - (1 - settings.fee) ** (1 / Q)
    for k in range(steps):
        v += cq[k]
        v -= min(v, wq[k] + settings.withdrawal_rate / Q * v)
        v *= (1 + port_q) * (1 - fee_q)
        if (k + 1) % per == 0:
            exp_path.append(float(v))

    hist_end, edges = np.histogram(end_real, bins=24,
                                   range=(0, float(np.percentile(end_real, 98))))
    hist_dd, dd_edges = np.histogram(max_dd, bins=20, range=(-0.8, 0.0))

    summary = dict(
        start=start, years=settings.years, trials=n_t, method=settings.method,
        frequency=settings.frequency,
        end_nominal=_fl(_pct(end)), end_real=_fl(_pct(end_real)),
        end_mean=float(end.mean()),
        cagr=_fl(_pct(cagr)),
        p_loss=float((end < net_in - 1e-6).mean()),
        p_real_loss=float((cagr < settings.inflation).mean()),
        p_depleted=float((depleted_at >= 0).mean()),
        p_target=(float(((target_hits >= 0)).mean()) if target_hits is not None
                  else None),
        target=settings.target,
        max_dd=_fl(_pct(max_dd)),
        worst_year=_fl(_pct(worst_year)),
        total_contrib=float(contrib.sum(axis=1).mean()),
        total_withdraw_p50=float(np.median(withdraw.sum(axis=1))),
        exp_return=port_mu, exp_vol=port_sig,
        expected_end=exp_path[-1] if exp_path else start,
        success_se=None,
    )
    if summary["p_target"] is not None:
        p = summary["p_target"]
        summary["success_se"] = math.sqrt(max(p * (1 - p), 1e-12) / n_t)

    return dict(
        settings=settings.to_dict(),
        summary=summary,
        periods=periods,
        expected=exp_path,
        representative=reps,
        assets=[dict(asdict(m), risk_share=float(rc[i]))
                for i, m in enumerate(models)],
        corr=[[float(x) for x in row] for row in corr],
        hist_end=dict(counts=hist_end.tolist(), edges=edges.tolist()),
        hist_dd=dict(counts=hist_dd.tolist(), edges=dd_edges.tolist()),
        notes=notes,
        stress=(dict(key=settings.stress, **{k: v for k, v in
                                             SCENARIOS[settings.stress].items()
                                             if k != "returns"})
                if settings.stress else None),
        run_date=date.today().isoformat(),
    )


def _fl(d):
    return {k: float(v) for k, v in d.items()}


# --------------------------------------------------------------------------- #
# deterministic crisis replay
# --------------------------------------------------------------------------- #
def replay(assets: list[AssetInput], key: str, settings: Settings | None = None,
           after_quarters: int = 40) -> dict:
    """Run the current mix through one crisis, then at expected returns until
    it recovers (or ``after_quarters`` pass). No cash flows: this isolates the
    portfolio's own behaviour."""
    settings = (settings or Settings()).clamped()
    assets = [a for a in assets if a.value > 0]
    models, _, _ = estimate(assets, settings)
    w = np.array([m.weight for m in models])
    mu = np.array([m.mu for m in models])
    paths = np.array([class_path(key, m.asset_class) for m in models])   # (A, K)
    start = float(sum(a.value for a in assets))
    V = w * start
    out = [start]
    reb = settings.rebalance
    for k in range(paths.shape[1]):
        V = V * (1 + paths[:, k])
        if reb == "quarterly" or (reb == "annual" and (k + 1) % Q == 0):
            V = V.sum() * w
        out.append(float(V.sum()))
    trough = min(out)
    crisis_len = len(out) - 1
    recovered_at = None
    peak = max(out)
    for k in range(after_quarters):
        if out[-1] >= start and recovered_at is None:
            recovered_at = len(out) - 1
            break
        V = V * (1 + mu) ** (1 / Q)
        out.append(float(V.sum()))
    if recovered_at is None and out[-1] >= start:
        recovered_at = len(out) - 1
    sc = SCENARIOS[key]
    return dict(key=key, label=sc["label"], short=sc["short"], blurb=sc["blurb"],
                start=start, path=out, crisis_quarters=crisis_len,
                trough=trough, drawdown=trough / start - 1,
                end_of_crisis=out[crisis_len], crisis_return=out[crisis_len] / start - 1,
                recovered_quarter=recovered_at, peak=peak)


def assets_from_db(repo, owner: str, pid: int) -> list[AssetInput]:
    """One AssetInput per symbol (a symbol held in two accounts is one asset),
    with its stored daily closes and long-run statistics."""
    val = repo.valuation(owner, pid)
    by: dict[str, AssetInput] = {}
    for p in val.positions:
        if p.value <= 0:
            continue
        a = by.get(p.symbol)
        if a is None:
            by[p.symbol] = AssetInput(p.symbol, p.name or p.symbol, p.asset_class,
                                      p.value)
        else:
            a.value += p.value
    base = val.currency
    for sym, a in by.items():
        a.daily = repo.series_in(sym, base) if sym != CASH_SYMBOL else []
        sec = repo.security(sym) or {}
        a.lt_return, a.lt_vol, a.lt_years = (sec.get("lt_return"), sec.get("lt_vol"),
                                             sec.get("lt_years"))
    return sorted(by.values(), key=lambda a: -a.value)
