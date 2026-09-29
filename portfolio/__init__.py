"""Portfolios: holdings, daily prices from Yahoo, and Monte Carlo projections.

    db          SQLAlchemy engine and schema bootstrap (SQLite or PostgreSQL)
    assets      asset classes, classification and long-run assumptions
    repository  every query about portfolios, holdings, securities and prices
    yahoo       a standard-library client for Yahoo's chart and search endpoints
    prices      the daily collector and its scheduler
    projection  the multi-asset Monte Carlo projection
    stress      historical crisis replays

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
