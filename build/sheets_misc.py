"""Market, tax and lookup tables, the debt schedule, and the simulation sheets."""
from __future__ import annotations

import theme
import unohelp as U
from spec import (N_ASSET, N_BAND, N_LOAN, N_MRD, N_REGIME, N_SMILE, SH, T)

ASSET_SAMPLE = [
    # label, mu, sigma, yield, ter, crash beta
    ("Global equity", 0.070, 0.170, 0.020, 0.0020, 1.00),
    ("Government bonds", 0.035, 0.060, 0.030, 0.0015, -0.15),
    ("Corporate credit", 0.045, 0.080, 0.040, 0.0025, 0.40),
    ("Property", 0.055, 0.130, 0.035, 0.0060, 0.60),
    ("Cash", 0.020, 0.010, 0.020, 0.0010, 0.00),
    ("Alternatives", 0.060, 0.150, 0.010, 0.0090, 0.50),
]
CORR_SAMPLE = [
    [1.00, 0.10, 0.45, 0.60, 0.00, 0.50],
    [0.10, 1.00, 0.60, 0.15, 0.20, 0.05],
    [0.45, 0.60, 1.00, 0.35, 0.10, 0.25],
    [0.60, 0.15, 0.35, 1.00, 0.05, 0.35],
    [0.00, 0.20, 0.10, 0.05, 1.00, 0.00],
    [0.50, 0.05, 0.25, 0.35, 0.00, 1.00],
]
REGIME_SAMPLE = [
    # label, mean offset, vol mult, corr tighten, transitions
    ("Bear", -0.22, 1.90, 0.55, [0.50, 0.45, 0.05]),
    ("Normal", 0.00, 1.00, 0.00, [0.10, 0.80, 0.10]),
    ("Bull", 0.08, 0.80, 0.00, [0.04, 0.26, 0.70]),
]
# Bands are in gross-income space: the tax-free allowance is simply a 0% band,
# and an allowance taper is a band with the higher effective marginal rate.
BAND_SAMPLE = [(0, 0.00), (12570, 0.20), (50270, 0.40), (100000, 0.60),
               (125140, 0.45), (None, None), (None, None), (None, None)]
CG_SAMPLE = [(0, 0.00), (3000, 0.10), (40000, 0.20), (None, None),
             (None, None), (None, None), (None, None), (None, None)]
SMILE_SAMPLE = [(55, 1.00), (65, 1.00), (75, 0.94), (85, 0.86), (95, 0.88), (105, 0.88)]
MRD_SAMPLE = [(75, 24.6), (80, 20.2), (85, 16.0), (90, 12.2), (95, 8.9), (100, 6.4),
              (105, 4.6), (110, 3.5), (115, 2.9), (120, 2.0), (None, None), (None, None)]


