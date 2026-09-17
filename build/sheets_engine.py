"""The formula engine: one row per year, one named column per quantity.

Every intermediate is its own column, so any number on the Dashboard can be
traced back through visible arithmetic (CR-4).  The withdrawal cascade is the
interesting part: six stages, each resolving which account to draw from by
priority, how much of that draw is taxable, and the exact gross amount needed to
deliver the remaining net requirement - by inverting the band table, never by
iterating.
"""
from __future__ import annotations

import theme
import unohelp as U
from spec import N_LEDGER, N_WRAPPER, SH, T

# sheet geometry
R_TITLE, R_NOTE, R_GROUP = 0, 1, 2
R_WTXF, R_PEN, R_EARLY, R_LOCK, R_LIQ, R_CAPT, R_CAPV = 3, 4, 5, 6, 7, 8, 9
R_CG, R_CUA, R_CUV = 10, 11, 12
R_HDR = 14
R_DATA = 15


class Cols:
    """Symbolic column registry, so inserting a column never breaks a formula."""

    def __init__(self):
        self.idx = {}
        self.order = []

    def add(self, name, header, group="", fmt="money", width=1900):
        self.idx[name] = len(self.order)
        self.order.append(dict(name=name, header=header, group=group, fmt=fmt,
                               width=width))
        return self.idx[name]

    def block(self, prefix, n, header, group, fmt="money", width=1500):
        return [self.add(f"{prefix}{i+1}", f"{header} {i+1}", group, fmt, width)
                for i in range(n)]

    def __getitem__(self, name):
        return self.idx[name]

    def c(self, name, k=None):
        """A1 reference to a column, on the row for period k (or same-row)."""
        row = R_DATA + (0 if k is None else k)
        return U.a1(self.idx[name], row)

    def rng(self, first, last, k):
        row = R_DATA + k
        return f"{U.a1(self.idx[first], row)}:{U.a1(self.idx[last], row)}"


