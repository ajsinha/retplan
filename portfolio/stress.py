"""Historical crisis replays.

Each scenario is a sequence of *quarterly* total returns for five proxy classes -
US equity, US investment-grade bonds, cash, REITs and a broad commodity index -
over a real episode. Every holding follows the proxy of its asset class (see
``portfolio.assets``), scaled by a beta for classes that have no proxy of their
own, and the sequence can be replayed two ways:

- **alone**, as a deterministic path: how deep the fall, how long to recover at
  the expected return afterwards;
- **as the opening of every Monte Carlo trial**, which is the honest test of
  sequence risk: the crisis happens first, then the future is uncertain.

The figures are rounded approximations of the broad indices (S&P 500, Bloomberg
US Aggregate, 3-month T-bills, FTSE Nareit All Equity REITs, S&P GSCI), good to
roughly a percentage point per quarter. They are illustrations of the shape and
depth of each episode, not a data source. The 1973-74 episode is published as
annual figures and is spread evenly across the quarters of each year.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

PROXIES = ("equity", "bond", "cash", "property", "commodity")

# beta to the proxy, for classes that borrow another class's path
CLASS_PROXY = {
    "equity": ("equity", 1.00), "intl_equity": ("equity", 1.05),
    "em_equity": ("equity", 1.25), "bond": ("bond", 1.00), "cash": ("cash", 1.00),
    "property": ("property", 1.00), "commodity": ("commodity", 1.00),
    "crypto": ("equity", 2.50), "other": ("equity", 0.80),
}


def _even(annual: float, quarters: int = 4) -> list[float]:
    return [(1 + annual) ** (1 / quarters) - 1] * quarters


SCENARIOS: dict[str, dict] = {
    "gfc": dict(
        label="Global financial crisis (2007 Q4 - 2009 Q4)",
        short="2008 crisis",
        start="2007-10",
        blurb="Equities fell about 55% peak to trough; high-quality bonds rose.",
        returns=dict(
            equity=[-0.033, -0.094, -0.027, -0.084, -0.219, -0.110, 0.159, 0.156, 0.060],
            bond=[0.030, 0.022, -0.010, -0.005, 0.046, 0.001, 0.018, 0.037, 0.002],
            cash=[0.010, 0.006, 0.004, 0.004, 0.001, 0.001, 0.000, 0.000, 0.000],
            property=[-0.127, 0.014, -0.049, 0.056, -0.388, -0.319, 0.288, 0.333, 0.094],
            commodity=[0.120, 0.090, 0.270, -0.300, -0.440, -0.080, 0.180, 0.030, 0.080],
        )),
    "dotcom": dict(
        label="Dot-com bust (2000 Q2 - 2002 Q4)",
        short="Dot-com bust",
        start="2000-04",
        blurb="A slow, grinding fall of about 45% over two and a half years.",
        returns=dict(
            equity=[-0.027, -0.010, -0.078, -0.119, 0.059, -0.147, 0.107, 0.003,
                    -0.134, -0.173, 0.084],
            bond=[0.017, 0.030, 0.042, 0.030, 0.006, 0.046, 0.000, 0.001, 0.037,
                  0.046, 0.016],
            cash=[0.014, 0.015, 0.015, 0.012, 0.010, 0.008, 0.005, 0.004, 0.004,
                  0.004, 0.004],
            property=[0.100, 0.030, 0.040, 0.000, 0.090, 0.010, 0.030, 0.090, 0.050,
                      -0.090, 0.000],
            commodity=[0.150, 0.050, 0.100, -0.080, -0.050, -0.150, -0.100, 0.120,
                       0.080, 0.100, 0.050],
        )),
    "covid": dict(
        label="Covid crash (2020 Q1 - 2020 Q2)",
        short="Covid crash",
        start="2020-01",
        blurb="The fastest 30% fall on record, recovered within months.",
        returns=dict(
            equity=[-0.196, 0.205],
            bond=[0.031, 0.029],
            cash=[0.004, 0.000],
            property=[-0.273, 0.118],
            commodity=[-0.420, 0.100],
        )),
    "rates2022": dict(
        label="Rate shock (2022)",
        short="2022 rate shock",
        start="2022-01",
        blurb="Stocks and bonds fell together - the year a 60/40 portfolio had "
              "nowhere to hide.",
        returns=dict(
            equity=[-0.046, -0.161, -0.049, 0.076],
            bond=[-0.059, -0.047, -0.048, 0.019],
            cash=[0.000, 0.002, 0.005, 0.009],
            property=[-0.041, -0.170, -0.102, 0.041],
            commodity=[0.330, 0.020, -0.100, 0.030],
        )),
    "stagflation": dict(
        label="Stagflation (1973 - 1974)",
        short="1973-74 stagflation",
        start="1973-01",
        blurb="Two years of falling stocks and double-digit inflation; annual "
              "figures spread evenly across quarters.",
        returns=dict(
            equity=_even(-0.147) + _even(-0.265),
            bond=_even(0.023) + _even(0.002),
            cash=_even(0.069) + _even(0.080),
            property=_even(-0.156) + _even(-0.215),
            commodity=_even(0.750) + _even(0.390),
        )),
}

SCENARIO_OPTIONS = [(k, v["label"]) for k, v in SCENARIOS.items()]


def class_path(key: str, asset_class: str) -> list[float]:
    """Quarterly returns a holding of ``asset_class`` earns in scenario ``key``."""
    sc = SCENARIOS[key]
    proxy, beta = CLASS_PROXY.get(asset_class, CLASS_PROXY["other"])
    base = sc["returns"][proxy]
    if proxy == "cash" or beta == 1.0:
        return list(base)
    cash = sc["returns"]["cash"]
    # scale the excess over cash, so a beta of 2 doubles the risk, not the rate
    return [max(-0.95, c + beta * (r - c)) for r, c in zip(base, cash)]


def quarters(key: str) -> int:
    return len(SCENARIOS[key]["returns"]["equity"])