def markets_tables(ctx, sh, start_row):
    """Assets across columns so a weight row and a parameter row multiply directly."""
    P = ctx.fmt
    r = start_row
    U.put(sh, 0, r, "Asset classes - the return engine", style="rp_h1")
    for cc in range(1, 8):
        U.put(sh, cc, r, "", style="rp_h1")
    r += 1
    U.put(sh, 0, r, "Expected returns are ARITHMETIC and NOMINAL, per year. The "
          "compound (geometric) figure the portfolio actually earns is lower by "
          "roughly half the variance - the Dashboard reports both.", style="rp_note")
    r += 2
    hdr_row = r
    U.put(sh, 0, r, "Attribute", style="rp_hdrcol")
    for i in range(N_ASSET):
        U.put(sh, 1 + i, r, f"Asset {i+1}", style="rp_hdrcol")
    rows = [("Label", "text", None), ("Expected return", "pct2", "AST_MU"),
            ("Volatility", "pct2", "AST_SD"), ("Income yield", "pct2", "AST_YLD"),
            ("Fund cost (TER)", "pct2", "AST_TER"), ("Crash beta", "num", "AST_BETA")]
    for j, (lab, fmt, name) in enumerate(rows):
        rr = hdr_row + 1 + j
        U.put(sh, 0, rr, lab, style="rp_label")
        for i in range(N_ASSET):
            v = ASSET_SAMPLE[i][j] if i < len(ASSET_SAMPLE) else None
            U.put(sh, 1 + i, rr, v, style="rp_input", fmt=P.get(fmt))
        if name:
            ctx.name(name, SH["market"], 1, rr, N_ASSET, rr)
    ctx.name("AST_LABEL", SH["market"], 1, hdr_row + 1, N_ASSET, hdr_row + 1)
    r = hdr_row + 1 + len(rows) + 2

    U.put(sh, 0, r, "Correlation matrix", style="rp_h2")
    U.put(sh, 3, r, "Symmetric, 1 on the diagonal. If it is not positive "
          "semi-definite the engine shrinks it toward the identity and says so.",
          style="rp_note")
    r += 1
    for i in range(N_ASSET):
        U.put(sh, 0, r + i, f"=INDEX(AST_LABEL,{i+1})", style="rp_calc")
        for j in range(N_ASSET):
            U.put(sh, 1 + j, r + i, CORR_SAMPLE[i][j], style="rp_input", fmt=P["num"])
    ctx.name("AST_CORR", SH["market"], 1, r, N_ASSET, r + N_ASSET - 1)
    U.put(sh, N_ASSET + 2, r, "Check", style="rp_hdrcol")
    U.put(sh, N_ASSET + 2, r + 1,
          '=IF(SUMPRODUCT((AST_CORR<-1)+(AST_CORR>1))>0,"OUT OF RANGE","OK")',
          style="rp_calc")
    ctx.name("CHK_CORR", SH["market"], N_ASSET + 2, r + 1)
    r += N_ASSET + 2

    U.put(sh, 0, r, "Market regimes and the transition matrix", style="rp_h2")
    r += 1
    heads = ["Regime", "Mean offset", "Vol multiplier", "Correlation tightening"] + \
            [f"P(-> {REGIME_SAMPLE[i][0]})" for i in range(N_REGIME)] + \
            ["Row sum", "Expected years"]
    for i, h in enumerate(heads):
        U.put(sh, i, r, h, style="rp_hdrcol")
    r += 1
    for i in range(N_REGIME):
        lab, off, vm, ct, tr = REGIME_SAMPLE[i]
        U.put(sh, 0, r + i, lab, style="rp_input")
        U.put(sh, 1, r + i, off, style="rp_input", fmt=P["pct2"])
        U.put(sh, 2, r + i, vm, style="rp_input", fmt=P["num"])
        U.put(sh, 3, r + i, ct, style="rp_input", fmt=P["pct"])
        for j in range(N_REGIME):
            U.put(sh, 4 + j, r + i, tr[j], style="rp_input", fmt=P["num"])
        rowrng = f"{U.a1(4, r+i)}:{U.a1(4+N_REGIME-1, r+i)}"
        U.put(sh, 4 + N_REGIME, r + i, f"=SUM({rowrng})", style="rp_calc", fmt=P["num"])
        U.put(sh, 5 + N_REGIME, r + i,
              f"=IF(1-{U.a1(4+i, r+i)}<0.0001,999,1/(1-{U.a1(4+i, r+i)}))",
              style="rp_calc", fmt=P["num"])
    ctx.name("REG_LABEL", SH["market"], 0, r, 0, r + N_REGIME - 1)
    ctx.name("REG_OFF", SH["market"], 1, r, 1, r + N_REGIME - 1)
    ctx.name("REG_VOL", SH["market"], 2, r, 2, r + N_REGIME - 1)
    ctx.name("REG_TIGHT", SH["market"], 3, r, 3, r + N_REGIME - 1)
    ctx.name("REG_P", SH["market"], 4, r, 4 + N_REGIME - 1, r + N_REGIME - 1)
    U.put(sh, 0, r + N_REGIME + 1,
          '=IF(SUMPRODUCT(ABS(MMULT(REG_P,TRANSPOSE(REG_P*0+1))-1))>0.001,'
          '"ROWS MUST SUM TO 1","OK")', style="rp_calc")
    ctx.name("CHK_REG", SH["market"], 0, r + N_REGIME + 1)
    return r + N_REGIME + 3


