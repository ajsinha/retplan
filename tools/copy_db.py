#!/usr/bin/env python3
"""Copy every RetPlan table from one database to another (e.g. SQLite -> PostgreSQL).

    python tools/copy_db.py --to postgresql+psycopg://retplan:pw@localhost/retplan
    python tools/copy_db.py --from sqlite:///data/retplan.db --to sqlite:///backup.db

The source defaults to the configured database. The target is built from its own
schema file if empty, and must hold no RetPlan rows (refuses otherwise, so a
copy never merges into live data). Primary keys are kept, so links between
tables survive; on PostgreSQL the identity sequences are advanced past the
copied ids afterwards.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from portfolio.db import Database, declared_tables, schema_path  # noqa: E402
from web.config import load_config  # noqa: E402

# parents before children, so foreign keys hold at every insert
ORDER = ["plans", "portfolios", "securities", "holdings", "prices", "fetch_runs",
         "projections", "import_drafts", "app_settings"]
IDENTITY = ["plans", "portfolios", "holdings", "fetch_runs", "projections", "import_drafts"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--from", dest="src", default=None,
                    help="source database URL (default: the configured one)")
    ap.add_argument("--to", dest="dst", required=True, help="target database URL")
    ap.add_argument("--batch", type=int, default=2000)
    args = ap.parse_args()
    src = Database(args.src or load_config().database_url)
    dst = Database(args.dst)
    with open(schema_path(dst.dialect), encoding="utf-8") as fh:
        tables = declared_tables(fh.read())
    missing = [t for t in ORDER if t not in tables]
    if missing:
        print(f"schema file lacks {missing}; update ORDER in this tool", file=sys.stderr)
        return 2
    busy = {t: dst.scalar(f"SELECT COUNT(*) FROM {t}") for t in ORDER}
    busy = {t: n for t, n in busy.items() if n}
    if busy:
        print(f"refusing: the target already holds rows {busy}", file=sys.stderr)
        return 1
    print(f"copying {src.safe_url} -> {dst.safe_url}")
    for t in ORDER:
        rows = src.query(f"SELECT * FROM {t}")
        if not rows:
            print(f"  {t:12s} 0")
            continue
        cols = list(rows[0].keys())
        sql = text(f"INSERT INTO {t} ({', '.join(cols)}) VALUES "
                   f"({', '.join(':' + c for c in cols)})")
        with dst.tx() as c:
            for i in range(0, len(rows), args.batch):
                c.execute(sql, rows[i:i + args.batch])
        print(f"  {t:12s} {len(rows):,}")
    if dst.dialect == "postgresql":
        with dst.tx() as c:
            for t in IDENTITY:
                c.execute(text(f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), "
                               f"COALESCE((SELECT MAX(id) FROM {t}), 0) + 1, false)"))
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
