"""Plan configuration objects.  Everything the model knows is data on these."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict, is_dataclass
import json

import numpy as np

from .markets import (AssetClass, CrashSpec, InflationSpec, MarketSpec, Regime)
from .tax import Schedule, TaxSystem

CATEGORIES = ["employment", "self_employment", "rental", "db_pension",
              "state_pension", "annuity", "other_taxable", "tax_free", "one_off"]


@dataclass
class Person:
    label: str = "Person 1"
    age: float = 40.0            # age at plan start
    retire_age: float = 65.0
    death_age: float = 95.0
    included: bool = True


@dataclass
class IncomeRow:
    label: str = "Salary"
    owner: int = 0
    category: str = "employment"
    amount: float = 0.0
    basis: str = "real"          # real (today's money) | nominal
    growth: float = 0.0          # growth in that basis, per year
    grow_from_start: bool = False
    start_age: float = 0.0       # owner's age when the stream starts
    end_age: float = 200.0
    taxable_fraction: float = 1.0
    survivor_fraction: float = 0.0   # share continuing after the owner's death
    probability: float = 1.0
    enabled: bool = True


@dataclass
class ExpenseRow:
    label: str = "Living costs"
    amount: float = 0.0
    basis: str = "real"
    essential: bool = True
    infl_delta: float = 0.0      # real growth above (or below) CPI
    smile: bool = False          # subject to the age spending curve
    start_age: float = 0.0
    end_age: float = 200.0
    owner: int = -1              # -1 = household
    recur_years: int = 0         # 0 = every year; n = every n years (one-offs)
    probability: float = 1.0
    enabled: bool = True


@dataclass
class Loan:
    label: str = "Mortgage"
    balance: float = 0.0
    rate: float = 0.04           # nominal annual
    term_years: int = 20
    kind: str = "amortising"     # amortising | interest_only | bullet
    extra_payment: float = 0.0   # nominal, per year
    start_year: int = 0
    enabled: bool = True


@dataclass
class Wrapper:
    """A generic tax wrapper.  EET, TEE, TTE and ETT are all special cases."""
    label: str = "Taxable"
    contribution_deductible: float = 0.0   # share of contributions deducted
    growth_taxed_annually: bool = True     # interest/dividends taxed as they arise
    growth_taxable_fraction: float = 1.0
    withdrawal_taxable_fraction: float = 0.0
    realises_capital_gains: bool = True
    cap_type: str = "none"       # none | absolute | pct_income
    cap_value: float = 0.0
    catch_up_age: float = 200.0
    catch_up_amount: float = 0.0
    early_age: float = 0.0
    early_penalty: float = 0.0
    mrd_age: float = 200.0
    mrd_divisors: list = field(default_factory=list)   # [(age, divisor), ...]
    lock_age: float = 0.0
    tax_free_lump_sum: float = 0.0
    liquid: bool = True


@dataclass
class Ledger:
    """An account, or a group of accounts sharing a wrapper and an allocation."""
    label: str = "Brokerage"
    wrapper: int = 0
    owner: int = 0
    opening: float = 0.0
    basis: float = 0.0           # cost basis, for capital gains
    weights: list = field(default_factory=lambda: [1.0])
    glide_to: list = field(default_factory=list)       # target weights at the end
    glide_start_age: float = 200.0
    glide_end_age: float = 200.0
    withdraw_priority: int = 1
    contribute_priority: int = 1
    contribution: float = 0.0    # regular contribution, real terms per year
    contribution_pct_income: float = 0.0
    employer_match_pct: float = 0.0
    employer_match_cap_pct: float = 0.0
    rebalance: str = "annual"    # annual | none
    enabled: bool = True


@dataclass
class Policy:
    method: str = "fixed_real"   # fixed_real | fixed_nominal | pct_portfolio | vpw |
                                 # guardrails | table
    pct: float = 0.04
    vpw_rate: float = 0.035
    guard_up: float = 0.20
    guard_down: float = 0.20
    guard_cut: float = 0.10
    guard_raise: float = 0.10
    guard_final_years: int = 15
    inflation_skip: bool = True
    legacy_target: float = 0.0   # real terminal wealth required for "success"
    cash_buffer_years: float = 0.0
    sweep_ledger: int = 0        # index of the account unspent income flows into
    confidence: float = 0.85
    discount_rate: float = 0.03


@dataclass
class SmileCurve:
    ages: list = field(default_factory=lambda: [55, 65, 75, 85, 95])
    mult: list = field(default_factory=lambda: [1.00, 1.00, 0.92, 0.85, 0.88])


@dataclass
class Plan:
    label: str = "Base"
    horizon: int = 60
    persons: list = field(default_factory=lambda: [Person()])
    income: list = field(default_factory=list)
    expenses: list = field(default_factory=list)
    loans: list = field(default_factory=list)
    wrappers: list = field(default_factory=lambda: [Wrapper()])
    ledgers: list = field(default_factory=lambda: [Ledger()])
    market: MarketSpec = field(default_factory=MarketSpec)
    tax: TaxSystem = field(default_factory=TaxSystem)
    policy: Policy = field(default_factory=Policy)
    smile: SmileCurve = field(default_factory=SmileCurve)
    platform_fee: float = 0.0025
    adviser_fee: float = 0.0
    timing: str = "end"          # begin | mid | end
    seed: int = 20260916


# --- (de)serialisation ----------------------------------------------------
_TYPES = {
    "persons": Person, "income": IncomeRow, "expenses": ExpenseRow, "loans": Loan,
    "wrappers": Wrapper, "ledgers": Ledger, "assets": AssetClass, "regimes": Regime,
}


def to_dict(obj):
    if is_dataclass(obj):
        return {k: to_dict(v) for k, v in asdict(obj).items()}
    if isinstance(obj, (list, tuple)):
        return [to_dict(v) for v in obj]
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    return obj


def _build(cls, d):
    if not isinstance(d, dict):
        return d
    fields = {f for f in cls.__dataclass_fields__}
    return cls(**{k: v for k, v in d.items() if k in fields})


def plan_from_dict(d: dict) -> Plan:
    p = Plan()
    for key, cls in _TYPES.items():
        if key in d:
            setattr(p, key, [_build(cls, x) for x in d[key]])
    for key in ("label", "horizon", "platform_fee", "adviser_fee", "timing", "seed"):
        if key in d:
            setattr(p, key, d[key])
    if "policy" in d:
        p.policy = _build(Policy, d["policy"])
    if "smile" in d:
        p.smile = _build(SmileCurve, d["smile"])
    if "market" in d:
        m = dict(d["market"])
        assets = [_build(AssetClass, a) for a in m.pop("assets", [])] or [AssetClass()]
        regimes = [_build(Regime, r) for r in m.pop("regimes", [])] or [Regime()]
        crash = _build(CrashSpec, m.pop("crash", {}))
        infl = _build(InflationSpec, m.pop("inflation", {}))
        p.market = _build(MarketSpec, m)
        p.market.assets, p.market.regimes = assets, regimes
        p.market.crash, p.market.inflation = crash, infl
    if "tax" in d:
        t = dict(d["tax"])
        ordinary = _build(Schedule, t.pop("ordinary", {}))
        capital = _build(Schedule, t.pop("capital", {}))
        p.tax = _build(TaxSystem, t)
        p.tax.ordinary, p.tax.capital = ordinary, capital
    return p


def load_plan(path) -> Plan:
    with open(path) as fh:
        return plan_from_dict(json.load(fh))


def save_plan(plan: Plan, path):
    with open(path, "w") as fh:
        json.dump(to_dict(plan), fh, indent=2)
