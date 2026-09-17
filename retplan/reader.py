"""Read a Plan out of an open LibreOffice document.

Deliberately free of any `uno` import: it only ever touches the document through
duck-typed calls, so it can be unit-tested against a stub and reused by the
cross-implementation check that proves the sheet and this engine agree.
"""
from __future__ import annotations

import numpy as np

from .markets import (AssetClass, CrashSpec, InflationSpec, MarketSpec, Regime)
from .plan import (ExpenseRow, IncomeRow, Ledger, Loan, Person, Plan, Policy,
                   SmileCurve, Wrapper)
from .tax import Schedule, TaxSystem

BLANK = ("", None)


def cells(doc, name):
    return doc.NamedRanges.getByName(name).ReferredCells


def arr(doc, name):
    """Flatten a named range to a list, preserving '' for blank cells."""
    rng = cells(doc, name)
    data = rng.getDataArray()
    if len(data) == 1:
        return list(data[0])
    if len(data[0]) == 1:
        return [row[0] for row in data]
    return [list(row) for row in data]


def val(doc, name, default=0.0):
    v = arr(doc, name)[0] if isinstance(arr(doc, name), list) else 0.0
    return default if v in BLANK else v


def num(doc, name, default=0.0):
    v = cells(doc, name).getCellByPosition(0, 0)
    return default if v.getString() == "" else v.getValue()


def txt(doc, name, default=""):
    return cells(doc, name).getCellByPosition(0, 0).getString() or default


def _f(v, default=0.0):
    return default if v in BLANK or isinstance(v, str) else float(v)


def _s(v, default=""):
    return v if isinstance(v, str) and v else default