def define_columns():
    c = Cols()
    g = "Timeline"
    c.add("t", "t", g, "int", 800)
    c.add("year", "Year", g, "year", 1200)
    c.add("age1", "Age 1", g, "age", 1200)
    c.add("age2", "Age 2", g, "age", 1200)
    c.add("alive1", "Alive 1", g, "int", 1100)
    c.add("alive2", "Alive 2", g, "int", 1100)
    c.add("working", "Working?", g, "int", 1300)
    c.add("cpi", "CPI index", g, "num", 1500)
    c.add("bscale", "Band scale", g, "num", 1500)
    c.add("smidx", "Smile idx", g, "int", 1300)
    c.add("smile", "Smile mult", g, "num", 1500)

    g = "Income (real)"
    for n, h in (("incr", "Income real-basis"), ("incn", "Income nominal-basis"),
                 ("inc", "Income total"), ("itxr", "Taxable real-basis"),
                 ("itxn", "Taxable nominal-basis"), ("itx", "Taxable income"),
                 ("earnr", "Earnings real"), ("earnn", "Earnings nominal"),
                 ("earn", "Earnings total")):
        c.add(n, h, g)

    g = "Spending (real)"
    for n, h in (("essr", "Essential real-basis"), ("essn", "Essential nominal-basis"),
                 ("discr", "Discretionary real-basis"), ("discn", "Discretionary nominal-basis"),
                 ("ess", "Essential"), ("disc", "Discretionary"),
                 ("debtpay", "Debt service"), ("debtbal", "Debt balance")):
        c.add(n, h, g)

    c.block("open", N_LEDGER, "Opening", "Opening balance by account")
    c.block("frac", N_LEDGER, "Glide", "Glidepath fraction", "pct")
    c.block("rret", N_LEDGER, "Real return", "Real return by account", "pct2")
    c.block("feer", N_LEDGER, "Fee", "Fee rate by account", "pct2")
    c.block("basis", N_LEDGER, "Cost basis", "Cost basis by account")
    c.block("gainf", N_LEDGER, "Gain fraction", "Unrealised gain fraction", "pct")
    c.add("mrddiv", "MRD divisor", "Forced draws", "num")
    c.block("mrd", N_LEDGER, "Forced", "Forced draws")
    c.add("mrdtot", "Forced total", "Forced draws")
    c.add("mrdtax", "Forced taxable", "Forced draws")

    g = "Policy"
    c.add("portopen", "Portfolio opening", g)
    c.add("portliq", "Liquid portfolio", g)
    c.add("spend", "Spending target", g)
    c.add("taxbase", "Taxable base", g)
    c.add("taxinc", "Tax on income", g)
    c.add("need", "Net need", g)

    # Laid out one variable at a time across the six stages, NOT stage by stage:
    # the scatter back to accounts uses SUMPRODUCT over the stage vectors, which
    # requires each variable's six cells to be contiguous.
    for n, h, f in (("sidx", "Account", "int"), ("savail", "Available", "money"),
                    ("sf", "Taxable frac", "pct"), ("spen", "Penalty", "pct"),
                    ("sfeff", "Effective frac", "num"), ("sx0", "Stacked at", "money"),
                    ("stx0", "Tax at stack", "money"), ("sk", "Bands crossed", "int"),
                    ("sist", "Band index", "int"), ("swant", "Gross wanted", "money"),
                    ("stake", "Gross taken", "money"), ("stax", "Tax on draw", "money"),
                    ("snet", "Net delivered", "money"), ("srem", "Still needed", "money")):
        c.block(n, N_LEDGER, h, f"Withdrawal cascade - {h}", f, 1600)

    c.block("take", N_LEDGER, "Drawn", "Drawn by account")
    c.add("shortfall", "Shortfall", "Result", "money")
    c.add("surplus", "Surplus", "Contributions")
    c.block("cwant", N_LEDGER, "Wanted", "Contributions wanted")
    for n, h, f in (("cidx", "Account", "int"), ("cw", "Wanted", "money"),
                    ("ctk", "Paid in", "money"), ("crem", "Left", "money")):
        c.block(n, N_LEDGER, h, f"Contribution cascade - {h}", f, 1500)
    c.block("contr", N_LEDGER, "Paid in", "Contributions by account")
    c.block("sweep", N_LEDGER, "Swept", "Surplus sweep")
    c.block("close", N_LEDGER, "Closing", "Closing balance by account")

    g = "Result"
    for n, h, f in (("retamt", "Return earned", "money"),
                    ("feeamt", "Fees charged", "money"),
                    ("recon", "Reconciliation error", "money"),
                    ("wdtot", "Total drawn", "money"), ("taxwd", "Tax on draws", "money"),
                    ("taxtot", "Total tax", "money"), ("contrtot", "Total paid in", "money"),
                    ("feetot", "Total fees", "money"), ("portclose", "Portfolio close", "money"),
                    ("networth", "Net worth (real)", "money"),
                    ("nwnom", "Net worth (nominal)", "money"),
                    ("spendreal", "Spending delivered", "money"),
                    ("wdrate", "Withdrawal rate", "pct"),
                    ("cumtax", "Cumulative tax", "money"),
                    ("disc_pv", "PV of spending", "money"),
                    ("inc_pv", "PV of income", "money")):
        c.add(n, h, g, f, 2000)
    return c


def _tax_at(c, x_expr, k):
    """Band-table tax on a real amount, with the band scale applied."""
    b = c.c("bscale", k)
    return (f"SUMPRODUCT(TXO_R*({x_expr}>TXO_L*{b})*(({x_expr}<TXO_U*{b})*"
            f"({x_expr}-TXO_L*{b})+({x_expr}>=TXO_U*{b})*(TXO_U*{b}-TXO_L*{b})))")


