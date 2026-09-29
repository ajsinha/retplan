"""Net worth over time.

A portfolio holds every account - investments, cash, property and debts - so its
valuation is a net worth. After every price collection each portfolio's assets
and debts are recorded in ``snapshots`` (kind ``portfolio``, one row a day), with
a breakdown by kind of account. Daily prices are pruned after a year; these
records are kept, so the history grows for as long as RetPlan runs.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import json
import logging
from datetime import date

from .db import Database, utcnow

logger = logging.getLogger(__name__)


class NetWorthRepo:
    def __init__(self, db: Database):
        self.db = db

    def record_portfolio(self, owner: str, pid: int, assets: float, debts: float = 0.0,
                         breakdown: dict | None = None, taken_on: str | None = None) -> None:
        """Today's (or a given day's) assets and debts for one portfolio."""
        taken_on = taken_on or date.today().isoformat()
        date.fromisoformat(taken_on)                      # refuse a malformed date
        with self.db.tx() as c:
            Database.run(c, "INSERT INTO snapshots (owner, taken_on, kind, ref, assets,"
                            " liabilities, data, note, created_at)"
                            " VALUES (:o, :d, 'portfolio', :r, :a, :l, :j, '', :t)"
                            " ON CONFLICT (owner, taken_on, kind, ref) DO UPDATE SET"
                            " assets = excluded.assets, liabilities = excluded.liabilities,"
                            " data = excluded.data, created_at = excluded.created_at",
                         {"o": owner, "d": taken_on, "r": str(pid), "a": float(assets),
                          "l": float(debts), "j": json.dumps(breakdown or {}),
                          "t": utcnow()})

    def history(self, owner: str, pid: int) -> list[dict]:
        """[{taken_on, assets, liabilities, net, data}] for one portfolio, oldest first."""
        rows = self.db.query("SELECT taken_on, assets, liabilities, data FROM snapshots"
                             " WHERE owner = :o AND kind = 'portfolio' AND ref = :r"
                             " ORDER BY taken_on", {"o": owner, "r": str(pid)})
        for r in rows:
            r["data"] = json.loads(r["data"] or "{}")
            r["net"] = r["assets"] - r["liabilities"]
        return rows

    def forget(self, owner: str, pid: int) -> None:
        with self.db.tx() as c:
            Database.run(c, "DELETE FROM snapshots WHERE owner = :o AND kind = 'portfolio'"
                            " AND ref = :r", {"o": owner, "r": str(pid)})


def breakdown(v) -> dict:
    """A valuation's totals by kind of account, for the history's stacked view."""
    return {"investments": v.kind_total("investments"), "cash": v.kind_total("cash"),
            "property": v.property_total, "debt": v.debts}


def record_one(repo, networth: NetWorthRepo, owner: str, pid: int) -> bool:
    v = repo.valuation(owner, pid)
    if v.unpriced or (v.assets <= 0 and v.debts <= 0):
        return False
    networth.record_portfolio(owner, pid, v.assets, v.debts, breakdown(v))
    return True


def record_all_portfolio_values(repo, networth: NetWorthRepo) -> int:
    """After a price run: today's net worth of every portfolio, in every workspace."""
    n = 0
    for row in repo.db.query("SELECT id, owner FROM portfolios"):
        try:
            n += record_one(repo, networth, row["owner"], row["id"])
        except Exception:  # noqa: BLE001 - one bad portfolio never stops the rest
            logger.exception("valuing portfolio %s for the history failed", row["id"])
    return n
