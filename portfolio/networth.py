"""Net worth over time.

Two kinds of record share the ``snapshots`` table:

- **manual** - a snapshot someone takes: each account's balance, each
  portfolio's value, other assets (a home, a car), and debts. One per day; taking
  another on the same day replaces it.
- **portfolio** - each portfolio's value, recorded automatically after every
  price collection. Daily prices are pruned after a year; these daily values are
  kept, so a portfolio's history grows for as long as RetPlan runs.

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

    def _upsert(self, owner, taken_on, kind, ref, assets, liabilities, data, note):
        with self.db.tx() as c:
            Database.run(c, "INSERT INTO snapshots (owner, taken_on, kind, ref, assets,"
                            " liabilities, data, note, created_at)"
                            " VALUES (:o, :d, :k, :r, :a, :l, :j, :n, :t)"
                            " ON CONFLICT (owner, taken_on, kind, ref) DO UPDATE SET"
                            " assets = excluded.assets, liabilities = excluded.liabilities,"
                            " data = excluded.data, note = excluded.note,"
                            " created_at = excluded.created_at",
                         {"o": owner, "d": taken_on, "k": kind, "r": str(ref), "a": float(assets),
                          "l": float(liabilities), "j": json.dumps(data), "n": note[:300],
                          "t": utcnow()})

    def record(self, owner: str, items: list[dict], taken_on: str | None = None,
               note: str = "") -> None:
        """A manual snapshot. items: [{name, kind: account|portfolio|asset|debt, value, ref?}]."""
        taken_on = taken_on or date.today().isoformat()
        date.fromisoformat(taken_on)                      # refuse a malformed date
        items = [dict(i, value=float(i.get("value") or 0.0)) for i in items
                 if str(i.get("name", "")).strip() and float(i.get("value") or 0.0) != 0.0]
        assets = sum(i["value"] for i in items if i["kind"] != "debt")
        debts = sum(abs(i["value"]) for i in items if i["kind"] == "debt")
        self._upsert(owner, taken_on, "manual", "", assets, debts, {"items": items}, note)

    def record_portfolio(self, owner: str, pid: int, value: float,
                         taken_on: str | None = None) -> None:
        self._upsert(owner, taken_on or date.today().isoformat(), "portfolio", pid, value,
                     0.0, {}, "")

    def manual(self, owner: str) -> list[dict]:
        rows = self.db.query("SELECT * FROM snapshots WHERE owner = :o AND kind = 'manual'"
                             " ORDER BY taken_on", {"o": owner})
        for r in rows:
            r["data"] = json.loads(r["data"] or "{}")
            r["net"] = r["assets"] - r["liabilities"]
        return rows

    def portfolio_series(self, owner: str) -> dict[str, list[tuple[str, float]]]:
        """{portfolio id: [(date, value)]} from the automatic records."""
        out: dict[str, list] = {}
        for r in self.db.query("SELECT ref, taken_on, assets FROM snapshots WHERE owner = :o"
                               " AND kind = 'portfolio' ORDER BY taken_on", {"o": owner}):
            out.setdefault(r["ref"], []).append((r["taken_on"], r["assets"]))
        return out

    def delete(self, owner: str, sid: int) -> None:
        with self.db.tx() as c:
            Database.run(c, "DELETE FROM snapshots WHERE id = :i AND owner = :o",
                         {"i": sid, "o": owner})

    def get(self, owner: str, sid: int) -> dict | None:
        r = self.db.one("SELECT * FROM snapshots WHERE id = :i AND owner = :o",
                        {"i": sid, "o": owner})
        if r:
            r["data"] = json.loads(r["data"] or "{}")
        return r


def record_all_portfolio_values(repo, networth: NetWorthRepo) -> int:
    """After a price run: today's value of every portfolio, in every workspace."""
    n = 0
    for row in repo.db.query("SELECT id, owner FROM portfolios"):
        try:
            v = repo.valuation(row["owner"], row["id"])
        except Exception:  # noqa: BLE001 - one bad portfolio never stops the rest
            logger.exception("valuing portfolio %s for the history failed", row["id"])
            continue
        if v.total > 0 and not v.unpriced:
            networth.record_portfolio(row["owner"], row["id"], v.total, v.as_of)
            n += 1
    return n
