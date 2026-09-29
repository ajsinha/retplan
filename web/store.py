"""Per-workspace plan storage: named scenarios in the database.

The browser session holds nothing but an opaque workspace id; plans live in the
``plans`` table as the JSON form of :class:`retplan.plan.Plan`, so a cookie never
carries someone's finances. A workspace can keep several plans ("scenarios") and
has exactly one active - the one the editor, dashboard and reports show.

Simulation results are large and cheap to recompute, so they stay in memory,
keyed by plan id, and are dropped whenever that plan changes.

Plans saved by earlier versions as ``data/plans/<workspace>.json`` are imported
the first time that workspace is seen.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import uuid

from portfolio.db import Database, utcnow
from retplan.plan import Plan, plan_from_dict, to_dict
from retplan.samples import sample_plan

logger = logging.getLogger(__name__)
SESSION_KEY = "rp_sid"


def session_id(request) -> str:
    sid = request.session.get(SESSION_KEY)
    if not sid:
        sid = uuid.uuid4().hex
        request.session[SESSION_KEY] = sid
    return sid


def blank_plan(name: str = "My plan") -> Plan:
    """The sample's assumptions (markets, tax, wrappers) with nothing personal."""
    plan = sample_plan()
    plan.label = name
    plan.income, plan.expenses, plan.loans = [], [], []
    for lg in plan.ledgers:
        lg.opening, lg.basis, lg.contribution = 0.0, 0.0, 0.0
        lg.contribution_pct_income = 0.0
    return plan