def tax_tables(ctx, sh, start_row):
    P = ctx.fmt
    r = start_row
    U.put(sh, 0, r, "Tax bands - expressed in gross-income space", style="rp_h1")
    for cc in range(1, 7):
        U.put(sh, cc, r, "", style="rp_h1")
    r += 1
    U.put(sh, 0, r, "A tax-free allowance is simply a 0% first band. An allowance "
          "taper is a band carrying the higher effective marginal rate. Expressed "
          "this way the schedule is exactly invertible, which is what lets the model "
          "answer 'how much must I withdraw to spend X' without a circular reference.",
          style="rp_note")
    r += 2
    for title, sample, prefix in (("Ordinary income", BAND_SAMPLE, "TXO"),):
        U.put(sh, 0, r, title, style="rp_h2")
        r += 1
        for i, h in enumerate(["Band", "Income from", "Marginal rate", "Band ends",
                               "Cumulative tax at start"]):
            U.put(sh, i, r, h, style="rp_hdrcol")
        r += 1
        for i in range(N_BAND):
            lo, rate = sample[i] if i < len(sample) else (None, None)
            U.put(sh, 0, r + i, i + 1, style="rp_calc", fmt=P["int"])
            U.put(sh, 1, r + i, lo, style="rp_input", fmt=P["money"])
            U.put(sh, 2, r + i, rate, style="rp_input", fmt=P["pct2"])
            nxt = U.a1(1, r + i + 1)
            U.put(sh, 3, r + i,
                  f'=IF({i+1}={N_BAND},1E15,IF({nxt}="",1E15,{nxt}))',
                  style="rp_calc", fmt=P["money"])
            if i == 0:
                U.put(sh, 4, r + i, 0, style="rp_calc", fmt=P["money"])
            else:
                pl, pu, pr, pc = (U.a1(1, r + i - 1), U.a1(3, r + i - 1),
                                  U.a1(2, r + i - 1), U.a1(4, r + i - 1))
                U.put(sh, 4, r + i, f"={pc}+{pr}*MIN({pu},1E15)-{pr}*{pl}",
                      style="rp_calc", fmt=P["money"])
        ctx.name(f"{prefix}_L", SH["tax"], 1, r, 1, r + N_BAND - 1)
        ctx.name(f"{prefix}_R", SH["tax"], 2, r, 2, r + N_BAND - 1)
        ctx.name(f"{prefix}_U", SH["tax"], 3, r, 3, r + N_BAND - 1)
        ctx.name(f"{prefix}_CT", SH["tax"], 4, r, 4, r + N_BAND - 1)
        r += N_BAND + 2
    return r


def lookup_tables(ctx):
    P = ctx.fmt
    sh = ctx.sheet(SH["expense"])
    # Spending smile lives with the expenses it modifies, but well clear of the
    # table's computed columns - overlapping them silently zeroed the first rows.
    r = 3
    col = 32
    U.put(sh, col, r, "Spending smile (age curve)", style="rp_h2")
    U.put(sh, col, r + 1, "Real spending typically drifts down through retirement, then "
          "ticks up if care is needed.", style="rp_note")
    U.put(sh, col, r + 2, "Age", style="rp_hdrcol")
    U.put(sh, col, r + 3, "Multiplier", style="rp_hdrcol")
    for i, (a, m) in enumerate(SMILE_SAMPLE[:N_SMILE]):
        U.put(sh, col + 1 + i, r + 2, a, style="rp_input", fmt=P["age"])
        U.put(sh, col + 1 + i, r + 3, m, style="rp_input", fmt=P["num"])
    ctx.name("SM_AGE", SH["expense"], col + 1, r + 2, col + N_SMILE, r + 2)
    ctx.name("SM_MULT", SH["expense"], col + 1, r + 3, col + N_SMILE, r + 3)

    sh = ctx.sheet(SH["wrap"])
    r = 3
    col = 24
    U.put(sh, col, r, "Minimum distribution table", style="rp_h2")
    U.put(sh, col, r + 1, "Balance divided by the divisor for the age reached. "
          "Step lookup, as published tables are stated.", style="rp_note")
    U.put(sh, col, r + 2, "From age", style="rp_hdrcol")
    U.put(sh, col + 1, r + 2, "Divisor", style="rp_hdrcol")
    for i, (a, d) in enumerate(MRD_SAMPLE[:N_MRD]):
        U.put(sh, col, r + 3 + i, a, style="rp_input", fmt=P["age"])
        U.put(sh, col + 1, r + 3 + i, d, style="rp_input", fmt=P["num"])
    ctx.name("MRD_AGE", SH["wrap"], col, r + 3, col, r + 2 + N_MRD)
    ctx.name("MRD_DIV", SH["wrap"], col + 1, r + 3, col + 1, r + 2 + N_MRD)


