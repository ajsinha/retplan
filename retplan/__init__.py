"""RetPlan - a jurisdiction-agnostic retirement planning engine.

The same code runs the deterministic projection and the Monte Carlo simulation
(a single trial is just n = 1), which keeps the two from drifting apart.
"""
from .version import BUILD_DATE, HIGHLIGHTS, __version__  # noqa: F401