class PlanStore:
    """Plans in the database, results in memory, one lock around the results."""

    def __init__(self, db: Database, legacy_dir: str | None = None):
        self.db = db
        self.legacy_dir = legacy_dir
        self._results: dict[int, dict] = {}
        self._lock = threading.RLock()

    # -- scenarios ---------------------------------------------------------
    def scenarios(self, sid: str) -> list[dict]:
        self._active_row(sid)                     # make sure there is one
        return self.db.query("SELECT id, name, is_active, created_at, updated_at"
                             " FROM plans WHERE owner = :o ORDER BY created_at, id",
                             {"o": sid})

    def active_id(self, sid: str) -> int:
        return self._active_row(sid)["id"]

    def _active_row(self, sid: str) -> dict:
        row = self.db.one("SELECT * FROM plans WHERE owner = :o AND is_active = 1"
                          " ORDER BY id LIMIT 1", {"o": sid})
        if row:
            return row
        first = self.db.one("SELECT * FROM plans WHERE owner = :o ORDER BY id LIMIT 1",
                            {"o": sid})
        if first:
            self.activate(sid, first["id"])
            first["is_active"] = 1
            return first
        plan = self._legacy(sid) or sample_plan()
        pid = self.create(sid, plan.label or "Base", plan, activate=True)
        return self.db.one("SELECT * FROM plans WHERE id = :id", {"id": pid})

    def _legacy(self, sid: str) -> Plan | None:
        if not self.legacy_dir:
            return None
        safe = "".join(c for c in sid if c.isalnum())[:64]
        path = os.path.join(self.legacy_dir, f"{safe}.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as fh:
                plan = plan_from_dict(json.load(fh))
            logger.info("imported legacy plan file %s", path)
            return plan
        except Exception as exc:  # noqa: BLE001 - never lose the session over it
            logger.error("legacy plan %s unreadable: %s", path, exc)
            return None

    def create(self, sid: str, name: str, plan: Plan | None = None,
               activate: bool = True) -> int:
        plan = plan or blank_plan(name)
        plan.label = name
        now = utcnow()
        with self.db.tx() as c:
            if activate:
                Database.run(c, "UPDATE plans SET is_active = 0 WHERE owner = :o",
                             {"o": sid})
            return Database.insert(
                c, "INSERT INTO plans (owner, name, data, is_active, created_at,"
                   " updated_at) VALUES (:o, :n, :d, :a, :t, :t)",
                {"o": sid, "n": name, "d": json.dumps(to_dict(plan)),
                 "a": 1 if activate else 0, "t": now})

    def activate(self, sid: str, plan_id: int) -> None:
        with self.db.tx() as c:
            hit = Database.run(c, "SELECT id FROM plans WHERE id = :id AND owner = :o",
                               {"id": plan_id, "o": sid}).first()
            if hit is None:
                raise LookupError(f"plan {plan_id}")
            Database.run(c, "UPDATE plans SET is_active = CASE WHEN id = :id THEN 1"
                            " ELSE 0 END WHERE owner = :o", {"id": plan_id, "o": sid})

    def duplicate(self, sid: str, plan_id: int, name: str | None = None) -> int:
        src = self.get_by_id(sid, plan_id)
        return self.create(sid, name or f"{src.label} (copy)", src, activate=True)

    def rename(self, sid: str, plan_id: int, name: str) -> None:
        plan = self.get_by_id(sid, plan_id)
        plan.label = name.strip() or plan.label
        self._write(sid, plan_id, plan)

    def delete(self, sid: str, plan_id: int) -> None:
        if len(self.scenarios(sid)) <= 1:
            raise ValueError("a workspace keeps at least one plan")
        with self.db.tx() as c:
            Database.run(c, "DELETE FROM plans WHERE id = :id AND owner = :o",
                         {"id": plan_id, "o": sid})
        with self._lock:
            self._results.pop(plan_id, None)
        self._active_row(sid)

    def get_by_id(self, sid: str, plan_id: int) -> Plan:
        row = self.db.one("SELECT data FROM plans WHERE id = :id AND owner = :o",
                          {"id": plan_id, "o": sid})
        if row is None:
            raise LookupError(f"plan {plan_id}")
        return plan_from_dict(json.loads(row["data"]))

    def _write(self, sid: str, plan_id: int, plan: Plan) -> None:
        with self.db.tx() as c:
            Database.run(c, "UPDATE plans SET data = :d, name = :n, updated_at = :t"
                            " WHERE id = :id AND owner = :o",
                         {"d": json.dumps(to_dict(plan)), "n": plan.label,
                          "t": utcnow(), "id": plan_id, "o": sid})
        with self._lock:
            self._results.pop(plan_id, None)      # inputs changed; results are stale

    # -- the active plan (the API every page uses) ---------------------------
    def get(self, sid: str) -> Plan:
        row = self._active_row(sid)
        try:
            return plan_from_dict(json.loads(row["data"]))
        except Exception as exc:  # noqa: BLE001 - never lose the session
            logger.error("plan %s unreadable, showing the sample: %s", row["id"], exc)
            return sample_plan()

    def put(self, sid: str, plan: Plan) -> None:
        self._write(sid, self.active_id(sid), plan)

    def reset(self, sid: str) -> Plan:
        plan = sample_plan()
        plan.label = self.get(sid).label
        self.put(sid, plan)
        return plan

    def clear(self, sid: str) -> Plan:
        """An empty plan - for someone who would rather start from nothing."""
        plan = blank_plan(self.get(sid).label)
        self.put(sid, plan)
        return plan

    # -- simulation results ------------------------------------------------
    def results(self, sid: str):
        with self._lock:
            return self._results.get(self.active_id(sid))

    def results_for(self, plan_id: int):
        with self._lock:
            return self._results.get(plan_id)

    def set_results(self, sid: str, payload: dict, plan_id: int | None = None) -> None:
        with self._lock:
            self._results[plan_id or self.active_id(sid)] = payload

    def drop_results(self, sid: str) -> None:
        with self._lock:
            self._results.pop(self.active_id(sid), None)

    def export_json(self, sid: str) -> str:
        return json.dumps(to_dict(self.get(sid)), indent=2)

    def import_json(self, sid: str, text: str, as_new: bool = False) -> Plan:
        plan = plan_from_dict(json.loads(text))
        if as_new:
            self.create(sid, plan.label or "Imported plan", plan, activate=True)
        else:
            self.put(sid, plan)
        return plan
