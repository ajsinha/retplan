"""Case studies: worked households carried through RetPlan end to end.

Each case is a household built by the quick-start wizard's own plan builder, a
short story, and the questions worth asking of it. The figures on a case page are
computed when the page is shown - by the same engine, on a fixed seed - so the text
never quotes a number the model would not give today. Any case can be opened as a
scenario in the reader's own workspace and changed from there.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import threading

from web import levers, wizard

CASES: list[dict] = [
    dict(
        slug="early-retirement",
        title="Retiring at 60 with a pension gap",
        icon="bi-sunrise",
        summary="A couple who want to stop at 60 and 58, seven years before their public "
                "pensions start. Can the savings bridge the gap - and should they convert?",
        answers=dict(wizard.DEFAULTS, name="Case: retire at 60", age="52", retire_age="60",
                     plan_to="95", partner="1", p2_age="50", p2_retire_age="58",
                     p2_plan_to="96", salary="110000", salary_growth="1", p2_salary="65000",
                     pension="24000", pension_age="67", p2_pension="16000", p2_pension_age="67",
                     taxable="180000", deferred="720000", taxfree="140000", cash="40000",
                     save_pct="10", employer_pct="5", save_amount="12000", spend="85000",
                     retire_spend_pct="85", essential_pct="55", mortgage="120000",
                     mortgage_rate="3.5", mortgage_years="9", risk="balanced", tax="sample",
                     inflation="2.5"),
        story=[
            "Both work until their late fifties and have saved steadily, most of it in "
            "workplace accounts taxed on the way out. Their public pensions start at 67. "
            "Retiring at 60 and 58 leaves seven lean years with no pension income, paid for "
            "entirely from savings - and those are exactly the years in which a market fall "
            "does the most damage.",
            "Their mortgage ends a year after they stop working, and they plan to spend 85% "
            "of what they spend now.",
        ],
        questions=[
            ("Does the gap hold?", "Run the simulation and read the chance of success and the "
             "age the money runs out in a bad future. Then open the stress tests on any "
             "portfolio: the first seven years carry the risk."),
            ("What would help most?", "Find the levers. For this household, working a year or "
             "two longer and trimming spending usually lead - but see what your version says."),
            ("Should they convert?", "The gap years have low taxable income. The conversion "
             "explorer tries moving workplace money into the tax-free account between 60 and "
             "67, and compares strategies after the tax their heirs would still owe."),
            ("When to claim?", "With savings carrying the gap, claiming the public pension later "
             "raises lifelong income. The claiming explorer shows the trade-off on the whole "
             "plan."),
        ]),
    dict(
        slug="late-starter",
        title="A late starter at 52",
        icon="bi-hourglass-split",
        summary="Single, 52, with modest savings and fifteen working years left. How much "
                "does saving harder buy, and what retirement age makes it work?",
        answers=dict(wizard.DEFAULTS, name="Case: late starter", age="52", retire_age="67",
                     plan_to="92", partner="", salary="58000", salary_growth="0.5",
                     pension="14000", pension_age="67", taxable="8000", deferred="65000",
                     taxfree="12000", cash="6000", save_pct="6", employer_pct="3",
                     save_amount="1500", spend="42000", retire_spend_pct="80",
                     essential_pct="70", mortgage="0", risk="growth", tax="sample",
                     inflation="2.5"),
        story=[
            "A career break and a divorce left little in savings. Fifteen years of work remain, "
            "a public pension will cover about a third of today's spending, and most of what "
            "is spent is essential.",
            "The plan starts with a growth mix, because time is short and the savings are small "
            "- which also means a bad decade would hurt.",
        ],
        questions=[
            ("Where does it stand?", "Run the simulation. A plan like this often shows a good "
             "chance at typical growth and a much worse one across real futures - the gap is "
             "the sequence risk."),
            ("Is saving harder enough?", "Drag the saving slider: every extra amount saved is "
             "also an amount not spent, which lowers the spending the savings must replace."),
            ("What retirement age works?", "The solvers (Full analysis) find the earliest "
             "retirement age that meets the confidence target; the retire slider shows the "
             "odds at each age."),
            ("Is the mix right?", "Try 10% fewer shares in the levers. With little time, "
             "a gentler mix can raise the odds even as it lowers the median."),
        ]),
    dict(
        slug="drawdown-crash",
        title="Retired at 68 and worried about a crash",
        icon="bi-cloud-lightning-rain",
        summary="Already retired, drawing an income from savings. What would a 2008 in the "
                "first years do, and how much can safely be spent?",
        answers=dict(wizard.DEFAULTS, name="Case: retired, crash-worried", age="68",
                     retire_age="68", plan_to="96", partner="1", p2_age="66",
                     p2_retire_age="66", p2_plan_to="97", salary="0", p2_salary="0",
                     pension="21000", pension_age="68", p2_pension="11000",
                     p2_pension_age="67", taxable="260000", deferred="690000",
                     taxfree="210000", cash="60000", save_pct="0", employer_pct="0",
                     save_amount="0", spend="78000", retire_spend_pct="100",
                     essential_pct="60", mortgage="0", risk="balanced", tax="sample",
                     inflation="2.5"),
        story=[
            "Both have stopped work and draw on 1.2 million of savings alongside their "
            "pensions. They read that the first years of retirement decide how it goes, and "
            "want to know what a crash now would mean - and whether to spend less.",
        ],
        questions=[
            ("How exposed are they?", "Run the simulation and note the bad-luck final wealth. "
             "Then build their holdings as a portfolio and open the stress tests: how deep, "
             "and how long to recover."),
            ("How much can they spend?", "Full analysis finds the maximum sustainable spending "
             "at their confidence target; the spending slider shows the odds either side."),
            ("Would guardrails help?", "Change the withdrawal policy to guardrails (Plan → "
             "Withdrawal policy), save as a scenario, and compare: spending that flexes a "
             "little in bad years buys a lot of safety."),
        ]),
]

_CACHE: dict[str, dict] = {}
_LOCK = threading.Lock()


def get(slug: str) -> dict | None:
    return next((c for c in CASES if c["slug"] == slug), None)


def plan_for(case: dict):
    return wizard.build_plan(case["answers"])


def figures(case: dict) -> dict:
    """The case's headline numbers, computed once per process on a fixed seed."""
    with _LOCK:
        hit = _CACHE.get(case["slug"])
    if hit:
        return hit
    plan = plan_for(case)
    out = levers.run(plan, trials=1500)
    p0 = plan.persons[0]
    out.update(savings=sum(l.opening for l in plan.ledgers),
               spend=sum(e.amount for e in plan.expenses
                         if e.start_age <= p0.age < e.end_age and not e.recur_years),
               people=len(plan.persons))
    with _LOCK:
        _CACHE[case["slug"]] = out
    return out
