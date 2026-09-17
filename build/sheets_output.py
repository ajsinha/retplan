"""Simulation sheets, chart data, dashboard, reports and the audit sheet."""
from __future__ import annotations

import theme
import unohelp as U
from spec import N_ASSET, N_LEDGER, N_REGIME, SH, T

MACRO = "vnd.sun.star.script:retplan_macros.py${fn}?language=Python&location=user"
NPCT = 7
PCT_LABELS = ["P5", "P10", "P25", "P50", "P75", "P90", "P95"]
N_SAMPLE = 20
N_BINS = 30
N_SWEEP = 21

SIM_KPIS = [
    ("SIMK_TRIALS", "Trials run", "int"),
    ("SIMK_SUCCESS", "Success probability", "pct"),
    ("SIMK_SE", "Standard error", "pct"),
    ("SIMK_CILO", "95% interval, low", "pct"),
    ("SIMK_CIHI", "95% interval, high", "pct"),
    ("SIMK_TERM5", "Terminal wealth P5", "money"),
    ("SIMK_TERM50", "Terminal wealth P50", "money"),
    ("SIMK_TERM95", "Terminal wealth P95", "money"),
    ("SIMK_DEPAGE10", "Money runs out by (P10)", "age"),
    ("SIMK_DEPAGE50", "Money runs out by (P50)", "age"),
    ("SIMK_FAILRATE", "Failure rate", "pct"),
    ("SIMK_DD", "Worst drawdown", "pct"),
    ("SIMK_SHORT", "Median total shortfall", "money"),
    ("SIMK_MAXSPEND", "Max sustainable spend", "money"),
    ("SIMK_SWR", "Max spend as % of portfolio", "pct"),
    ("SIMK_EARLIEST", "Earliest retirement age", "age"),
    ("SIMK_REQSAVE", "Required extra saving/yr", "money"),
    ("SIMK_SHRINK", "Correlation shrinkage applied", "pct"),
    ("SIMK_SECONDS", "Run time (seconds)", "num"),
]


def sim_control(ctx):
    P = ctx.fmt
    sh = ctx.sheet(SH["sim"])
    U.put(sh, 0, 0, "Simulation control", style="rp_title")
    U.put(sh, 0, 1, "The deterministic projection needs none of this. These settings "
          "drive the Monte Carlo engine, which runs in Python with numpy.",
          style="rp_note")
    sh.Columns.getByIndex(0).Width = 6200
    sh.Columns.getByIndex(1).Width = 3600
    sh.Columns.getByIndex(2).Width = 14000
    rows = [
        ("SIM_SEED", "Seed in use", "=IN_MKT_SEED", "int",
         "Same seed and inputs always give the same answer."),
        ("SIM_TRIALS", "Trials requested", "=IN_MKT_TRIALS", "int", ""),
        ("SIM_MODE", "Return mode", "=IN_MKT_MODE", "text",
         "fixed reproduces the sheet exactly; mc runs the regime and crash engine."),
        ("SIM_LIVEHASH", "Input fingerprint (live)",
         "=ROUND(SUM(INC_KR)+SUM(INC_KN)+SUM(EXP_KER)+SUM(EXP_KDR)+SUM(EXP_KEN)"
         "+SUM(EXP_KDN)+SUM(LG_OPEN)+SUM(LG_MU0)+SUM(AST_MU)*1000+SUM(AST_SD)*1000"
         "+SUM(TXO_L)+SUM(TXO_R)*1000+IN_INF_MEAN*100000+IN_MKT_SEED"
         "+IN_MKT_TRIALS+IN_POL_LEGACY+IN_P1_AGE+IN_P1_RETIRE+IN_P1_DEATH,4)",
         "num", "A cheap fingerprint of every input the engine reads."),
        ("SIM_RUNHASH", "Input fingerprint (last run)", 0, "num",
         "Written by the engine when it finishes."),
        ("SIM_STALE", "Results are",
         '=IF(SIM_RUNHASH=0,"NOT YET RUN",IF(ABS(SIM_LIVEHASH-SIM_RUNHASH)>0.0001,'
         '"STALE - inputs changed since the last run","FRESH"))', "text", ""),
        ("SIM_STATUS", "Engine status", "Not run yet", "text", ""),
    ]
    r = 3
    for key, lab, val, fmt, note in rows:
        U.put(sh, 0, r, lab, style="rp_label")
        U.put(sh, 1, r, val, style="rp_calc", fmt=P.get(fmt))
        U.put(sh, 2, r, note, style="rp_note")
        ctx.name(key, SH["sim"], 1, r)
        r += 1
    U.cond_format(sh, 1, r - 2, 1, r - 2,
                  [(f'ISNUMBER(SEARCH("STALE",{U.a1(1, r-2)}))', "rp_bad"),
                   (f'{U.a1(1, r-2)}="FRESH"', "rp_good")], base_addr=(1, r - 2))
    r += 1
    U.put(sh, 0, r, "Results", style="rp_h1")
    for cc in range(1, 3):
        U.put(sh, cc, r, "", style="rp_h1")
    r += 1
    for key, lab, fmt in SIM_KPIS:
        U.put(sh, 0, r, lab, style="rp_label")
        U.put(sh, 1, r, 0, style="rp_calc", fmt=P.get(fmt))
        ctx.name(key, SH["sim"], 1, r)
        r += 1
    r += 1
    U.put(sh, 0, r, "Effective long-run statistics after regimes and crashes",
          style="rp_h2")
    r += 1
    U.put(sh, 0, r, "Asset", style="rp_hdrcol")
    for i, h in enumerate(("Target return", "Effective return", "Effective compound",
                           "Target volatility", "Effective volatility")):
        U.put(sh, 1 + i, r, h, style="rp_hdrcol")
    r += 1
    for i in range(N_ASSET):
        U.put(sh, 0, r + i, f"=INDEX(AST_LABEL,{i+1})", style="rp_calc")
        U.put(sh, 1, r + i, f"=INDEX(AST_MU,{i+1})", style="rp_calc", fmt=P["pct2"])
        for j in range(2, 6):
            U.put(sh, j, r + i, 0, style="rp_calc", fmt=P["pct2"])
    ctx.name("SIM_EFF", SH["sim"], 2, r, 5, r + N_ASSET - 1)
    r += N_ASSET + 1
    U.put(sh, 0, r, "Regime occupancy", style="rp_h2")
    r += 1
    for i in range(N_REGIME):
        U.put(sh, 0, r + i, f"=INDEX(REG_LABEL,{i+1})", style="rp_calc")
        U.put(sh, 1, r + i, 0, style="rp_calc", fmt=P["pct"])
    ctx.name("SIM_REGMIX", SH["sim"], 1, r, 1, r + N_REGIME - 1)
    return sh


