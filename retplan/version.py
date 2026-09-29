"""The single authority for RetPlan's version and what each release brought.

The about page's "In this release" is generated from HIGHLIGHTS, so a release
note cannot be forgotten in one place and remembered in another.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

__version__ = "2.0.0"
BUILD_DATE = "2026-09-29"

HIGHLIGHTS: dict[str, list[str]] = {
    "2.0.0": [
        "A web application in its own right: a database (SQLite or PostgreSQL, "
        "switched in config), MAYA's design, and no spreadsheet to maintain",
        "Portfolios priced daily from Yahoo, with currency conversion, risk checks, "
        "rebalancing and a copy into the plan",
        "The portfolio builder: upload a broker's positions export and review every "
        "identified security before it is saved",
        "Portfolio projections over 1-60 years with three market models, yearly or "
        "quarterly tables and five historical crisis replays",
        "Deciding, not only projecting: what-if sliders, your biggest levers, when to "
        "claim a public pension, and Roth-style conversions between any two accounts",
        "A quick-start wizard, named scenarios compared on one seed, a life timeline "
        "and a one-page plan report",
        "Model corrections: employer matches paid on top of saving; a funded ratio "
        "that counts forced withdrawals once; fixed-return projections at typical, "
        "not average, growth",
        "Securities: look up anything live; an administrator account manages the "
        "shared securities list, including manually priced assets",
    ],
    "1.0.0": [
        "The planning engine: real-terms projection, exact tax gross-up, Monte Carlo "
        "with regimes, crashes and fat tails, six withdrawal policies, solvers",
    ],
}
