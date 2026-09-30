"""What leaves the machine: names replaced, money rounded, holdings held back.

Everything the model sees - the plan summary in the system prompt and every tool
result - passes through a :class:`Redactor` built for that request:

- with ``assistant.privacy.share_names: false`` the people become "Person 1",
  "Person 2", accounts "Account 1"…, the plan "Your plan" and portfolios
  "Portfolio 1"…; any of those names inside other text (an income called
  "Maria's salary") is replaced too. The map stays in the request; the answer is
  turned back ("Person 1" -> "Maria") before it is shown;
- amounts of 1,000 or more are rounded to ``assistant.privacy.round_money_to``;
  ages, rates and shares are left alone;
- institutions are never sent.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import re


class Redactor:
    def __init__(self, share_names: bool = False, round_to: float = 1000):
        self.share_names = share_names
        self.round_to = round_to
        self.names: dict[str, str] = {}        # real -> placeholder

    def learn_plan(self, plan) -> "Redactor":
        if self.share_names:
            return self
        self._add(plan.label, "Your plan")
        for i, p in enumerate(plan.persons):
            self._add(p.label, f"Person {i + 1}")
        for i, lg in enumerate(plan.ledgers):
            self._add(lg.label, f"Account {i + 1}")
        for i, ln in enumerate(plan.loans):
            self._add(ln.label, f"Loan {i + 1}")
        return self

    def learn(self, name: str, placeholder: str) -> None:
        if not self.share_names:
            self._add(name, placeholder)

    def _add(self, name, placeholder):
        name = (name or "").strip()
        # generic words are not names worth hiding ("Brokerage", "Person 1")
        if len(name) < 3 or name == placeholder or name in self.names:
            return
        self.names[name] = placeholder

    # -- outbound ------------------------------------------------------------
    def text(self, s: str) -> str:
        if self.share_names or not s:
            return s
        for real in sorted(self.names, key=len, reverse=True):
            s = re.sub(re.escape(real), self.names[real], s, flags=re.IGNORECASE)
        return s

    def money(self, x: float) -> float:
        if self.round_to and abs(x) >= 1000:
            return round(x / self.round_to) * self.round_to
        return x

    def data(self, obj):
        """A tool result made safe to send: names replaced, money rounded."""
        if isinstance(obj, dict):
            return {k: self.data(v) for k, v in obj.items()
                    if k not in ("institution", "notes")}
        if isinstance(obj, (list, tuple)):
            return [self.data(v) for v in obj]
        if isinstance(obj, bool) or obj is None:
            return obj
        if isinstance(obj, float):
            v = self.money(obj)
            return round(v, 4) if abs(v) < 1000 else v
        if isinstance(obj, int):
            return int(self.money(obj)) if abs(obj) >= 1000 else obj
        if isinstance(obj, str):
            return self.text(obj)
        return obj

    # -- inbound -------------------------------------------------------------
    def restore(self, s: str) -> str:
        """The answer with placeholders turned back into the real names."""
        if self.share_names or not s:
            return s
        for real, ph in sorted(self.names.items(), key=lambda kv: -len(kv[1])):
            s = s.replace(ph, real)
        return s