def sim_paths(ctx):
    P = ctx.fmt
    sh = ctx.sheet(SH["simpaths"])
    U.put(sh, 0, 0, "Simulation paths - written by the engine", style="rp_title")
    hdr = 2
    U.put(sh, 0, hdr, "Year", style="rp_hdrcol")
    cols = ([f"Net worth {p}" for p in PCT_LABELS] +
            ["Fan base"] + [f"Fan {PCT_LABELS[i]}" for i in range(1, NPCT)] +
            [f"Spending {p}" for p in PCT_LABELS] +
            [f"Path {i+1}" for i in range(N_SAMPLE)])
    for i, h in enumerate(cols):
        U.put(sh, 1 + i, hdr, h, style="rp_hdrcol")
    for k in range(T + 1):
        r = hdr + 1 + k
        U.put(sh, 0, r, f"=INDEX(ENGC_YEAR,{k+1})", style="rp_calc", fmt=P["year"])
        for i in range(len(cols)):
            U.put(sh, 1 + i, r, 0, style="rp_calc", fmt=P["money"])
    ctx.name("SIMP_YEAR", SH["simpaths"], 0, hdr + 1, 0, hdr + 1 + T)
    ctx.name("SIMP_NW", SH["simpaths"], 1, hdr + 1, NPCT, hdr + 1 + T)
    ctx.name("SIMP_FAN", SH["simpaths"], NPCT + 1, hdr + 1, 2 * NPCT, hdr + 1 + T)
    ctx.name("SIMP_SPEND", SH["simpaths"], 2 * NPCT + 1, hdr + 1, 3 * NPCT, hdr + 1 + T)
    ctx.name("SIMP_SAMPLE", SH["simpaths"], 3 * NPCT + 1, hdr + 1,
             3 * NPCT + N_SAMPLE, hdr + 1 + T)
    return sh, hdr


def sim_results(ctx):
    P = ctx.fmt
    sh = ctx.sheet(SH["simres"])
    U.put(sh, 0, 0, "Simulation distributions - written by the engine", style="rp_title")
    U.put(sh, 0, 2, "Terminal wealth", style="rp_h2")
    U.put(sh, 0, 3, "Bin", style="rp_hdrcol")
    U.put(sh, 1, 3, "Trials", style="rp_hdrcol")
    for i in range(N_BINS):
        U.put(sh, 0, 4 + i, 0, style="rp_calc", fmt=P["money"])
        U.put(sh, 1, 4 + i, 0, style="rp_calc", fmt=P["int"])
    ctx.name("SIMR_HIST", SH["simres"], 0, 4, 1, 3 + N_BINS)

    U.put(sh, 3, 2, "When the money runs out", style="rp_h2")
    U.put(sh, 3, 3, "Age", style="rp_hdrcol")
    U.put(sh, 4, 3, "Cumulative chance", style="rp_hdrcol")
    for i in range(T + 1):
        U.put(sh, 3, 4 + i, 0, style="rp_calc", fmt=P["age"])
        U.put(sh, 4, 4 + i, 0, style="rp_calc", fmt=P["pct"])
    ctx.name("SIMR_DEP", SH["simres"], 3, 4, 4, 4 + T)

    U.put(sh, 6, 2, "Success against spending", style="rp_h2")
    U.put(sh, 6, 3, "Spending", style="rp_hdrcol")
    U.put(sh, 7, 3, "Success", style="rp_hdrcol")
    for i in range(N_SWEEP):
        U.put(sh, 6, 4 + i, 0, style="rp_calc", fmt=P["money"])
        U.put(sh, 7, 4 + i, 0, style="rp_calc", fmt=P["pct"])
    ctx.name("SIMR_SWEEP", SH["simres"], 6, 4, 7, 3 + N_SWEEP)

    U.put(sh, 9, 2, "What moves the answer (tornado)", style="rp_h2")
    U.put(sh, 9, 3, "Driver", style="rp_hdrcol")
    U.put(sh, 10, 3, "Downside", style="rp_hdrcol")
    U.put(sh, 11, 3, "Upside", style="rp_hdrcol")
    for i in range(10):
        U.put(sh, 9, 4 + i, "", style="rp_calc")
        U.put(sh, 10, 4 + i, 0, style="rp_calc", fmt=P["pct"])
        U.put(sh, 11, 4 + i, 0, style="rp_calc", fmt=P["pct"])
    ctx.name("SIMR_TORN", SH["simres"], 9, 4, 11, 13)
    return sh


