"""Deterministic random number generation.

Implements L'Ecuyer's 1988 combined multiplicative generator plus inverse-CDF
samplers, exactly as specified in docs/04-math-and-simulation.md section 2-3.

Why not numpy's Generator: the spreadsheet fallback and the Python engine must
produce *bit-identical* streams, so the algorithm has to be one that a cell
formula can also evaluate exactly in IEEE-754 doubles.  Every product below
stays under 2**53, so no rounding occurs anywhere.
"""
from __future__ import annotations

import numpy as np

M1, A1 = 2147483563, 40014
M2, A2 = 2147483399, 40692
MOD = 2147483562

# Fixed per-dimension stream offsets, so toggling one feature never reshuffles
# the draws of another (docs/04 section 2).
STREAM = {
    "asset": 0, "regime": 1, "crash_occur": 2, "crash_depth": 3,
    "inflation": 4, "longevity": 5, "expense_shock": 6, "one_off": 7,
    "chi2": 8, "ltc": 9,
}


def _splitmix64(x: np.ndarray) -> np.ndarray:
    """SplitMix64 finaliser: turns a counter into well-scattered 64-bit words.

    Needed because L'Ecuyer streams seeded by nearby values are lagged copies of
    one another and show measurable cross-correlation; scrambling the seeds
    first removes it (see tests/test_rng.py::test_streams_independent).
    """
    x = np.asarray(x, dtype=np.uint64).copy()
    x = (x + np.uint64(0x9E3779B97F4A7C15))
    x ^= x >> np.uint64(30)
    x *= np.uint64(0xBF58476D1CE4E5B9)
    x ^= x >> np.uint64(27)
    x *= np.uint64(0x94D049BB133111EB)
    x ^= x >> np.uint64(31)
    return x


class LEcuyer:
    """Vectorised combined MCG.  One instance holds `n` independent streams."""

    def __init__(self, seed: int, n: int = 1, stream: str | int = "asset"):
        off = STREAM.get(stream, 0) if isinstance(stream, str) else int(stream)
        i = np.arange(n, dtype=np.uint64)
        b = ((int(seed) & 0xFFFFFFFFFFFF) * 0x9E3779B97F4A7C15
             + (off + 1) * 0xD1342543DE82EF95) % (1 << 64)
        base = np.uint64(b)
        w1 = _splitmix64(base + i * np.uint64(0xA24BAED4963EE407))
        w2 = _splitmix64(w1 ^ np.uint64(0x165667B19E3779F9))
        self.s1 = (1 + (w1 % np.uint64(M1 - 1))).astype(np.int64)
        self.s2 = (1 + (w2 % np.uint64(M2 - 1))).astype(np.int64)
        for _ in range(8):           # warm-up, discard
            self.uniform()

    def uniform(self) -> np.ndarray:
        self.s1 = (self.s1 * A1) % M1
        self.s2 = (self.s2 * A2) % M2
        z = (self.s1 - self.s2) % MOD
        return (z + 1) / (M1 + 0.0)

    def uniforms(self, k: int = 1) -> np.ndarray:
        """Return an (n_streams, k) block of uniforms, column by column."""
        out = np.empty((self.s1.shape[0], int(k)), dtype=float)
        for j in range(int(k)):
            out[:, j] = self.uniform()
        return out


# --- Acklam's inverse normal CDF, refined by one Halley step ---------------
_A = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
      1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
_B = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
      6.680131188771972e+01, -1.328068155288572e+01]
_C = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
      -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
_D = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
      3.754408661907416e+00]
_PLOW, _PHIGH = 0.02425, 1 - 0.02425


def norm_ppf(u: np.ndarray) -> np.ndarray:
    """Inverse standard normal CDF.  |error| < 1e-15 after the Halley step."""
    u = np.clip(np.asarray(u, dtype=float), 1e-16, 1 - 1e-16)
    x = np.empty_like(u)

    lo = u < _PLOW
    if lo.any():
        q = np.sqrt(-2 * np.log(u[lo]))
        x[lo] = (((((_C[0]*q+_C[1])*q+_C[2])*q+_C[3])*q+_C[4])*q+_C[5]) / \
                ((((_D[0]*q+_D[1])*q+_D[2])*q+_D[3])*q+1)
    hi = u > _PHIGH
    if hi.any():
        q = np.sqrt(-2 * np.log(1 - u[hi]))
        x[hi] = -(((((_C[0]*q+_C[1])*q+_C[2])*q+_C[3])*q+_C[4])*q+_C[5]) / \
                 ((((_D[0]*q+_D[1])*q+_D[2])*q+_D[3])*q+1)
    mid = ~(lo | hi)
    if mid.any():
        q = u[mid] - 0.5
        r = q * q
        x[mid] = (((((_A[0]*r+_A[1])*r+_A[2])*r+_A[3])*r+_A[4])*r+_A[5])*q / \
                 (((((_B[0]*r+_B[1])*r+_B[2])*r+_B[3])*r+_B[4])*r+1)

    # One Halley refinement using the complementary error function.
    e = 0.5 * _erfc(-x / np.sqrt(2.0)) - u
    v = e * np.sqrt(2 * np.pi) * np.exp(x * x / 2.0)
    return x - v / (1 + x * v / 2)


def _erfc(x):
    return np.vectorize(_erfc_scalar, otypes=[float])(x) if np.ndim(x) else _erfc_scalar(x)


def _erfc_scalar(x: float) -> float:
    import math
    return math.erfc(x)


def triangular_ppf(u, lo, mode, hi):
    """Exact inverse CDF of the triangular distribution (docs/04 section 7)."""
    u = np.asarray(u, dtype=float)
    if hi <= lo:
        return np.full_like(u, lo)
    c = (mode - lo) / (hi - lo)
    left = lo + np.sqrt(np.clip(u, 0, 1) * (hi - lo) * (mode - lo))
    right = hi - np.sqrt(np.clip(1 - u, 0, 1) * (hi - lo) * (hi - mode))
    return np.where(u < c, left, right)


def student_t(z: np.ndarray, chi_u: np.ndarray, nu: float) -> np.ndarray:
    """Variance-matched Student-t from a normal draw and uniforms for chi-square.

    t = z / sqrt(W/nu) scaled by sqrt((nu-2)/nu) so the stated volatility still
    means what the user thinks it means.  Requires nu > 2.
    """
    if nu <= 2:
        raise ValueError("degrees of freedom must exceed 2 for finite variance")
    k = max(1, int(round(nu)))
    w = np.zeros_like(z)
    for j in range(k):                       # chi-square as a sum of squares
        w += norm_ppf(chi_u[..., j]) ** 2
    return z / np.sqrt(w / k) * np.sqrt((k - 2) / k)


def cholesky_psd(corr: np.ndarray, grid=None):
    """Cholesky with shrinkage repair.  Returns (L, lambda_applied)."""
    corr = np.asarray(corr, dtype=float)
    n = corr.shape[0]
    grid = grid if grid is not None else np.arange(0, 0.51, 0.01)
    eye = np.eye(n)
    for lam in grid:
        c = (1 - lam) * corr + lam * eye
        try:
            return np.linalg.cholesky(c), float(lam)
        except np.linalg.LinAlgError:
            continue
    return eye, 1.0
