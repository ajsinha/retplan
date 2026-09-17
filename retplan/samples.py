"""The worked sample household, shared by the workbook and the web app.

Fictional, but deliberately not a toy: two earners retiring at different times,
six accounts across four tax wrappers, a mortgage, a lumpy car-replacement cycle,
education costs, and a state pension with survivor continuation.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

from .markets import (AssetClass, CrashSpec, InflationSpec, MarketSpec, Regime)
from .plan import (ExpenseRow, IncomeRow, Ledger, Loan, Person, Plan, Policy,
                   SmileCurve, Wrapper)
from .tax import Schedule, TaxSystem


def sample_assets():
    return [
        AssetClass("Global equity", 0.070, 0.170, 0.020, 0.0020, 1.00),
        AssetClass("Government bonds", 0.035, 0.060, 0.030, 0.0015, -0.15),
        AssetClass("Corporate credit", 0.045, 0.080, 0.040, 0.0025, 0.40),
        AssetClass("Property", 0.055, 0.130, 0.035, 0.0060, 0.60),
        AssetClass("Cash", 0.020, 0.010, 0.020, 0.0010, 0.00),
        AssetClass("Alternatives", 0.060, 0.150, 0.010, 0.0090, 0.50),
    ]


def sample_corr():
    return [
        [1.00, 0.10, 0.45, 0.60, 0.00, 0.50],
        [0.10, 1.00, 0.60, 0.15, 0.20, 0.05],
        [0.45, 0.60, 1.00, 0.35, 0.10, 0.25],
        [0.60, 0.15, 0.35, 1.00, 0.05, 0.35],
        [0.00, 0.20, 0.10, 0.05, 1.00, 0.00],
        [0.50, 0.05, 0.25, 0.35, 0.00, 1.00],
    ]


def sample_regimes():
    return [
        Regime("Bear", -0.22, 1.90, 0.55, [0.50, 0.45, 0.05]),
        Regime("Normal", 0.00, 1.00, 0.00, [0.10, 0.80, 0.10]),
        Regime("Bull", 0.08, 0.80, 0.00, [0.04, 0.26, 0.70]),
    ]


def sample_wrappers():
    return [
        Wrapper("Taxable brokerage", 0.0, True, 1.0, 0.0, True, "none", 0,
                200, 0, 0, 0.0, 999, [], 0, 0.0, True),
        Wrapper("Pension (EET)", 1.0, False, 0.0, 1.0, False, "pct_income", 0.20,
                50, 8000, 60, 0.10, 75,
                [(75, 24.6), (80, 20.2), (85, 16.0), (90, 12.2), (95, 8.9),
                 (100, 6.4), (105, 4.6), (110, 3.5)], 55, 0.0, True),
        Wrapper("Tax-free account (TEE)", 0.0, False, 0.0, 0.0, False, "absolute",
                20000, 200, 0, 0, 0.0, 999, [], 0, 0.0, True),
        Wrapper("Cash savings", 0.0, True, 1.0, 0.0, False, "none", 0, 200, 0, 0,
                0.0, 999, [], 0, 0.0, True),
        Wrapper("Property (illiquid)", 0.0, False, 0.0, 0.0, True, "none", 0, 200,
                0, 0, 0.0, 999, [], 0, 0.0, False),
    ]


def sample_plan() -> Plan:
    """A complete, plausible household. Every number here is made up."""
    eq = [0.70, 0.20, 0.05, 0.05, 0.00, 0.00]
    eq_glide = [0.45, 0.40, 0.10, 0.05, 0.00, 0.00]
    pen = [0.80, 0.15, 0.00, 0.05, 0.00, 0.00]
    pen_glide = [0.45, 0.45, 0.05, 0.05, 0.00, 0.00]
    tfa = [0.85, 0.10, 0.00, 0.05, 0.00, 0.00]
    tfa_glide = [0.55, 0.35, 0.05, 0.05, 0.00, 0.00]
    cash = [0.00, 0.00, 0.00, 1.00, 0.00, 0.00]
    prop = [0.00, 0.00, 1.00, 0.00, 0.00, 0.00]

    return Plan(
        label="Sample household",
        horizon=60,
        persons=[Person("Person 1", 45, 65, 95), Person("Person 2", 43, 65, 97)],
        income=[
            IncomeRow("Salary - person 1", 0, "employment", 95000, "real", 0.010,
                      False, 45, 65, 1.0, 0.0, 1.0),
            IncomeRow("Salary - person 2", 1, "employment", 62000, "real", 0.005,
                      False, 43, 65, 1.0, 0.0, 1.0),
            IncomeRow("State pension - person 1", 0, "state_pension", 11500, "real",
                      0.0, False, 67, 130, 1.0, 0.5, 1.0),
            IncomeRow("State pension - person 2", 1, "state_pension", 11500, "real",
                      0.0, False, 67, 130, 1.0, 0.5, 1.0),
            IncomeRow("Final salary pension", 0, "db_pension", 9000, "real", 0.0,
                      False, 65, 130, 1.0, 0.5, 1.0),
            IncomeRow("Rental income (net)", 0, "rental", 8400, "real", 0.0, False,
                      45, 130, 1.0, 1.0, 1.0),
            IncomeRow("Part-time consulting", 0, "self_employment", 18000, "real",
                      0.0, False, 65, 70, 1.0, 0.0, 1.0),
        ],
        expenses=[
            ExpenseRow("Housing, utilities, tax", 14000, "real", True, 0.0, False,
                       45, 130, 0, 0, 1.0),
            ExpenseRow("Food and household", 9000, "real", True, 0.0, False,
                       45, 130, 0, 0, 1.0),
            ExpenseRow("Transport", 5200, "real", True, 0.0, True, 45, 130, 0, 0, 1.0),
            ExpenseRow("Insurance and health", 3600, "real", True, 0.02, False,
                       45, 130, 0, 0, 1.0),
            ExpenseRow("Travel and leisure", 9000, "real", False, 0.0, True,
                       45, 85, 0, 0, 1.0),
            ExpenseRow("Hobbies, gifts, other", 6000, "real", False, 0.0, True,
                       45, 130, 0, 0, 1.0),
            ExpenseRow("Car replacement", 22000, "real", False, 0.0, False,
                       46, 86, 0, 8, 1.0),
            ExpenseRow("Home maintenance", 3000, "real", True, 0.0, False,
                       45, 130, 0, 0, 1.0),
            ExpenseRow("University support", 12000, "real", False, 0.03, False,
                       50, 54, 0, 0, 1.0),
        ],
        loans=[Loan("Mortgage", 185000, 0.042, 17, "amortising", 0.0, 0)],
        wrappers=sample_wrappers(),
        ledgers=[
            Ledger("Joint brokerage", 0, 0, 120000, 95000, eq, eq_glide, 55, 75,
                   1, 4, 6000, 0.0, 0.0, 0.0, "annual"),
            Ledger("Workplace pension P1", 1, 0, 310000, 0, pen, pen_glide, 55, 70,
                   3, 1, 0, 0.08, 1.0, 0.05, "annual"),
            Ledger("Workplace pension P2", 1, 1, 185000, 0, pen, pen_glide, 55, 70,
                   4, 2, 0, 0.06, 1.0, 0.04, "annual"),
            Ledger("Tax-free account", 2, 0, 95000, 95000, tfa, tfa_glide, 55, 75,
                   2, 3, 4000, 0.0, 0.0, 0.0, "annual"),
            Ledger("Cash reserve", 3, 0, 35000, 35000, cash, [], 55, 75,
                   5, 5, 0, 0.0, 0.0, 0.0, "annual"),
            Ledger("Rental property", 4, 0, 240000, 180000, prop, [], 55, 75,
                   6, 6, 0, 0.0, 0.0, 0.0, "none"),
        ],
        market=MarketSpec(
            mode="mc", dist="lognormal", nu=5.0, assets=sample_assets(),
            corr=sample_corr(), regimes=sample_regimes(),
            start_regime="stationary", crash=CrashSpec(),
            inflation=InflationSpec(mode="fixed", mean=0.025, sd=0.012,
                                    persistence=0.55, corr_equity=-0.20)),
        tax=TaxSystem(
            ordinary=Schedule("Ordinary income",
                              [0, 12570, 50270, 100000, 125140],
                              [0.00, 0.20, 0.40, 0.60, 0.45]),
            capital=Schedule("Capital", [0.0], [0.0]),
            cg_inclusion=1.0, index_bands=True),
        policy=Policy(method="fixed_real", pct=0.04, vpw_rate=0.035,
                      legacy_target=0.0, confidence=0.85, discount_rate=0.03,
                      sweep_ledger=0),
        smile=SmileCurve([55, 65, 75, 85, 95, 105],
                         [1.00, 1.00, 0.94, 0.86, 0.88, 0.88]),
        platform_fee=0.0025, adviser_fee=0.0, timing="end", seed=20260916)