def build(ctx):
    sh = ctx.sheet(SH["eng"])
    c = define_columns()
    U.put(sh, 0, R_TITLE, "Engine - deterministic projection, one row per year, "
          "all figures in today's money", style="rp_title")
    U.put(sh, 0, R_NOTE, "Calculated. Nothing here is typed. Every column is named and "
          "every step is visible - see docs/03-data-model.md for the calculation order.",
          style="rp_note")

    # --- aligned per-account constant rows (used by the cascade) -------------
    o0 = c["open1"]
    labels = {R_WTXF: ("Withdrawal taxable fraction", "INDEX(WR_WTXF,INDEX(LG_WR,{L}))"),
              R_PEN: ("Early penalty", "INDEX(WR_EP,INDEX(LG_WR,{L}))"),
              R_EARLY: ("Penalty before age", "INDEX(WR_EA,INDEX(LG_WR,{L}))"),
              R_LOCK: ("Locked until age", "INDEX(WR_LOCK,INDEX(LG_WR,{L}))"),
              R_LIQ: ("Liquid flag", 'IF(INDEX(WR_LIQ,INDEX(LG_WR,{L}))="Yes",1,0)'),
              R_CAPT: ("Cap type", 'MATCH(INDEX(WR_CAPT,INDEX(LG_WR,{L})),LST_CAPTYPE,0)'),
              R_CAPV: ("Cap value", "INDEX(WR_CAPV,INDEX(LG_WR,{L}))"),
              R_CG: ("Realises capital gains",
                     'IF(INDEX(WR_CG,INDEX(LG_WR,{L}))="Yes",1,0)'),
              R_CUA: ("Catch-up from age", "INDEX(WR_CUA,INDEX(LG_WR,{L}))"),
              R_CUV: ("Catch-up amount", "INDEX(WR_CUV,INDEX(LG_WR,{L}))")}
    names = {R_WTXF: "ENG_WTXF", R_PEN: "ENG_PEN", R_EARLY: "ENG_EARLY",
             R_LOCK: "ENG_LOCK", R_LIQ: "ENG_LIQ", R_CAPT: "ENG_CAPT",
             R_CAPV: "ENG_CAPV", R_CG: "ENG_CG", R_CUA: "ENG_CUA",
             R_CUV: "ENG_CUV"}
    for row, (lab, tmpl) in labels.items():
        U.put(sh, 0, row, lab, style="rp_note")
        for L in range(1, N_LEDGER + 1):
            U.put(sh, o0 + L - 1, row,
                  f"=IFERROR({tmpl.format(L=L)},0)", style="rp_calc")
        ctx.name(names[row], SH["eng"], o0, row, o0 + N_LEDGER - 1, row)
    U.put(sh, 0, R_GROUP, "Per-account constants resolved from the wrapper table",
          style="rp_note")

    # --- headers -------------------------------------------------------------
    for i, col in enumerate(c.order):
        U.put(sh, i, R_HDR - 1, col["group"], style="rp_note")
        U.put(sh, i, R_HDR, col["header"], style="rp_hdrcol")
        sh.Columns.getByIndex(i).Width = col["width"]
    sh.Rows.getByIndex(R_HDR).Height = 1000

    P = ctx.fmt
    for k in range(T + 1):
        r = R_DATA + k
        prev = k - 1

        def F(name, formula, fmt=None):
            col = c[name]
            U.put(sh, col, r, formula, style="rp_calc",
                  fmt=P.get(fmt or c.order[col]["fmt"], None))

        t = c.c("t", k)
        cpi = c.c("cpi", k)
        b = c.c("bscale", k)
        a1 = c.c("age1", k)

        F("t", k)
        F("year", f"=IN_START_YEAR+{t}")
        F("age1", f"=IN_P1_AGE+{t}")
        F("age2", f"=IN_P2_AGE+{t}")
        F("alive1", f"=IF({a1}<=IN_P1_DEATH,1,0)")
        F("alive2", f'=IF({c.c("age2", k)}<=IN_P2_DEATH,1,0)')
        F("working", f'=IF(OR({a1}<IN_P1_RETIRE,AND(IN_P2_AGE<>"",'
                     f'{c.c("age2", k)}<IN_P2_RETIRE)),1,0)')
        F("cpi", f"=(1+IN_INF_MEAN)^{t}")
        F("bscale", f'=IF(IN_TX_INDEX="Yes",1,1/{cpi})')
        F("smidx", f"=IFERROR(MAX(1,MIN(COUNT(SM_AGE)-1,MATCH({a1},SM_AGE,1))),1)")
        i_ = c.c("smidx", k)
        F("smile", f"=INDEX(SM_MULT,{i_})+(MIN(MAX({a1},INDEX(SM_AGE,1)),"
                   f"INDEX(SM_AGE,COUNT(SM_AGE)))-INDEX(SM_AGE,{i_}))/"
                   f"(INDEX(SM_AGE,{i_}+1)-INDEX(SM_AGE,{i_}))*"
                   f"(INDEX(SM_MULT,{i_}+1)-INDEX(SM_MULT,{i_}))")

        live = (f"({t}>=INC_T0)*({t}<=INC_T1)*(({t}<=INC_TD)+({t}>INC_TD)*INC_SV)"
                f"*(1+INC_G)^({t}-INC_GF0*INC_T0)")
        F("incr", f"=SUMPRODUCT(INC_KR*{live})")
        F("incn", f"=SUMPRODUCT(INC_KN*{live})")
        F("inc", f'={c.c("incr", k)}+{c.c("incn", k)}/{cpi}')
        F("itxr", f"=SUMPRODUCT(INC_KRT*{live})")
        F("itxn", f"=SUMPRODUCT(INC_KNT*{live})")
        F("itx", f'={c.c("itxr", k)}+{c.c("itxn", k)}/{cpi}')
        F("earnr", f"=SUMPRODUCT(INC_KR*(INC_CAT<=2)*{live})")
        F("earnn", f"=SUMPRODUCT(INC_KN*(INC_CAT<=2)*{live})")
        F("earn", f'={c.c("earnr", k)}+{c.c("earnn", k)}/{cpi}')

        sm = c.c("smile", k)
        elive = (f"({t}>=EXP_T0)*({t}<=EXP_T1)*(MOD({t}-EXP_T0,EXP_R)=0)"
                 f"*(1+EXP_DD)^{t}*((1-EXP_SM0)+EXP_SM0*{sm})")
        F("essr", f"=SUMPRODUCT(EXP_KER*{elive})")
        F("essn", f"=SUMPRODUCT(EXP_KEN*{elive})")
        F("discr", f"=SUMPRODUCT(EXP_KDR*{elive})")
        F("discn", f"=SUMPRODUCT(EXP_KDN*{elive})")
        F("ess", f'={c.c("essr", k)}+{c.c("essn", k)}/{cpi}')
        F("disc", f'={c.c("discr", k)}+{c.c("discn", k)}/{cpi}')
        F("debtpay", f"=INDEX(DBT_PAY,{k+1})/{cpi}")
        F("debtbal", f"=INDEX(DBT_BAL,{k+1})/{cpi}")

        for L in range(1, N_LEDGER + 1):
            if k == 0:
                F(f"open{L}", f"=INDEX(LG_OPEN,{L})*INDEX(LG_ACT,{L})")
            else:
                F(f"open{L}", f'={c.c(f"close{L}", prev)}')
            F(f"frac{L}", f"=IF(INDEX(LG_GA1,{L})<=INDEX(LG_GA0,{L}),1,"
                          f"MIN(1,MAX(0,({a1}-INDEX(LG_GA0,{L}))/"
                          f"(INDEX(LG_GA1,{L})-INDEX(LG_GA0,{L})))))")
            fr = c.c(f"frac{L}", k)
            F(f"rret{L}", f"=(1+INDEX(LG_MU0,{L})+{fr}*(INDEX(LG_MU1,{L})-"
                          f"INDEX(LG_MU0,{L})))/(1+IN_INF_MEAN)-1")
            F(f"feer{L}", f"=INDEX(LG_TER0,{L})+{fr}*(INDEX(LG_TER1,{L})-"
                          f"INDEX(LG_TER0,{L}))+IN_FEE_PLATFORM+IN_FEE_ADVISER")
        for L in range(1, N_LEDGER + 1):
            if k == 0:
                F(f"basis{L}", f"=INDEX(LG_BASIS,{L})*INDEX(LG_ACT,{L})")
            else:
                pb, po, pm = (c.c(f"basis{L}", prev), c.c(f"open{L}", prev),
                              c.c(f"mrd{L}", prev))
                F(f"basis{L}", f'=MAX(0,{pb}*(1-{c.c(f"take{L}", prev)}'
                               f'/MAX(0.000000001,{po}-{pm}))'
                               f'+{c.c(f"contr{L}", prev)}+{c.c(f"sweep{L}", prev)})')
        F("mrddiv", f"=IFERROR(INDEX(MRD_DIV,MATCH({a1},MRD_AGE,1)),1E9)")
        for L in range(1, N_LEDGER + 1):
            F(f"mrd{L}", f"=IF({a1}>=INDEX(WR_MRDA,INDEX(LG_WR,{L})),"
                         f'{c.c(f"open{L}", k)}/MAX(1,{c.c("mrddiv", k)}),0)')
        for L in range(1, N_LEDGER + 1):
            F(f"gainf{L}", f'=MAX(0,MIN(1,1-{c.c(f"basis{L}", k)}'
                           f'/MAX(0.000000001,{c.c(f"open{L}", k)}-{c.c(f"mrd{L}", k)})))')
        F("mrdtot", f'=SUM({c.rng("mrd1", f"mrd{N_LEDGER}", k)})')
        F("mrdtax", f'=SUMPRODUCT({c.rng("mrd1", f"mrd{N_LEDGER}", k)},ENG_WTXF)')
        F("portopen", f'=SUM({c.rng("open1", f"open{N_LEDGER}", k)})')
        F("portliq", f'=SUMPRODUCT({c.rng("open1", f"open{N_LEDGER}", k)},ENG_LIQ)')

        # spending policy
        port = c.c("portopen", k)
        ess, disc = c.c("ess", k), c.c("disc", k)
        F("spend", f'=IF(IN_POL_METHOD="fixed_nominal",({ess}+{disc})/{cpi},'
                   f'IF(IN_POL_METHOD="pct_portfolio",MAX({ess},IN_POL_PCT*{port}),'
                   f'IF(IN_POL_METHOD="vpw",MAX({ess},{port}*IF(IN_POL_VPW<0.000001,'
                   f'1/MAX(1,{T}-{t}),IN_POL_VPW/(1-(1+IN_POL_VPW)^-MAX(1,{T}-{t})))),'
                   f'IF(IN_POL_METHOD="table",MAX({ess},{port}/MAX(1,{T}-{t})),'
                   f"{ess}+{disc}))))")
        F("taxbase", f'={c.c("itx", k)}+{c.c("mrdtax", k)}')
        tb = c.c("taxbase", k)
        F("taxinc", f"={_tax_at(c, tb, k)}+MAX(0,{tb}-IN_TX_SUR_THR*{b})*IN_TX_SUR_RATE")
        F("need", f'=MAX(0,{c.c("spend", k)}+{c.c("debtpay", k)}+{c.c("taxinc", k)}'
                  f'-{c.c("inc", k)}-{c.c("mrdtot", k)})')

        # withdrawal cascade
        for j in range(1, N_LEDGER + 1):
            si = c.c(f"sidx{j}", k)
            F(f"sidx{j}", f"=IFERROR(MATCH({j},LG_WPRI,0),{j})")
            F(f"savail{j}", f'=MAX(0,(INDEX({c.rng("open1", f"open{N_LEDGER}", k)},{si})'
                            f'-INDEX({c.rng("mrd1", f"mrd{N_LEDGER}", k)},{si}))'
                            f"*INDEX(ENG_LIQ,{si})*IF({a1}>=INDEX(ENG_LOCK,{si}),1,0))")
            F(f"sf{j}", f"=IF(INDEX(ENG_CG,{si})=1,"
                        f'INDEX({c.rng("gainf1", f"gainf{N_LEDGER}", k)},{si})'
                        f"*IN_TX_CG_INCL,INDEX(ENG_WTXF,{si}))")
            F(f"spen{j}", f"=IF({a1}<INDEX(ENG_EARLY,{si}),INDEX(ENG_PEN,{si}),0)")
            f_, pen = c.c(f"sf{j}", k), c.c(f"spen{j}", k)
            F(f"sfeff{j}", f"={f_}/MAX(0.000001,1-{pen})")
            if j == 1:
                F(f"sx0{j}", f"={tb}")
                rem_in = c.c("need", k)
            else:
                F(f"sx0{j}", f'={c.c(f"sx0{j-1}", k)}+{c.c(f"sf{j-1}", k)}'
                             f'*{c.c(f"stake{j-1}", k)}')
                rem_in = c.c(f"srem{j-1}", k)
            x0 = c.c(f"sx0{j}", k)
            F(f"stx0{j}", f"={_tax_at(c, x0, k)}")
            tx0, fe = c.c(f"stx0{j}", k), c.c(f"sfeff{j}", k)
            F(f"sk{j}", f"=IF({fe}<0.000001,0,SUMPRODUCT((TXO_L*{b}>{x0})*"
                        f"(((TXO_L*{b}-{x0})/{fe}-(TXO_CT*{b}-{tx0}))<={rem_in})))")
            kk = c.c(f"sk{j}", k)
            F(f"sist{j}", f"=MIN(COUNT(TXO_L),MATCH({x0}/{b},TXO_L,1)+{kk})")
            ist = c.c(f"sist{j}", k)
            anchor = f"IF({kk}=0,{x0},INDEX(TXO_L,{ist})*{b})"
            neta = (f"IF({kk}=0,0,(INDEX(TXO_L,{ist})*{b}-{x0})/{fe}"
                    f"-(INDEX(TXO_CT,{ist})*{b}-{tx0}))")
            F(f"swant{j}", f"=IF({fe}<0.000001,{rem_in}/MAX(0.000001,1-{pen}),"
                           f"(({anchor}+({rem_in}-({neta}))/MAX(0.000001,1/{fe}"
                           f"-INDEX(TXO_R,{ist})))-{x0})/{fe}/MAX(0.000001,1-{pen}))")
            F(f"stake{j}", f'=MAX(0,MIN({c.c(f"savail{j}", k)},{c.c(f"swant{j}", k)}))')
            tk = c.c(f"stake{j}", k)
            F(f"stax{j}", f"={_tax_at(c, f'({x0}+{f_}*{tk})', k)}-{tx0}")
            F(f"snet{j}", f'={tk}*(1-{pen})-{c.c(f"stax{j}", k)}')
            F(f"srem{j}", f'=MAX(0,{rem_in}-{c.c(f"snet{j}", k)})')

        sidx_rng = c.rng("sidx1", f"sidx{N_LEDGER}", k)
        stake_rng = c.rng("stake1", f"stake{N_LEDGER}", k)
        for L in range(1, N_LEDGER + 1):
            F(f"take{L}", f"=SUMPRODUCT(({sidx_rng}={L})*{stake_rng})")
        F("shortfall", f'={c.c(f"srem{N_LEDGER}", k)}')

        # contributions
        F("surplus", f'=MAX(0,{c.c("inc", k)}+{c.c("mrdtot", k)}-{c.c("spend", k)}'
                     f'-{c.c("debtpay", k)}-{c.c("taxinc", k)})')
        earn = c.c("earn", k)
        wk = c.c("working", k)
        for L in range(1, N_LEDGER + 1):
            F(f"cwant{L}", f"=IF({wk}=0,0,MIN(IF(INDEX(ENG_CAPT,{L})=1,1E12,"
                           f"IF(INDEX(ENG_CAPT,{L})=2,INDEX(ENG_CAPV,{L}),"
                           f"INDEX(ENG_CAPV,{L})*{earn}))+IF({a1}>="
                           f"INDEX(ENG_CUA,{L}),INDEX(ENG_CUV,{L}),0),INDEX(LG_CONTR,{L})"
                           f"+INDEX(LG_CPCT,{L})*{earn}+MIN(INDEX(LG_CPCT,{L}),"
                           f"INDEX(LG_MCAP,{L}))*{earn}*INDEX(LG_MATCH,{L})))")
        cwant_rng = c.rng("cwant1", f"cwant{N_LEDGER}", k)
        for j in range(1, N_LEDGER + 1):
            ci = c.c(f"cidx{j}", k)
            F(f"cidx{j}", f"=IFERROR(MATCH({j},LG_CPRI,0),{j})")
            F(f"cw{j}", f"=INDEX({cwant_rng},{ci})")
            src = c.c("surplus", k) if j == 1 else c.c(f"crem{j-1}", k)
            F(f"ctk{j}", f'=MIN({src},{c.c(f"cw{j}", k)})')
            F(f"crem{j}", f'={src}-{c.c(f"ctk{j}", k)}')
        cidx_rng = c.rng("cidx1", f"cidx{N_LEDGER}", k)
        ctk_rng = c.rng("ctk1", f"ctk{N_LEDGER}", k)
        for L in range(1, N_LEDGER + 1):
            F(f"contr{L}", f"=SUMPRODUCT(({cidx_rng}={L})*{ctk_rng})")
            F(f"sweep{L}", f'=IF({L}=IN_POL_SWEEP,{c.c(f"crem{N_LEDGER}", k)},0)')
            grow = ("" if k == T else
                    f'*(1-{c.c(f"feer{L}", k)})*(1+{c.c(f"rret{L}", k)})')
            F(f"close{L}", f'=MAX(0,({c.c(f"open{L}", k)}-{c.c(f"mrd{L}", k)}'
                           f'-{c.c(f"take{L}", k)}+{c.c(f"contr{L}", k)}'
                           f'+{c.c(f"sweep{L}", k)}){grow})')

        base_terms = "+".join(
            f'({c.c(f"open{L}", k)}-{c.c(f"mrd{L}", k)}-{c.c(f"take{L}", k)}'
            f'+{c.c(f"contr{L}", k)}+{c.c(f"sweep{L}", k)})*(1-{c.c(f"feer{L}", k)})'
            f'*{c.c(f"rret{L}", k)}' for L in range(1, N_LEDGER + 1))
        F("retamt", "=0" if k == T else f"={base_terms}")
        fee_terms = "+".join(
            f'({c.c(f"open{L}", k)}-{c.c(f"mrd{L}", k)}-{c.c(f"take{L}", k)}'
            f'+{c.c(f"contr{L}", k)}+{c.c(f"sweep{L}", k)})*{c.c(f"feer{L}", k)}'
            for L in range(1, N_LEDGER + 1))
        F("feeamt", "=0" if k == T else f"={fee_terms}")
        F("wdtot", f'=SUM({c.rng("take1", f"take{N_LEDGER}", k)})+{c.c("mrdtot", k)}')
        F("taxwd", f'=SUM({c.rng("stax1", f"stax{N_LEDGER}", k)})')
        F("taxtot", f'={c.c("taxinc", k)}+{c.c("taxwd", k)}')
        F("contrtot", f'=SUM({c.rng("contr1", f"contr{N_LEDGER}", k)})'
                      f'+SUM({c.rng("sweep1", f"sweep{N_LEDGER}", k)})')
        F("feetot", f'={c.c("feeamt", k)}')
        F("recon", f'={c.c("portclose", k)}-({c.c("portopen", k)}-{c.c("mrdtot", k)}'
                   f'-SUM({c.rng("take1", f"take{N_LEDGER}", k)})+{c.c("contrtot", k)}'
                   f'-{c.c("feeamt", k)}+{c.c("retamt", k)})')
        F("portclose", f'=SUM({c.rng("close1", f"close{N_LEDGER}", k)})')
        F("networth", f'={c.c("portclose", k)}-{c.c("debtbal", k)}')
        F("nwnom", f'={c.c("networth", k)}*{cpi}')
        F("spendreal", f'={c.c("spend", k)}+{c.c("debtpay", k)}-{c.c("shortfall", k)}')
        F("wdrate", f'=IF({port}<=0,0,({c.c("wdtot", k)})/{port})')
        F("cumtax", f'={c.c("taxtot", k)}' if k == 0 else
          f'={c.c("cumtax", prev)}+{c.c("taxtot", k)}')
        F("disc_pv", f'={c.c("spend", k)}/(1+IN_POL_DISC)^{t}')
        F("inc_pv", f'={c.c("inc", k)}/(1+IN_POL_DISC)^{t}')

    # named ranges for every engine column, for charts, reports and macros
    for i, col in enumerate(c.order):
        ctx.name(f"ENGC_{col['name'].upper()}", SH["eng"], i, R_DATA, i, R_DATA + T)
    ctx.name("ENG_ALL", SH["eng"], 0, R_DATA, len(c.order) - 1, R_DATA + T)
    sh.Rows.getByIndex(R_DATA).Height = 400
    return sh, c