def chart_data(ctx):
    P = ctx.fmt
    sh = ctx.sheet(SH["chart"])
    U.put(sh, 0, 0, "Chart source data - every chart is reproducible from here",
          style="rp_title")
    hdr = 2
    b1 = ["Year", "Net worth", "Portfolio", "Debt", "Income", "Spending", "Tax",
          "Withdrawals", "Contributions"]
    src1 = ["ENGC_YEAR", "ENGC_NETWORTH", "ENGC_PORTCLOSE", "ENGC_DEBTBAL", "ENGC_INC",
            "ENGC_SPEND", "ENGC_TAXTOT", "ENGC_WDTOT", "ENGC_CONTRTOT"]
    for i, h in enumerate(b1):
        U.put(sh, i, hdr, h, style="rp_hdrcol")
    for k in range(T + 1):
        for i, s in enumerate(src1):
            U.put(sh, i, hdr + 1 + k, f"=INDEX({s},{k+1})", style="rp_calc",
                  fmt=P["year"] if i == 0 else P["money"])
    ctx.name("CD_MAIN", SH["chart"], 0, hdr, len(b1) - 1, hdr + 1 + T)
    ctx.name("CD_NW", SH["chart"], 0, hdr, 1, hdr + 1 + T)
    ctx.name("CD_FLOWS", SH["chart"], 4, hdr, 8, hdr + 1 + T)

    c0 = len(b1) + 1
    U.put(sh, c0, hdr, "Year", style="rp_hdrcol")
    for i in range(N_LEDGER):
        U.put(sh, c0 + 1 + i, hdr, f"=INDEX(TBL_ACCT,{i+1},3)", style="rp_hdrcol")
    for k in range(T + 1):
        U.put(sh, c0, hdr + 1 + k, f"=INDEX(ENGC_YEAR,{k+1})", style="rp_calc",
              fmt=P["year"])
        for i in range(N_LEDGER):
            U.put(sh, c0 + 1 + i, hdr + 1 + k, f"=INDEX(ENGC_CLOSE{i+1},{k+1})",
                  style="rp_calc", fmt=P["money"])
    ctx.name("CD_ACCT", SH["chart"], c0, hdr, c0 + N_LEDGER, hdr + 1 + T)

    c1 = c0 + N_LEDGER + 2
    for i, h in enumerate(("Year", "Drawdown", "Withdrawal rate", "Effective tax rate")):
        U.put(sh, c1 + i, hdr, h, style="rp_hdrcol")
    for k in range(T + 1):
        r = hdr + 1 + k
        U.put(sh, c1, r, f"=INDEX(ENGC_YEAR,{k+1})", style="rp_calc", fmt=P["year"])
        U.put(sh, c1 + 1, r,
              f"=IFERROR(INDEX(ENGC_NETWORTH,{k+1})/MAX(1,MAX(OFFSET(ENGC_NETWORTH,0,0,"
              f"{k+1},1)))-1,0)", style="rp_calc", fmt=P["pct"])
        U.put(sh, c1 + 2, r, f"=INDEX(ENGC_WDRATE,{k+1})", style="rp_calc", fmt=P["pct"])
        U.put(sh, c1 + 3, r,
              f"=IFERROR(INDEX(ENGC_TAXTOT,{k+1})/MAX(1,INDEX(ENGC_INC,{k+1})"
              f"+INDEX(ENGC_WDTOT,{k+1})),0)", style="rp_calc", fmt=P["pct"])
    ctx.name("CD_RISK", SH["chart"], c1, hdr, c1 + 3, hdr + 1 + T)
    return sh, hdr