def debt_sheet(ctx):
    P = ctx.fmt
    sh = ctx.sheet(SH["engd"])
    U.put(sh, 0, 0, "Debt amortisation - nominal terms, one row per year",
          style="rp_title")
    U.put(sh, 0, 1, "Calculated. Interest, principal and the payoff year for every loan.",
          style="rp_note")
    hdr = 3
    data = 4
    U.put(sh, 0, hdr, "t", style="rp_hdrcol")
    for i in range(N_LOAN):
        for j, h in enumerate(("Balance", "Interest", "Principal", "Payment")):
            U.put(sh, 1 + i * 4 + j, hdr, f"L{i+1} {h}", style="rp_hdrcol")
    base = 1 + N_LOAN * 4
    for j, h in enumerate(("Payment total", "Balance total", "Interest total")):
        U.put(sh, base + j, hdr, h, style="rp_hdrcol")
    for k in range(T + 1):
        r = data + k
        U.put(sh, 0, r, k, style="rp_calc", fmt=P["int"])
        for i in range(N_LOAN):
            cb, ci, cp, cy = 1 + i * 4, 2 + i * 4, 3 + i * 4, 4 + i * 4
            L = i + 1
            if k == 0:
                U.put(sh, cb, r, f"=INDEX(LN_BAL,{L})*INDEX(LN_ACT,{L})",
                      style="rp_calc", fmt=P["money"])
            else:
                U.put(sh, cb, r, f"=MAX(0,{U.a1(cb, r-1)}-{U.a1(cp, r-1)})",
                      style="rp_calc", fmt=P["money"])
            bal = U.a1(cb, r)
            U.put(sh, ci, r, f"=IF(OR({bal}<=0,{k}<INDEX(LN_ST,{L})),0,"
                             f"{bal}*INDEX(LN_R,{L}))", style="rp_calc", fmt=P["money"])
            it = U.a1(ci, r)
            U.put(sh, cp, r,
                  f'=IF(OR({bal}<=0,{k}<INDEX(LN_ST,{L})),0,'
                  f'IF(INDEX(LN_KIND,{L})="interest_only",MIN({bal},INDEX(LN_EX,{L})),'
                  f'IF({k}-INDEX(LN_ST,{L})>=INDEX(LN_N,{L})-1,{bal},'
                  f'MIN({bal},MAX(0,INDEX(LN_PAY,{L})-{it}+INDEX(LN_EX,{L}))))))',
                  style="rp_calc", fmt=P["money"])
            U.put(sh, cy, r, f"={it}+{U.a1(cp, r)}", style="rp_calc", fmt=P["money"])
        pay_cols = [U.a1(4 + i * 4, r) for i in range(N_LOAN)]
        bal_cols = [U.a1(1 + i * 4, r) for i in range(N_LOAN)]
        int_cols = [U.a1(2 + i * 4, r) for i in range(N_LOAN)]
        U.put(sh, base, r, "=" + "+".join(pay_cols), style="rp_calc", fmt=P["money"])
        U.put(sh, base + 1, r, "=" + "+".join(bal_cols), style="rp_calc", fmt=P["money"])
        U.put(sh, base + 2, r, "=" + "+".join(int_cols), style="rp_calc", fmt=P["money"])
    ctx.name("DBT_PAY", SH["engd"], base, data, base, data + T)
    ctx.name("DBT_BAL", SH["engd"], base + 1, data, base + 1, data + T)
    ctx.name("DBT_INT", SH["engd"], base + 2, data, base + 2, data + T)
    return sh
