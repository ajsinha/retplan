"""Market return generation: deterministic, historical, and stochastic.

The stochastic path is built in three independent layers so each can be reasoned
about (and switched off) on its own:

  1. a Markov **regime** (bear / normal / bull, or any user set) that sets the
     drift, the volatility and how tightly the assets co-move that period;
  2. correlated **diffusive shocks** drawn as lognormal, normal or variance
     matched Student-t;
  3. a **jump process** for crashes, with a depth distribution, a multi-period
     drawdown shape, per-asset transmission betas and partial recovery.

A crash is therefore not an equity-only haircut: government bonds can carry a
negative beta and gain while equities fall, which is the behaviour that actually
determines whether a diversified retiree survives 2008.

See docs/04-math-and-simulation.md sections 5-9.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .rng import LEcuyer, cholesky_psd, norm_ppf, student_t, triangular_ppf


@dataclass
class AssetClass:
    label: str = "Equity"
    mu: float = 0.07            # arithmetic expected simple return, per year
    sigma: float = 0.17         # annualised standard deviation
    income_yield: float = 0.02  # share of mu paid as taxable income
    ter: float = 0.0020         # fund cost
    crash_beta: float = 1.0     # transmission of a crash to this class


@dataclass
class Regime:
    label: str = "Normal"
    mean_offset: float = 0.0    # added to every asset's mu while in this regime
    vol_mult: float = 1.0
    corr_tighten: float = 0.0   # 0 = user matrix, 1 = everything perfectly correlated
    trans: list = field(default_factory=lambda: [1.0])


@dataclass
class CrashSpec:
    enabled: bool = True
    prob: float = 0.04          # probability a crash *starts* in a given year
    depth_min: float = 0.20
    depth_mode: float = 0.35
    depth_max: float = 0.60
    duration: int = 2           # periods over which the fall is spread
    shape: list = field(default_factory=lambda: [0.6, 0.3, 0.1])
    recovery_fraction: float = 0.45
    recovery_periods: int = 3


@dataclass
class InflationSpec:
    mode: str = "fixed"         # fixed | path | stochastic
    mean: float = 0.025
    sd: float = 0.012
    persistence: float = 0.55   # AR(1) phi
    corr_equity: float = -0.20
    path: list = field(default_factory=list)


@dataclass
class MarketSpec:
    mode: str = "mc"            # fixed | path | mc | historical
    dist: str = "lognormal"     # lognormal | normal | t
    nu: float = 5.0
    assets: list = field(default_factory=lambda: [AssetClass()])
    corr: list = field(default_factory=lambda: [[1.0]])
    regimes: list = field(default_factory=lambda: [Regime()])
    start_regime: str = "stationary"   # stationary | <index> | random
    crash: CrashSpec = field(default_factory=CrashSpec)
    inflation: InflationSpec = field(default_factory=InflationSpec)
    fixed_path: list = field(default_factory=list)      # (T, A) simple returns
    historical: list = field(default_factory=list)      # (n, A) historical rows
    block_length: int = 5
    antithetic: bool = False
    calibrate: bool = True
    """Re-centre regime drift and crash drag so the *unconditional* mean return
    equals the mu the user typed.  Without this, adding a bear regime or a crash
    process silently lowers every expected return in the model, which makes the
    inputs mean something different from what they say."""


def stationary_distribution(P: np.ndarray) -> np.ndarray:
    """Long-run regime mix, by repeated squaring (docs/04 section 6)."""
    M = np.asarray(P, dtype=float)
    for _ in range(6):          # P^64 has converged for any practical matrix
        M = M @ M
    return M[0] / M[0].sum()


def expected_durations(P: np.ndarray) -> np.ndarray:
    d = np.diag(np.asarray(P, dtype=float))
    return 1.0 / np.maximum(1e-9, 1.0 - d)


def _log_params(m, s):
    """Arithmetic (mean, sd) of simple returns -> lognormal parameters."""
    m = np.asarray(m, dtype=float)
    s = np.asarray(s, dtype=float)
    var = np.log1p((s / (1.0 + m)) ** 2)
    return np.log1p(m) - 0.5 * var, np.sqrt(var)


class MarketModel:
    def __init__(self, spec: MarketSpec):
        self.spec = spec
        self.A = len(spec.assets)
        self.mu = np.array([a.mu for a in spec.assets])
        self.sigma = np.array([a.sigma for a in spec.assets])
        self.beta = np.array([a.crash_beta for a in spec.assets])
        self.corr = np.asarray(spec.corr, dtype=float)
        self.P = np.array([r.trans for r in spec.regimes], dtype=float)
        if self.P.shape != (len(spec.regimes), len(spec.regimes)):
            raise ValueError("regime transition matrix must be square (K x K)")
        rs = self.P.sum(axis=1)
        if np.any(np.abs(rs - 1) > 1e-6):
            raise ValueError(f"regime transition rows must sum to 1, got {rs}")
        self.pi = stationary_distribution(self.P)
        # A scalar regime offset is scaled by each asset's volatility relative to
        # the first asset, so a bear market hits equities harder than cash.
        ref = self.sigma[0] if self.sigma[0] > 1e-9 else 1.0
        self.offsets = np.array([
            (np.asarray(r.mean_offset, dtype=float) if np.ndim(r.mean_offset)
             else float(r.mean_offset) * self.sigma / ref)
            for r in spec.regimes])                      # (K, A)
        self.drag = self._crash_drag()
        if spec.calibrate:
            bar = self.pi @ self.offsets                 # (A,)
            self.mu_eff = (1.0 + self.mu) / (1.0 - self.drag) - 1.0 - bar
        else:
            self.mu_eff = self.mu.copy()
        self.chol, self.shrinkage = [], []
        ones = np.ones((self.A, self.A))
        for r in spec.regimes:
            c = (1 - r.corr_tighten) * self.corr + r.corr_tighten * ones
            L, lam = cholesky_psd(c)
            self.chol.append(L)
            self.shrinkage.append(lam)

    def _crash_drag(self):
        """Expected per-period multiplicative loss from the jump process."""
        cs = self.spec.crash
        if not cs.enabled or cs.prob <= 0:
            return np.zeros(self.A)
        mean_depth = (cs.depth_min + cs.depth_mode + cs.depth_max) / 3.0
        net = mean_depth * (1.0 - cs.recovery_fraction)
        return np.clip(cs.prob * net * self.beta, -0.5, 0.5)

    def effective_moments(self, seed=1, n=8000, T=60):
        """Realised long-run statistics after regimes and crashes.

        Reported next to the inputs, because the honest answer to "what return am
        I actually assuming?" is not the number typed into the asset table.
        """
        out = self.generate(n, T, seed)
        r = out["returns"].reshape(-1, self.A)
        return dict(mean=r.mean(axis=0), sd=r.std(axis=0),
                    corr=np.corrcoef(r.T) if self.A > 1 else np.ones((1, 1)),
                    p01=np.percentile(r, 1, axis=0), p99=np.percentile(r, 99, axis=0),
                    regime_mix=np.bincount(out["regime"].ravel(), minlength=self.P.shape[0])
                    / out["regime"].size)

    # -- regimes ---------------------------------------------------------
    def _regime_path(self, n, T, seed):
        K = self.P.shape[0]
        g = LEcuyer(seed, n, "regime")
        pi = stationary_distribution(self.P)
        u0 = g.uniform()
        if self.spec.start_regime == "stationary":
            state = np.searchsorted(np.cumsum(pi), u0).clip(0, K - 1)
        elif self.spec.start_regime == "random":
            state = (u0 * K).astype(int).clip(0, K - 1)
        else:
            state = np.full(n, int(self.spec.start_regime), dtype=int)
        out = np.empty((n, T), dtype=np.int8)
        cum = np.cumsum(self.P, axis=1)
        for t in range(T):
            out[:, t] = state
            u = g.uniform()
            state = (u[:, None] > cum[state]).sum(axis=1).clip(0, K - 1)
        return out

    # -- crashes ---------------------------------------------------------
    def _crash_path(self, n, T, seed):
        cs = self.spec.crash
        shock = np.zeros((n, T))
        if not cs.enabled or cs.prob <= 0:
            return shock, np.zeros((n, T))
        go = LEcuyer(seed, n, "crash_occur")
        gd = LEcuyer(seed, n, "crash_depth")
        w = np.array(cs.shape[: max(1, cs.duration)], dtype=float)
        w = w / w.sum()
        depth_rec = np.zeros((n, T))
        for t in range(T):
            hit = go.uniform() < cs.prob
            if not hit.any():
                continue
            d = triangular_ppf(gd.uniform(), cs.depth_min, cs.depth_mode, cs.depth_max) * hit
            depth_rec[:, t] = d
            for j, wj in enumerate(w):
                if t + j < T:
                    shock[:, t + j] += d * wj
            if cs.recovery_fraction > 0 and cs.recovery_periods > 0:
                back = d * cs.recovery_fraction / cs.recovery_periods
                for j in range(cs.recovery_periods):
                    k = t + len(w) + j
                    if k < T:
                        shock[:, k] -= back
        return shock, depth_rec

    # -- inflation -------------------------------------------------------
    def _inflation_path(self, n, T, seed, eq_shock):
        sp = self.spec.inflation
        if sp.mode == "fixed":
            return np.full((n, T), sp.mean)
        if sp.mode == "path":
            p = np.asarray(sp.path, dtype=float)
            p = np.resize(p, T) if p.size else np.full(T, sp.mean)
            return np.tile(p, (n, 1))
        g = LEcuyer(seed, n, "inflation")
        rho = float(np.clip(sp.corr_equity, -0.99, 0.99))
        out = np.empty((n, T))
        prev = np.full(n, sp.mean)
        for t in range(T):
            z_ind = norm_ppf(g.uniform())
            z = rho * eq_shock[:, t] + np.sqrt(1 - rho ** 2) * z_ind
            prev = sp.mean + sp.persistence * (prev - sp.mean) + sp.sd * z
            out[:, t] = prev
        return out

    # -- main entry ------------------------------------------------------
    def generate(self, n_trials: int, T: int, seed: int):
        """Return dict with returns (n,T,A), inflation (n,T), regime, crash depth."""
        sp = self.spec
        if sp.mode == "fixed":
            r = np.tile(self.mu, (n_trials, T, 1))  # no regimes, no jumps
            infl = np.full((n_trials, T), sp.inflation.mean)
            return dict(returns=r, inflation=infl,
                        regime=np.ones((n_trials, T), dtype=np.int8),
                        crash=np.zeros((n_trials, T)), shrinkage=0.0)
        if sp.mode == "path":
            p = np.asarray(sp.fixed_path, dtype=float).reshape(-1, self.A)
            idx = np.arange(T) % len(p)
            r = np.tile(p[idx], (n_trials, 1, 1))
            infl = self._inflation_path(n_trials, T, seed, np.zeros((n_trials, T)))
            return dict(returns=r, inflation=infl,
                        regime=np.ones((n_trials, T), dtype=np.int8),
                        crash=np.zeros((n_trials, T)), shrinkage=0.0)
        if sp.mode == "historical":
            return self._bootstrap(n_trials, T, seed)

        regime = self._regime_path(n_trials, T, seed)
        gz = LEcuyer(seed, n_trials, "asset")
        gc = LEcuyer(seed, n_trials, "chi2")
        nu_k = max(1, int(round(sp.nu)))
        ret = np.empty((n_trials, T, self.A))
        eq_shock = np.empty((n_trials, T))
        for t in range(T):
            u = gz.uniforms(self.A)
            if sp.antithetic:                      # mirror the odd-numbered trials
                u[1::2] = 1.0 - u[1::2]
            z = norm_ppf(u)
            if sp.dist == "t":
                cu = gc.uniforms(nu_k)
                z = np.stack([student_t(z[:, j], cu, sp.nu) for j in range(self.A)], axis=1)
            eps = np.empty_like(z)
            for k, L in enumerate(self.chol):      # correlate within each regime
                m = regime[:, t] == k
                if m.any():
                    eps[m] = z[m] @ L.T
            eq_shock[:, t] = eps[:, 0]
            off = self.offsets[regime[:, t]]                       # (n, A)
            vm = np.array([sp.regimes[k].vol_mult for k in regime[:, t]])[:, None]
            m_t = self.mu_eff[None, :] + off
            s_t = self.sigma[None, :] * vm
            if sp.dist == "normal":
                ret[:, t, :] = m_t + s_t * eps
            else:
                ml, sl = _log_params(m_t, s_t)
                ret[:, t, :] = np.exp(ml + sl * eps) - 1.0
        shock, depth = self._crash_path(n_trials, T, seed)
        ret = (1.0 + ret) * (1.0 - shock[:, :, None] * self.beta[None, None, :]) - 1.0
        ret = np.maximum(ret, -0.995)
        infl = self._inflation_path(n_trials, T, seed, eq_shock)
        return dict(returns=ret, inflation=infl, regime=regime, crash=depth,
                    shrinkage=max(self.shrinkage))

    def _bootstrap(self, n_trials, T, seed):
        hist = np.asarray(self.spec.historical, dtype=float).reshape(-1, self.A)
        if len(hist) < 2:
            raise ValueError("historical mode needs at least 2 rows of data")
        L = max(1, int(self.spec.block_length))
        g = LEcuyer(seed, n_trials, "asset")
        nb = int(np.ceil(T / L))
        idx = np.empty((n_trials, nb * L), dtype=int)
        for b in range(nb):
            start = (g.uniform() * (len(hist) - L + 1)).astype(int)
            for j in range(L):
                idx[:, b * L + j] = (start + j) % len(hist)
        idx = idx[:, :T]
        ret = hist[idx]
        infl = self._inflation_path(n_trials, T, seed, np.zeros((n_trials, T)))
        return dict(returns=ret, inflation=infl,
                    regime=np.ones((n_trials, T), dtype=np.int8),
                    crash=np.zeros((n_trials, T)), shrinkage=0.0)
