"""Per-session plan storage.

The browser session holds nothing but an opaque id; the plan itself lives
server-side as JSON on disk, so a cookie never carries someone's finances and a
restart does not lose their work. Simulation results are large and cheap to
recompute, so they stay in memory only and are dropped when the inputs change.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import uuid

from retplan.plan import Plan, load_plan, plan_from_dict, save_plan, to_dict
from retplan.samples import sample_plan

logger = logging.getLogger(__name__)
SESSION_KEY = "rp_sid"


def session_id(request) -> str:
    sid = request.session.get(SESSION_KEY)
    if not sid:
        sid = uuid.uuid4().hex
        request.session[SESSION_KEY] = sid
    return sid


class PlanStore:
    """Plans on disk, results in memory, one lock around both."""

    def __init__(self, data_dir: str):
        self.dir = data_dir
        os.makedirs(self.dir, exist_ok=True)
        self._results: dict[str, dict] = {}
        self._lock = threading.RLock()

    def _path(self, sid: str) -> str:
        safe = "".join(c for c in sid if c.isalnum())[:64] or "default"
        return os.path.join(self.dir, f"{safe}.json")

    def get(self, sid: str) -> Plan:
        path = self._path(sid)
        with self._lock:
            if os.path.exists(path):
                try:
                    return load_plan(path)
                except Exception as exc:  # noqa: BLE001 - never lose the session
                    logger.error("plan %s unreadable, starting from the sample: %s",
                                 sid, exc)
            plan = sample_plan()
            save_plan(plan, path)
            return plan

    def put(self, sid: str, plan: Plan) -> None:
        with self._lock:
            save_plan(plan, self._path(sid))
            self._results.pop(sid, None)      # inputs changed; results are stale

    def reset(self, sid: str) -> Plan:
        with self._lock:
            plan = sample_plan()
            save_plan(plan, self._path(sid))
            self._results.pop(sid, None)
            return plan

    def clear(self, sid: str) -> Plan:
        """An empty plan - for someone who would rather start from nothing."""
        with self._lock:
            plan = sample_plan()
            plan.label = "My plan"
            plan.income, plan.expenses, plan.loans = [], [], []
            for lg in plan.ledgers:
                lg.opening, lg.basis, lg.contribution = 0.0, 0.0, 0.0
                lg.contribution_pct_income = 0.0
            save_plan(plan, self._path(sid))
            self._results.pop(sid, None)
            return plan

    # -- simulation results ------------------------------------------------
    def results(self, sid: str):
        with self._lock:
            return self._results.get(sid)

    def set_results(self, sid: str, payload: dict) -> None:
        with self._lock:
            self._results[sid] = payload

    def drop_results(self, sid: str) -> None:
        with self._lock:
            self._results.pop(sid, None)

    def export_json(self, sid: str) -> str:
        return json.dumps(to_dict(self.get(sid)), indent=2)

    def import_json(self, sid: str, text: str) -> Plan:
        plan = plan_from_dict(json.loads(text))
        self.put(sid, plan)
        return plan
