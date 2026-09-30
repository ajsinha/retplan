"""A plan's risks and gaps, found by rules - for the assistant to explain.

Each finding is computed here, from the plan and its last simulation, never by
the model: ``{"check", "severity": "high" | "medium" | "low", "finding",
"suggestion"}``. The model's job is to explain and prioritise them.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations


def _spend_at(plan, age: float) -> float:
    return sum(e.amount for e in plan.expenses
               if e.enabled and not (e.recur_years and e.recur_years > 1)
               and e.start_age <= age <= e.end_age)


def review(plan, results: dict | None = None) -> list[dict]:
    out = []
    p0 = plan.persons[0]
    now_age = p0.age

    def add(check, severity, finding, suggestion):
        out.append(dict(check=check, severity=severity, finding=finding, suggestion=suggestion))

    # health cover between retiring and public cover (Medicare at 65 in the US)
    early = [p for p in plan.persons if p.retire_age < 65 and p.age < 65]
    has_health = any("health" in e.label.lower() or "insurance" in e.label.lower()
                     or "medical" in e.label.lower() for e in plan.expenses if e.enabled)
    if early and not has_health:
        add("health cover before 65", "high",
            f"{', '.join(p.label for p in early)} retire"
            f"{'s' if len(early) == 1 and early[0].label.lower() != 'you' else ''} before 65 "
            "and the plan has no spending on health insurance.",
            "Add the cost of cover until public cover starts (the health and care tool does it).")

    # emergency cash
    cash = sum(lg.opening for lg in plan.ledgers if lg.enabled
               and "cash" in plan.wrappers[lg.wrapper].label.lower())
    monthly = _spend_at(plan, now_age) / 12
    if monthly > 0 and cash < 3 * monthly:
        add("emergency cash", "medium",
            f"Cash covers about {cash / monthly:.1f} months of spending.",
            "Three to six months in cash avoids selling investments in a fall.")

    # a survivor's income
    if len(plan.persons) > 1:
        lost = sum(r.amount * (1 - r.survivor_fraction) for r in plan.income
                   if r.enabled and r.category in ("state_pension", "db_pension", "annuity"))
        if lost > 0.25 * max(1.0, _spend_at(plan, max(now_age, p0.retire_age))):
            add("a survivor's income", "medium",
                f"If one of you dies, about {lost:,.0f} a year of pension income stops.",
                "Check the survivor's odds: pensions with survivor benefits, the higher earner "
                "claiming later, or life cover narrow the gap.")

    # required withdrawals
    big_deferred = sum(lg.opening for lg in plan.ledgers if lg.enabled
                       and plan.wrappers[lg.wrapper].mrd_age < 150)
    if big_deferred > 500_000:
        add("required withdrawals", "low",
            f"{big_deferred:,.0f} sits in accounts with required withdrawals.",
            "Large forced withdrawals later can raise your tax bracket; conversions in "
            "low-income years may pay (the conversion explorer compares them).")

    # risk near retirement
    labels = [a.label.lower() for a in plan.market.assets]
    eq = [i for i, lab in enumerate(labels) if any(w in lab for w in ("equity", "stock", "share"))]
    years_to_go = p0.retire_age - now_age
    if eq and 0 <= years_to_go <= 5:
        tot = sum(lg.opening for lg in plan.ledgers if lg.enabled and plan.wrappers[lg.wrapper].liquid)
        share = sum(lg.opening * sum(lg.weights[i] for i in eq if i < len(lg.weights))
                    for lg in plan.ledgers if lg.enabled and plan.wrappers[lg.wrapper].liquid)
        if tot and share / tot > 0.8:
            add("risk near retirement", "medium",
                f"{share / tot:.0%} of savings is in shares with {years_to_go:g} years to go.",
                "A fall just before or after retiring does the most damage; a glide path or a "
                "cash buffer softens it.")

    # essentials against income
    ess = sum(e.amount for e in plan.expenses if e.enabled and e.essential
              and e.start_age <= max(now_age, p0.retire_age) <= e.end_age)
    guaranteed = sum(r.amount for r in plan.income if r.enabled
                     and r.category in ("state_pension", "db_pension", "annuity"))
    if ess and guaranteed < 0.5 * ess:
        add("essentials and guaranteed income", "low",
            f"Guaranteed income ({guaranteed:,.0f}) covers {guaranteed / ess:.0%} of essential "
            f"spending ({ess:,.0f}).",
            "The rest depends on markets; claiming later or an annuity for part of it raises "
            "the floor.")

    # the odds against the target
    if results:
        k = results["kpis"]
        if k["success_probability"] < plan.policy.confidence:
            add("chance of success", "high",
                f"The chance of success is {k['success_probability']:.0%}, below the "
                f"{plan.policy.confidence:.0%} target.",
                "Find my levers or the strategy optimiser show what closes the gap.")
    else:
        add("not simulated", "low", "The plan has not been simulated yet.",
            "Run the simulation for its chance of success.")
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(out, key=lambda f: order[f["severity"]])