def read_plan(doc) -> Plan:
    p = Plan()
    p.horizon = int(num(doc, "IN_HORIZON", 60))
    p.seed = int(num(doc, "IN_MKT_SEED", 1))
    p.timing = txt(doc, "IN_TIMING", "end")
    p.platform_fee = num(doc, "IN_FEE_PLATFORM")
    p.adviser_fee = num(doc, "IN_FEE_ADVISER")

    p.persons = [Person(txt(doc, "IN_P1_NAME", "Person 1"), num(doc, "IN_P1_AGE", 45),
                        num(doc, "IN_P1_RETIRE", 65), num(doc, "IN_P1_DEATH", 95))]
    if cells(doc, "IN_P2_AGE").getCellByPosition(0, 0).getString():
        p.persons.append(Person(txt(doc, "IN_P2_NAME", "Person 2"),
                                num(doc, "IN_P2_AGE"), num(doc, "IN_P2_RETIRE", 65),
                                num(doc, "IN_P2_DEATH", 95)))

    cat_map = {"employment": "employment", "self_employment": "self_employment"}
    en, own, cat, amt = (arr(doc, n) for n in ("INC_EN", "INC_OWN", "INC_CATT", "INC_AMT"))
    bas, g, gf = (arr(doc, n) for n in ("INC_BASIS", "INC_G", "INC_GFROM"))
    a0, a1, txf = (arr(doc, n) for n in ("INC_A0", "INC_A1", "INC_TAXF"))
    sv, prob = arr(doc, "INC_SURV"), arr(doc, "INC_PROB")
    for i in range(len(en)):
        if _s(en[i]) != "Yes" or _f(amt[i]) <= 0:
            continue
        p.income.append(IncomeRow(
            label=f"income {i+1}", owner=max(0, int(_f(own[i], 1)) - 1),
            category=_s(cat[i], "other_taxable"), amount=_f(amt[i]),
            basis=_s(bas[i], "real"), growth=_f(g[i]),
            grow_from_start=(_s(gf[i]) == "stream start"),
            start_age=_f(a0[i]), end_age=_f(a1[i], 200.0) or 200.0,
            taxable_fraction=1.0 if txf[i] in BLANK else _f(txf[i]),
            survivor_fraction=_f(sv[i]),
            probability=1.0 if prob[i] in BLANK else _f(prob[i])))

    en, amt, bas = (arr(doc, n) for n in ("EXP_EN", "EXP_AMT", "EXP_BASIS"))
    ess, d, sm = (arr(doc, n) for n in ("EXP_ESS", "EXP_D", "EXP_SM"))
    a0, a1, rec = (arr(doc, n) for n in ("EXP_A0", "EXP_A1", "EXP_REC"))
    own, prob = arr(doc, "EXP_OWN"), arr(doc, "EXP_PROB")
    for i in range(len(en)):
        if _s(en[i]) != "Yes" or _f(amt[i]) <= 0:
            continue
        p.expenses.append(ExpenseRow(
            label=f"expense {i+1}", amount=_f(amt[i]), basis=_s(bas[i], "real"),
            essential=(_s(ess[i]) == "Yes"), infl_delta=_f(d[i]),
            smile=(_s(sm[i]) == "Yes"), start_age=_f(a0[i]),
            end_age=_f(a1[i], 200.0) or 200.0, recur_years=int(_f(rec[i])),
            owner=max(0, int(_f(own[i], 1)) - 1),
            probability=1.0 if prob[i] in BLANK else _f(prob[i])))

    en, bal, r_, n_ = (arr(doc, x) for x in ("LN_EN", "LN_BAL", "LN_R", "LN_N"))
    kind, ex, st = (arr(doc, x) for x in ("LN_KIND", "LN_EX", "LN_ST"))
    for i in range(len(en)):
        if _s(en[i]) != "Yes" or _f(bal[i]) <= 0:
            continue
        p.loans.append(Loan(f"loan {i+1}", _f(bal[i]), _f(r_[i]),
                            max(1, int(_f(n_[i], 1))), _s(kind[i], "amortising"),
                            _f(ex[i]), int(_f(st[i]))))

    mrd_age, mrd_div = arr(doc, "MRD_AGE"), arr(doc, "MRD_DIV")
    mrd = [(_f(a), _f(v)) for a, v in zip(mrd_age, mrd_div)
           if a not in BLANK and _f(v) > 0]
    lab = arr(doc, "WR_LAB")
    cols = {k: arr(doc, f"WR_{k}") for k in
            ("DED", "GTX", "GTXF", "WTXF", "CG", "CAPT", "CAPV", "CUA", "CUV",
             "EA", "EP", "MRDA", "LOCK", "LIQ")}
    p.wrappers = []
    for i in range(len(lab)):
        p.wrappers.append(Wrapper(
            label=_s(lab[i], f"wrapper {i+1}"),
            contribution_deductible=_f(cols["DED"][i]),
            growth_taxed_annually=(_s(cols["GTX"][i]) == "Yes"),
            growth_taxable_fraction=_f(cols["GTXF"][i]),
            withdrawal_taxable_fraction=_f(cols["WTXF"][i]),
            realises_capital_gains=(_s(cols["CG"][i]) == "Yes"),
            cap_type=_s(cols["CAPT"][i], "none"), cap_value=_f(cols["CAPV"][i]),
            catch_up_age=_f(cols["CUA"][i], 200.0) or 200.0,
            catch_up_amount=_f(cols["CUV"][i]),
            early_age=_f(cols["EA"][i]), early_penalty=_f(cols["EP"][i]),
            mrd_age=_f(cols["MRDA"][i], 999.0) or 999.0, mrd_divisors=mrd,
            lock_age=_f(cols["LOCK"][i]),
            liquid=(_s(cols["LIQ"][i], "Yes") == "Yes")))

    n_asset = len(arr(doc, "AST_MU"))
    en = arr(doc, "LG_EN")
    base = {k: arr(doc, f"LG_{k}") for k in
            ("OWN", "WR", "OPEN", "BASIS", "GA0", "GA1", "WPRI", "CPRI", "CONTR",
             "CPCT", "MATCH", "MCAP", "REB")}
    wts = [arr(doc, f"LG_W{j+1}") for j in range(n_asset)]
    gls = [arr(doc, f"LG_V{j+1}") for j in range(n_asset)]
    p.ledgers = []
    for i in range(len(en)):
        if _s(en[i]) != "Yes":
            continue
        w = [_f(wts[j][i]) for j in range(n_asset)]
        v = [_f(gls[j][i]) for j in range(n_asset)]
        p.ledgers.append(Ledger(
            label=f"account {i+1}", wrapper=max(0, int(_f(base["WR"][i], 1)) - 1),
            owner=max(0, int(_f(base["OWN"][i], 1)) - 1), opening=_f(base["OPEN"][i]),
            basis=_f(base["BASIS"][i]), weights=w,
            glide_to=v if sum(v) > 1e-9 else [],
            glide_start_age=_f(base["GA0"][i], 200.0),
            glide_end_age=_f(base["GA1"][i], 200.0),
            withdraw_priority=int(_f(base["WPRI"][i], i + 1)),
            contribute_priority=int(_f(base["CPRI"][i], i + 1)),
            contribution=_f(base["CONTR"][i]),
            contribution_pct_income=_f(base["CPCT"][i]),
            employer_match_pct=_f(base["MATCH"][i]),
            employer_match_cap_pct=_f(base["MCAP"][i]),
            rebalance=_s(base["REB"][i], "annual")))

    mu, sd = arr(doc, "AST_MU"), arr(doc, "AST_SD")
    yld, ter, beta = arr(doc, "AST_YLD"), arr(doc, "AST_TER"), arr(doc, "AST_BETA")
    assets = [AssetClass(f"asset {j+1}", _f(mu[j]), _f(sd[j]), _f(yld[j]),
                         _f(ter[j]), _f(beta[j])) for j in range(n_asset)]
    corr = [[_f(x) for x in row] for row in arr(doc, "AST_CORR")]
    rlab, roff = arr(doc, "REG_LABEL"), arr(doc, "REG_OFF")
    rvol, rtig = arr(doc, "REG_VOL"), arr(doc, "REG_TIGHT")
    rp = [[_f(x) for x in row] for row in arr(doc, "REG_P")]
    regimes = [Regime(_s(rlab[i], f"regime {i+1}"), _f(roff[i]), _f(rvol[i], 1.0),
                      _f(rtig[i]), rp[i]) for i in range(len(rlab))]
    crash = CrashSpec(
        enabled=(txt(doc, "IN_CR_ON", "Yes") == "Yes"), prob=num(doc, "IN_CR_PROB"),
        depth_min=num(doc, "IN_CR_MIN"), depth_mode=num(doc, "IN_CR_MODE"),
        depth_max=num(doc, "IN_CR_MAX"), duration=int(num(doc, "IN_CR_DUR", 1)),
        recovery_fraction=num(doc, "IN_CR_REC"),
        recovery_periods=int(num(doc, "IN_CR_RECY", 1)))
    infl = InflationSpec(mode=txt(doc, "IN_INF_MODE", "fixed"),
                         mean=num(doc, "IN_INF_MEAN"), sd=num(doc, "IN_INF_SD"),
                         persistence=num(doc, "IN_INF_PHI"),
                         corr_equity=num(doc, "IN_INF_CORR"))
    p.market = MarketSpec(mode=txt(doc, "IN_MKT_MODE", "fixed"),
                          dist=txt(doc, "IN_MKT_DIST", "lognormal"),
                          nu=num(doc, "IN_MKT_NU", 5.0), assets=assets, corr=corr,
                          regimes=regimes,
                          start_regime=txt(doc, "IN_REG_START", "stationary"),
                          crash=crash, inflation=infl,
                          antithetic=(txt(doc, "IN_MKT_ANTI", "No") == "Yes"),
                          calibrate=(txt(doc, "IN_MKT_CALIB", "Yes") == "Yes"))

    lo, rate = arr(doc, "TXO_L"), arr(doc, "TXO_R")
    lowers, rates = [], []
    for i in range(len(lo)):
        if lo[i] in BLANK and i > 0:
            break
        lowers.append(_f(lo[i]))
        rates.append(_f(rate[i]))
    p.tax = TaxSystem(ordinary=Schedule("ordinary", lowers, rates),
                      capital=Schedule("capital", [0.0], [0.0]),
                      surtax_rate=num(doc, "IN_TX_SUR_RATE"),
                      surtax_threshold=num(doc, "IN_TX_SUR_THR", 1e18) or 1e18,
                      cg_inclusion=num(doc, "IN_TX_CG_INCL", 1.0),
                      index_bands=(txt(doc, "IN_TX_INDEX", "Yes") == "Yes"))

    p.policy = Policy(
        method=txt(doc, "IN_POL_METHOD", "fixed_real"), pct=num(doc, "IN_POL_PCT"),
        vpw_rate=num(doc, "IN_POL_VPW"), guard_up=num(doc, "IN_POL_GUARD_UP"),
        guard_down=num(doc, "IN_POL_GUARD_DN"), guard_cut=num(doc, "IN_POL_CUT"),
        guard_raise=num(doc, "IN_POL_RAISE"),
        guard_final_years=int(num(doc, "IN_POL_FINAL", 15)),
        inflation_skip=(txt(doc, "IN_POL_SKIP", "Yes") == "Yes"),
        legacy_target=num(doc, "IN_POL_LEGACY"),
        confidence=num(doc, "IN_POL_CONF", 0.85),
        discount_rate=num(doc, "IN_POL_DISC", 0.03),
        cash_buffer_years=num(doc, "IN_POL_CASH_YRS"))
    p.policy.sweep_ledger = max(0, int(num(doc, "IN_POL_SWEEP", 1)) - 1)
    ages, mult = arr(doc, "SM_AGE"), arr(doc, "SM_MULT")
    p.smile = SmileCurve([_f(a) for a in ages if a not in BLANK],
                         [_f(m) for m in mult if m not in BLANK])
    return p
