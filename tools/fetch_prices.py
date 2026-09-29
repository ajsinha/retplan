#!/usr/bin/env python3
"""Collect today's prices once - for cron, instead of (or as well as) the web app's
built-in daily schedule.

    python tools/fetch_prices.py                 # every held symbol
    python tools/fetch_prices.py VTI BND         # just these
    python tools/fetch_prices.py --prune-only    # only delete closes past retention

    # crontab: weekdays at 18:30
    30 18 * * 1-5  cd /path/to/retplan && .venv/bin/python tools/fetch_prices.py

Uses the database in config/retplan.toml (or RETPLAN_DATABASE_URL).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from portfolio.db import Database  # noqa: E402
from portfolio.prices import PriceCollector  # noqa: E402
from portfolio.repository import PortfolioRepo  # noqa: E402
from web.config import load_config  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Collect daily prices once.")
    ap.add_argument("symbols", nargs="*", help="default: every symbol held anywhere")
    ap.add_argument("--prune-only", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    repo = PortfolioRepo(Database(cfg.database_url))
    if args.prune_only:
        print(f"pruned {repo.prune(cfg.prices_retention_days)} rows")
        return 0
    res = PriceCollector(repo, retention_days=cfg.prices_retention_days).collect(
        args.symbols or None, reason="cli")
    print(f"{res['ok']} ok, {res['failed']} failed, {res['rows_added']} rows written, "
          f"{res['rows_pruned']} pruned")
    for e in res["errors"]:
        print("  " + e)
    return 1 if res["failed"] and not res["ok"] else 0


if __name__ == "__main__":
    sys.exit(main())