def dashboard(ctx):
    P = ctx.fmt
    sh = ctx.sheet(SH["dash"], 0)
    for i, w in enumerate((5200, 3600, 3600, 3600, 3600, 3600, 3600, 3600, 3600)):
        sh.Columns.getByIndex(i).Width = w
    U.put(sh, 0, 0, "Retirement plan - dashboard", style="rp_title")
    U.put(sh, 0, 1, "Deterministic figures come from the sheet itself and update as you "
          "type. Simulation figures come from the Monte Carlo engine - press Run.",
          style="rp_note")

    tiles = [
        ("Plan verdict", '=IF(SUM(ENGC_SHORTFALL)>1,"FUNDING GAP","FULLY FUNDED")', "text"),
        ("Money lasts to age", '=IFERROR(INDEX(ENGC_AGE1,MATCH(TRUE,ENGC_SHORTFALL>1,0)),'
                              'INDEX(ENGC_AGE1,COUNT(ENGC_AGE1)))', "age"),
        ("Success probability", "=SIMK_SUCCESS", "pct"),
        ("Terminal wealth (median)", "=SIMK_TERM50", "money"),
        ("Funded ratio", "=IFERROR((INDEX(ENGC_PORTOPEN,1)+SUM(ENGC_INC_PV))/"
                         "MAX(1,SUM(ENGC_DISC_PV)),0)", "num"),
        ("Max sustainable spend", "=SIMK_MAXSPEND", "money"),
        ("Lifetime tax", "=INDEX(ENGC_CUMTAX,COUNT(ENGC_CUMTAX))", "money"),
        ("First-year spending", "=INDEX(ENGC_SPEND,1)+INDEX(ENGC_DEBTPAY,1)", "money"),
    ]
    r = 3
    for i, (lab, formula, fmt) in enumerate(tiles):
        col = (i % 4) * 2
        row = r + (i // 4) * 3
        U.put(sh, col, row, lab, style="rp_kpi_lab")
        U.put(sh, col, row + 1, formula, style="rp_kpi", fmt=P.get(fmt))
    r += 7
    U.put(sh, 0, r, "Simulation", style="rp_h1")
    for cc in range(1, 9):
        U.put(sh, cc, r, "", style="rp_h1")
    r += 1
    U.put(sh, 0, r, "=SIM_STALE", style="rp_calc")
    U.put(sh, 2, r, "=SIM_STATUS", style="rp_calc")
    U.put(sh, 5, r, '="Success "&TEXT(SIMK_SUCCESS,"0.0%")&" +/- "'
                    '&TEXT(1.96*SIMK_SE,"0.0%")&" over "&TEXT(SIMK_TRIALS,"#,##0")'
                    '&" trials"', style="rp_calc")
    U.cond_format(sh, 0, r, 0, r,
                  [(f'ISNUMBER(SEARCH("STALE",{U.a1(0, r)}))', "rp_bad"),
                   (f'{U.a1(0, r)}="FRESH"', "rp_good")], base_addr=(0, r))
    ctx.name("DASH_STATUS", SH["dash"], 0, r)
    return sh, r + 2


def reports(ctx):
    P = ctx.fmt
    specs = [
        ("repcf", "Cash-flow statement", [
            ("Year", "ENGC_YEAR", "year"), ("Age", "ENGC_AGE1", "age"),
            ("Income", "ENGC_INC", "money"), ("Forced draws", "ENGC_MRDTOT", "money"),
            ("Spending", "ENGC_SPEND", "money"), ("Debt service", "ENGC_DEBTPAY", "money"),
            ("Tax", "ENGC_TAXTOT", "money"), ("Withdrawals", "ENGC_WDTOT", "money"),
            ("Paid in", "ENGC_CONTRTOT", "money"), ("Fees", "ENGC_FEETOT", "money"),
            ("Shortfall", "ENGC_SHORTFALL", "money"),
            ("Portfolio close", "ENGC_PORTCLOSE", "money")]),
        ("repbal", "Balance sheet", [("Year", "ENGC_YEAR", "year"),
                                     ("Age", "ENGC_AGE1", "age")] +
         [(f"Account {i+1}", f"ENGC_CLOSE{i+1}", "money") for i in range(N_LEDGER)] +
         [("Portfolio", "ENGC_PORTCLOSE", "money"), ("Debt", "ENGC_DEBTBAL", "money"),
          ("Net worth (real)", "ENGC_NETWORTH", "money"),
          ("Net worth (nominal)", "ENGC_NWNOM", "money")]),
        ("reptax", "Tax detail", [
            ("Year", "ENGC_YEAR", "year"), ("Age", "ENGC_AGE1", "age"),
            ("Taxable income", "ENGC_TAXBASE", "money"),
            ("Tax on income", "ENGC_TAXINC", "money"),
            ("Tax on withdrawals", "ENGC_TAXWD", "money"),
            ("Total tax", "ENGC_TAXTOT", "money"),
            ("Cumulative tax", "ENGC_CUMTAX", "money"),
            ("Withdrawal rate", "ENGC_WDRATE", "pct")]),
    ]
    for key, title, cols in specs:
        sh = ctx.sheet(SH[key])
        U.put(sh, 0, 0, title, style="rp_title")
        U.put(sh, 0, 1, "All figures in today's money unless the column says otherwise. "
              "Calculated - nothing here is typed.", style="rp_note")
        for i, (h, _, _) in enumerate(cols):
            U.put(sh, i, 3, h, style="rp_hdrcol")
            sh.Columns.getByIndex(i).Width = 2300
        for k in range(T + 1):
            for i, (_, src, fmt) in enumerate(cols):
                U.put(sh, i, 4 + k, f"=INDEX({src},{k+1})", style="rp_out",
                      fmt=P.get(fmt))
        U.cond_format(sh, 0, 4, len(cols) - 1, 4 + T,
                      [(f"$A5>=0", "rp_out")], base_addr=(0, 4))
    return True


def audit(ctx):
    P = ctx.fmt
    sh = ctx.sheet(SH["audit"])
    U.put(sh, 0, 0, "Audit - identities and self-tests", style="rp_title")
    U.put(sh, 0, 1, "If anything here says FAIL, do not trust the numbers on the "
          "Dashboard until it is resolved.", style="rp_note")
    sh.Columns.getByIndex(0).Width = 9000
    sh.Columns.getByIndex(1).Width = 3000
    sh.Columns.getByIndex(2).Width = 2600
    sh.Columns.getByIndex(3).Width = 14000

    checks = [
        ("Every account's weights sum to 100%",
         '=IF(COUNTIF(LG_CHK,"WEIGHTS<>100%")=0,"PASS","FAIL")',
         "An allocation that does not sum to 1 silently rescales your returns."),
        ("Correlation matrix entries are inside [-1, 1]",
         '=IF(CHK_CORR="OK","PASS","FAIL")', ""),
        ("Regime transition rows sum to 1",
         '=IF(CHK_REG="OK","PASS","FAIL")', ""),
        ("Tax bands ascend",
         '=IF(SUMPRODUCT((TXO_L>0)*(TXO_L<=N(OFFSET(TXO_L,-1,0))))>0,"FAIL","PASS")',
         "A band table that does not ascend makes the tax inversion meaningless."),
        ("Tax rates are between 0% and 100%",
         '=IF(SUMPRODUCT((TXO_R<0)+(TXO_R>1))>0,"FAIL","PASS")', ""),
        ("Balance roll-forward ties every year",
         '=IF(SUMPRODUCT((ABS(ENGC_RECON)>0.000001)*1)>0,"FAIL","PASS")',
         "Sources equal uses: closing = opening - draws + paid in - fees + return, "
         "checked independently every year."),
        ("Closing balance carries into the next opening balance",
         '=IF(SUMPRODUCT((ABS(ENGC_PORTOPEN-ENGC_PORTCLOSE)>0.000001)*1)'
         '>COUNT(ENGC_PORTOPEN),"FAIL","PASS")', ""),
        ("No account balance goes negative",
         '=IF(MIN(ENGC_PORTCLOSE)<-0.000001,"FAIL","PASS")', ""),
        ("Withdrawals never exceed what is available",
         '=IF(SUMPRODUCT((ENGC_WDTOT>ENGC_PORTOPEN+0.01)*1)>0,"FAIL","PASS")', ""),
        ("Net delivered meets the need whenever funds exist",
         '=IF(SUMPRODUCT((ENGC_SHORTFALL>0.01)*(ENGC_PORTLIQ>1)*1)>0,"REVIEW","PASS")',
         "A shortfall while liquid money remains means a lock-in or liquidity rule bit."),
        ("Spending never falls below the essential floor",
         '=IF(SUMPRODUCT((ENGC_SPEND<ENGC_ESS-0.01)*1)>0,"FAIL","PASS")', ""),
        ("Retirement ages are after current ages",
         '=IF(OR(IN_P1_RETIRE<IN_P1_AGE,AND(IN_P2_AGE<>"",IN_P2_RETIRE<IN_P2_AGE)),'
         '"FAIL","PASS")', ""),
        ("Planning age is after retirement age",
         '=IF(IN_P1_DEATH<=IN_P1_RETIRE,"FAIL","PASS")', ""),
        ("Horizon covers the planning age",
         '=IF(IN_P1_AGE+IN_HORIZON<IN_P1_DEATH,"REVIEW","PASS")',
         "The projection stops before the plan does."),
        ("No input cell contains a formula",
         '=IF(SUMPRODUCT(ISFORMULA(INC_AMT)*1)+SUMPRODUCT(ISFORMULA(EXP_AMT)*1)>0,'
         '"FAIL","PASS")',
         "Formulas in input cells break scenario switching."),
        ("Expected returns are inside a defensible range",
         '=IF(OR(MAX(AST_MU)>0.15,MIN(AST_MU)<-0.05),"REVIEW","PASS")', ""),
        ("Inflation assumption is plausible",
         '=IF(OR(IN_INF_MEAN>0.10,IN_INF_MEAN<-0.02),"REVIEW","PASS")', ""),
        ("Withdrawal rate at retirement is not extreme",
         '=IF(IFERROR(INDEX(ENGC_WDRATE,MATCH(IN_P1_RETIRE,ENGC_AGE1,0)),0)>0.08,'
         '"REVIEW","PASS")', ""),
        ("Fees are inside a plausible range",
         '=IF(IN_FEE_PLATFORM+IN_FEE_ADVISER>0.03,"REVIEW","PASS")', ""),
        ("At least one account is enabled",
         '=IF(SUM(LG_ACT)=0,"FAIL","PASS")', ""),
        ("At least one expense row is active",
         '=IF(SUM(EXP_ACT)=0,"FAIL","PASS")', ""),
        ("Simulation results match the current inputs",
         '=IF(SIM_STALE="FRESH","PASS","REVIEW")', ""),
        ("Sweep account exists",
         '=IF(OR(IN_POL_SWEEP<1,IN_POL_SWEEP>' + str(N_LEDGER) + '),"FAIL","PASS")', ""),
        ("Every wrapper referenced by an account exists",
         '=IF(SUMPRODUCT((LG_ACT=1)*((LG_WR<1)+(LG_WR>COUNTA(WR_LAB))))>0,"FAIL","PASS")',
         ""),
        ("Glidepath ages are ordered",
         '=IF(SUMPRODUCT((LG_ACT=1)*(LG_GA1<LG_GA0))>0,"REVIEW","PASS")', ""),
        ("Draw order has no duplicates",
         '=IF(SUMPRODUCT((LG_ACT=1)*(COUNTIF(LG_WPRI,LG_WPRI)>1))>0,"REVIEW","PASS")',
         "Duplicate priorities are resolved by row order, which may not be what you meant."),
    ]
    U.put(sh, 0, 3, "Check", style="rp_hdrcol")
    U.put(sh, 1, 3, "Result", style="rp_hdrcol")
    U.put(sh, 2, 3, "Severity", style="rp_hdrcol")
    U.put(sh, 3, 3, "Why it matters", style="rp_hdrcol")
    for i, (lab, formula, why) in enumerate(checks):
        r = 4 + i
        U.put(sh, 0, r, lab, style="rp_label")
        U.put(sh, 1, r, formula, style="rp_calc")
        U.put(sh, 2, r, f'=IF({U.a1(1, r)}="PASS","-",IF({U.a1(1, r)}="FAIL",'
                        f'"Blocking","Review"))', style="rp_calc")
        U.put(sh, 3, r, why, style="rp_note")
    last = 4 + len(checks) - 1
    ctx.name("AUDIT_RESULTS", SH["audit"], 1, 4, 1, last)
    U.cond_format(sh, 1, 4, 1, last,
                  [(f'{U.a1(1, 4)}="PASS"', "rp_good"),
                   (f'{U.a1(1, 4)}="FAIL"', "rp_bad"),
                   (f'{U.a1(1, 4)}="REVIEW"', "rp_warn")], base_addr=(1, 4))
    U.put(sh, 0, last + 2, "Overall", style="rp_h2")
    U.put(sh, 1, last + 2,
          '=IF(COUNTIF(AUDIT_RESULTS,"FAIL")>0,"FAIL - "&COUNTIF(AUDIT_RESULTS,"FAIL")'
          '&" blocking",IF(COUNTIF(AUDIT_RESULTS,"REVIEW")>0,"REVIEW - "'
          '&COUNTIF(AUDIT_RESULTS,"REVIEW")&" to check","PASS"))', style="rp_calc")
    ctx.name("AUDIT_OVERALL", SH["audit"], 1, last + 2)
    U.cond_format(sh, 1, last + 2, 1, last + 2,
                  [(f'LEFT({U.a1(1, last+2)},4)="PASS"', "rp_good"),
                   (f'LEFT({U.a1(1, last+2)},4)="FAIL"', "rp_bad"),
                   (f'LEFT({U.a1(1, last+2)},6)="REVIEW"', "rp_warn")],
                  base_addr=(1, last + 2))
    return sh


def charts_and_controls(ctx, sh, row):
    """Nine charts and four macro buttons on the Dashboard."""
    doc = ctx.doc
    idx = {doc.Sheets.getByIndex(i).Name: i for i in range(doc.Sheets.Count)}
    cd, sp, sr = idx[SH["chart"]], idx[SH["simpaths"]], idx[SH["simres"]]
    H = 2                                  # header row on ChartData / Sim-Paths
    last = H + 1 + T
    W, HT, GAP = 13500, 8200, 700
    x0, y0 = 300, row * 450 + 1500

    def pos(i):
        return x0 + (i % 2) * (W + GAP), y0 + (i // 2) * (HT + GAP)

    specs = [
        ("nw", "Net worth over time", "Today's money, after debt",
         [(cd, 0, H, 1, last)], "com.sun.star.chart.AreaDiagram", dict(), False),
        ("fan", "Range of outcomes", "Percentile bands from the simulation - press Run",
         [(sp, 0, H, 0, last), (sp, NPCT + 1, H, 2 * NPCT, last)],
         "com.sun.star.chart.AreaDiagram", dict(stacked=True), True),
        ("acct", "Where the money sits", "Closing balance by account",
         [(cd, 10, H, 10 + N_LEDGER, last)],
         "com.sun.star.chart.AreaDiagram", dict(stacked=True), False),
        ("flows", "Money in, money out", "Income, spending, tax, draws and pay-ins",
         [(cd, 0, H, 0, last), (cd, 4, H, 8, last)],
         "com.sun.star.chart.LineDiagram", dict(), False),
        ("paths", "A sample of individual futures", "Twenty simulated paths",
         [(sp, 0, H, 0, last), (sp, 3 * NPCT + 1, H, 3 * NPCT + N_SAMPLE, last)],
         "com.sun.star.chart.LineDiagram", dict(), False),
        ("hist", "Where you end up", "Distribution of terminal wealth",
         [(sr, 0, 3, 1, 3 + N_BINS)], "com.sun.star.chart.BarDiagram",
         dict(), False),
        ("dep", "Chance the money has run out by each age", "Cumulative",
         [(sr, 3, 3, 4, 3 + T)], "com.sun.star.chart.LineDiagram", dict(), False),
        ("sweep", "Success against spending", "The most useful chart in the workbook",
         [(sr, 6, 3, 7, 3 + N_SWEEP)], "com.sun.star.chart.LineDiagram",
         dict(), False),
        ("torn", "What moves the answer", "Success probability, driver by driver",
         [(sr, 9, 3, 11, 13)], "com.sun.star.chart.BarDiagram",
         dict(horizontal=True), False),
        ("risk", "Drawdown and withdrawal rate", "Deterministic path",
         [(cd, 10 + N_LEDGER + 2, H, 10 + N_LEDGER + 5, last)],
         "com.sun.star.chart.LineDiagram", dict(), False),
    ]
    for i, (name, title, sub, ranges, diagram, opts, transparent) in enumerate(specs):
        x, y = pos(i)
        horizontal = opts.pop("horizontal", False)
        ch = U.add_chart(doc, sh, f"rp_{name}", x, y, W, HT, ranges,
                         col_headers=True, row_headers=True, diagram=diagram,
                         title=title, subtitle=sub, **opts)
        if horizontal:
            try:
                ch.Diagram.setPropertyValue("Vertical", True)
            except Exception:
                pass
        U.style_series(ch, theme.SERIES, transparent_first=transparent)

    buttons = [("Run simulation", "run_simulation",
                "Monte Carlo at the trial count set on In-Markets"),
               ("Quick run (500)", "run_quick", "A fast pass while you edit inputs"),
               ("Full analysis", "run_full_analysis",
                "Simulation, solvers, spending sweep and tornado"),
               ("Clear results", "clear_results", "Blank every simulated figure")]
    bx = 300
    for label, fn, tip in buttons:
        U.add_button(doc, sh, label, bx, y0 - 1200, 3200, 900,
                     MACRO.format(fn=fn), name=f"btn_{fn}", tooltip=tip)
        bx += 3500
    return sh


def readme(ctx, version):
    sh = ctx.sheet(SH["readme"], 1)
    sh.Columns.getByIndex(0).Width = 4000
    sh.Columns.getByIndex(1).Width = 24000
    blocks = [
        ("title", "RetPlan - a retirement planning workbook", ""),
        ("note", f"Version {version}. Built from source; do not edit this file by hand "
                 f"if you intend to rebuild it.", ""),
        ("h1", "What this is", ""),
        ("", "A household cash-flow and portfolio model.", "It projects income, "
         "spending, debt, tax and investments year by year, then stress-tests the "
         "plan against thousands of simulated market histories."),
        ("", "Nothing here is country-specific.", "Tax is a table of bands you type. "
         "Account types are 'wrappers' that say when money is taxed - going in, "
         "while it grows, or coming out. EET, TEE, TTE and ETT are all just settings."),
        ("h1", "How to use it", ""),
        ("", "1.", "Work through 'Start Here'. It lists what is missing as you go."),
        ("", "2.", "The projection updates as you type - no macro needed for it."),
        ("", "3.", "Press Run on the Dashboard for the probability-based answers."),
        ("", "4.", "Check the Audit sheet before believing anything."),
        ("h1", "What the colours mean", ""),
        ("", "Blue", "You type here."),
        ("", "Green", "Choose from the list."),
        ("", "Grey", "Calculated - do not type over it."),
        ("", "Amber", "Advanced; safe to leave alone."),
        ("", "Red", "Something is wrong; the Status column says what."),
        ("h1", "Known limitations - read these", ""),
        ("", "Household-level tax.", "Income is taxed as one unit rather than split "
         "between two people with separate bands. Where a jurisdiction taxes "
         "individuals separately this overstates tax for couples with uneven incomes."),
        ("", "Annual periods.", "The engine steps a year at a time. Within-year timing "
         "of flows is not modelled."),
        ("", "Annual rebalancing assumed in the sheet.", "The formula engine blends "
         "returns by target weights each year; an unrebalanced portfolio would drift."),
        ("", "Allowances are bands.", "A tax-free allowance is entered as a 0% first "
         "band and a taper as a band with the higher effective rate. That keeps the "
         "schedule exactly invertible, which is what makes the 'how much must I "
         "withdraw' answer exact instead of iterative."),
        ("", "Capital gains.", "Taxed as a fraction of the withdrawal equal to the "
         "unrealised gain share times the inclusion rate, under the ordinary bands. "
         "There is no separate gains allowance."),
        ("", "Survivor mechanics are simplified.", "Income continuation percentages "
         "apply; account consolidation and filing changes are not modelled in full."),
        ("", "No advice.", "This is an educational model. It is not financial advice, "
         "and its outputs are only as good as the assumptions you type."),
        ("h1", "Protection and macros", ""),
        ("", "Calculation sheets are not password protected.", "Nothing is hidden. "
         "The macro source is a readable file in your LibreOffice profile at "
         "Scripts/python/retplan_macros.py - it performs no file, shell or network "
         "access."),
        ("", "Macros disabled?", "Everything except the simulation, the solvers and "
         "the four buttons still works."),
    ]
    r = 0
    for kind, a, b in blocks:
        if kind == "title":
            U.put(sh, 0, r, a, style="rp_title"); r += 2
        elif kind == "note":
            U.put(sh, 0, r, a, style="rp_note"); r += 2
        elif kind == "h1":
            U.put(sh, 0, r, a, style="rp_h1")
            U.put(sh, 1, r, "", style="rp_h1"); r += 2
        else:
            U.put(sh, 0, r, a, style="rp_label")
            U.put(sh, 1, r, b, style="rp_note")
            sh.Rows.getByIndex(r).OptimalHeight = True
            r += 1
    return sh


def start_here(ctx):
    sh = ctx.sheet(SH["start"], 2)
    sh.Columns.getByIndex(0).Width = 1200
    sh.Columns.getByIndex(1).Width = 9000
    sh.Columns.getByIndex(2).Width = 3000
    sh.Columns.getByIndex(3).Width = 2600
    sh.Columns.getByIndex(4).Width = 20000
    U.put(sh, 0, 0, "Start here", style="rp_title")
    U.put(sh, 0, 1, "Ten steps. The Status column tells you what is still missing; "
          "click a link to jump straight to it.", style="rp_note")
    steps = [
        ("Who the plan is for", "house", '=IF(COUNTIF(STAT_HOUSE,"OK")=COUNTA(STAT_HOUSE),'
         '"OK","CHECK")', "Ages, retirement ages and how long to plan for."),
        ("What comes in", "income", '=IF(SUM(INC_ACT)=0,"MISSING","OK")',
         "Salaries, pensions, rent, one-offs. Amounts are per year and before tax."),
        ("What goes out", "expense", '=IF(SUM(EXP_ACT)=0,"MISSING","OK")',
         "Split essential from discretionary: only the discretionary part can flex."),
        ("What you owe", "debt", '=IF(SUM(LN_ACT)=0,"NONE","OK")',
         "Mortgages and loans. Leave empty if you have none."),
        ("How money is taxed", "wrap", '=IF(COUNTA(WR_LAB)=0,"MISSING","OK")',
         "Define the wrappers first, then point accounts at them."),
        ("What you have", "acct", '=IF(SUM(LG_ACT)=0,"MISSING","OK")',
         "Balances, how they are invested, and the order they are drawn down."),
        ("Market assumptions", "market", '=IF(SUM(AST_MU)=0,"MISSING","OK")',
         "Returns, volatility, correlations, inflation, fees, crashes and regimes."),
        ("Tax bands", "tax", '=IF(COUNT(TXO_R)=0,"MISSING","OK")',
         "A tax-free allowance is simply a 0% first band."),
        ("Spending policy", "policy", '=IF(IN_POL_METHOD="","MISSING","OK")',
         "Fixed, percentage, amortised or guardrails - and what counts as success."),
        ("Read the answer", "dash", '=IF(SIM_RUNHASH=0,"NOT RUN","OK")',
         "The projection is already live. Press Run for the probabilities."),
    ]
    U.put(sh, 1, 3, "Step", style="rp_hdrcol")
    U.put(sh, 2, 3, "Go to", style="rp_hdrcol")
    U.put(sh, 3, 3, "Status", style="rp_hdrcol")
    U.put(sh, 4, 3, "What to do", style="rp_hdrcol")
    for i, (label, key, status, note) in enumerate(steps):
        r = 4 + i
        U.put(sh, 0, r, i + 1, style="rp_calc", fmt=ctx.fmt["int"])
        U.put(sh, 1, r, label, style="rp_label")
        U.put(sh, 2, r, f'=HYPERLINK("#$\'{SH[key]}\'.A1";"open")', style="rp_calc")
        U.put(sh, 3, r, status, style="rp_calc")
        U.put(sh, 4, r, note, style="rp_note")
    last = 4 + len(steps) - 1
    ctx.name("START_STATUS", SH["start"], 3, 4, 3, last)
    U.cond_format(sh, 3, 4, 3, last,
                  [(f'{U.a1(3, 4)}="OK"', "rp_good"),
                   (f'{U.a1(3, 4)}="MISSING"', "rp_bad"),
                   (f'{U.a1(3, 4)}<>"OK"', "rp_warn")], base_addr=(3, 4))
    r = last + 2
    U.put(sh, 1, r, "Completeness", style="rp_h2")
    U.put(sh, 3, r, '=COUNTIF(START_STATUS,"OK")/COUNTA(START_STATUS)',
          style="rp_calc", fmt=ctx.fmt["pct"])
    U.put(sh, 4, r, '="Model self-test: "&AUDIT_OVERALL', style="rp_calc")
    U.put(sh, 1, r + 2, "Everything in this workbook is in today's money unless a "
          "column says otherwise.", style="rp_note")
    U.put(sh, 1, r + 3, "The projection needs no macros. The simulation does - install "
          "them with tools/install_macros.py.", style="rp_note")
    return sh


SCENARIO_INPUTS = [
    ("IN_P1_AGE", "Person 1 age"), ("IN_P1_RETIRE", "Person 1 retires"),
    ("IN_P1_DEATH", "Person 1 plans to"), ("IN_P2_AGE", "Person 2 age"),
    ("IN_P2_RETIRE", "Person 2 retires"), ("IN_P2_DEATH", "Person 2 plans to"),
    ("IN_HORIZON", "Years projected"), ("IN_INF_MEAN", "Inflation"),
    ("IN_INF_SD", "Inflation volatility"), ("IN_FEE_PLATFORM", "Platform fee"),
    ("IN_FEE_ADVISER", "Adviser fee"), ("IN_MKT_SEED", "Seed"),
    ("IN_MKT_TRIALS", "Trials"), ("IN_MKT_NU", "Student-t d.o.f."),
    ("IN_CR_PROB", "Crash probability"), ("IN_CR_MIN", "Crash depth min"),
    ("IN_CR_MODE", "Crash depth mode"), ("IN_CR_MAX", "Crash depth max"),
    ("IN_CR_REC", "Crash recovery"), ("IN_POL_PCT", "Percentage policy rate"),
    ("IN_POL_VPW", "VPW rate"), ("IN_POL_GUARD_UP", "Guardrail up"),
    ("IN_POL_GUARD_DN", "Guardrail down"), ("IN_POL_CUT", "Guardrail cut"),
    ("IN_POL_RAISE", "Guardrail raise"), ("IN_POL_LEGACY", "Legacy target"),
    ("IN_POL_CONF", "Confidence level"), ("IN_POL_DISC", "Discount rate"),
    ("IN_TX_SUR_RATE", "Surtax rate"), ("IN_TX_CG_INCL", "Gains inclusion"),
]
N_SCEN = 6


def scenarios(ctx):
    """Named scenarios: the current inputs can be parked in a slot and recalled.

    Only scalar assumptions are stored - the tables are shared. That covers the
    comparisons people actually make (retire earlier, spend more, worse markets)
    without duplicating the whole workbook.
    """
    P = ctx.fmt
    sh = ctx.sheet(SH["scen"])
    U.put(sh, 0, 0, "Scenarios", style="rp_title")
    U.put(sh, 0, 1, "Set the slot, press Save, change your assumptions, press Load to "
          "bring the old ones back. Needs macros; without them the columns are still "
          "a written record of what you tried.", style="rp_note")
    sh.Columns.getByIndex(0).Width = 6000
    sh.Columns.getByIndex(1).Width = 3200
    for i in range(N_SCEN):
        sh.Columns.getByIndex(2 + i).Width = 2800

    U.put(sh, 0, 3, "Active slot", style="rp_label")
    U.put(sh, 1, 3, 1, style="rp_input", fmt=P["int"])
    ctx.name("SCEN_SLOT", SH["scen"], 1, 3)
    U.validate_number(sh, 1, 3, 1, 3, 1, N_SCEN, whole=True, help_title="Slot",
                      help_text=f"Which of the {N_SCEN} scenario columns to use.")
    U.put(sh, 2, 3, "Status", style="rp_label")
    U.put(sh, 3, 3, "ready", style="rp_calc")
    ctx.name("SCEN_STATUS", SH["scen"], 3, 3)

    U.put(sh, 0, 5, "Assumption", style="rp_hdrcol")
    U.put(sh, 1, 5, "Live value", style="rp_hdrcol")
    for i in range(N_SCEN):
        U.put(sh, 2 + i, 5, f"Slot {i+1}", style="rp_hdrcol")
    U.put(sh, 0, 6, "Scenario name", style="rp_label")
    U.put(sh, 1, 6, "(current)", style="rp_calc")
    for i in range(N_SCEN):
        U.put(sh, 2 + i, 6, f"Scenario {i+1}", style="rp_input")
    ctx.name("SCEN_NAMES", SH["scen"], 2, 6, 1 + N_SCEN, 6)

    r0 = 7
    for j, (key, label) in enumerate(SCENARIO_INPUTS):
        r = r0 + j
        U.put(sh, 0, r, label, style="rp_label")
        U.put(sh, 1, r, f"={key}", style="rp_calc", fmt=P["num"])
        for i in range(N_SCEN):
            U.put(sh, 2 + i, r, None, style="rp_input", fmt=P["num"])
    ctx.name("SCEN_LIVE", SH["scen"], 1, r0, 1, r0 + len(SCENARIO_INPUTS) - 1)
    ctx.name("SCEN_STORE", SH["scen"], 2, r0, 1 + N_SCEN,
             r0 + len(SCENARIO_INPUTS) - 1)

    bx = 300
    for label, fn, tip in (("Save to slot", "save_scenario",
                            "Copy the live assumptions into the active slot"),
                           ("Load from slot", "load_scenario",
                            "Replace the live assumptions with the slot's")):
        U.add_button(ctx.doc, sh, label, bx, 2400, 3400, 900, MACRO.format(fn=fn),
                     name=f"btn_{fn}", tooltip=tip)
        bx += 3700
    return sh
