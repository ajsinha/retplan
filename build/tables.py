"""Concrete table definitions for the input sheets, with worked sample data."""
from __future__ import annotations

from spec import (N_ASSET, N_BAND, N_EXPENSE, N_INCOME, N_LEDGER, N_LOAN, N_MRD,
                  N_REGIME, N_SMILE, N_WRAPPER, SH)

W = dict(narrow=1700, med=2300, wide=3400, label=4600)


def income_columns():
    c = [
        dict(header="#", kind="id", width=800),
        dict(header="On?", kind="text", enum="YESNO", width=1200, name="INC_EN"),
        dict(header="Label", kind="text", width=W["label"]),
        dict(header="Owner\n(1 or 2)", kind="int", lo=1, hi=2, width=1300, name="INC_OWN",
             help="Which person this income belongs to."),
        dict(header="Category", kind="text", enum="CATEGORY", width=2600, name="INC_CATT"),
        dict(header="Amount\nper year", kind="money", lo=0, hi=1e12, width=2600,
             fmt="money", name="INC_AMT",
             help="Gross, before tax, in the basis chosen in the next column."),
        dict(header="Basis", kind="text", enum="BASIS", width=1600, name="INC_BASIS",
             help="real = today's money and it keeps pace with inflation. "
                  "nominal = a fixed number of future currency units."),
        dict(header="Growth\n%/yr", kind="pct", lo=-0.5, hi=0.5, width=1600, fmt="pct2",
             name="INC_G", help="Growth in the chosen basis. Real basis + 1% = 1% above inflation."),
        dict(header="Grow from", kind="text", enum="GROWTH", width=2000, name="INC_GFROM"),
        dict(header="Start\nage", kind="age", lo=0, hi=120, width=1400, name="INC_A0"),
        dict(header="End\nage", kind="age", lo=0, hi=130, width=1400, name="INC_A1"),
        dict(header="Taxable\nfraction", kind="pct", lo=0, hi=1, width=1700, fmt="pct",
             name="INC_TAXF", help="1 = fully taxable, 0 = tax free, 0.75 = a 25% tax-free element."),
        dict(header="Survivor\n%", kind="pct", lo=0, hi=1, width=1600, fmt="pct",
             name="INC_SURV", help="Share that continues after the owner dies."),
        dict(header="Prob.", kind="pct", lo=0, hi=1, width=1300, fmt="pct", name="INC_PROB",
             help="Below 1 scales the amount in the projection and is drawn at random in simulation."),
        dict(header="Notes", kind="text", width=4000),
    ]
    calc = [
        ("INC_AGE0", '=IF({own}{r}=2,IN_P2_AGE,IN_P1_AGE)', "age"),
        ("INC_T0", '=MAX(0,{a0}{r}-{age0}{r})', "num"),
        ("INC_T1", '=IF({a1}{r}="",999,{a1}{r}-{age0}{r})', "num"),
        ("INC_TD", '=IF({own}{r}=2,IN_P2_DEATH,IN_P1_DEATH)-{age0}{r}', "num"),
        ("INC_ACT", '=IF(AND({en}{r}="Yes",N({amt}{r})>0),1,0)', "int"),
        ("INC_GF0", '=IF({gf}{r}="stream start",1,0)', "int"),
        ("INC_KR", '={act}{r}*IF({bas}{r}="real",1,0)*{amt}{r}*IF({prob}{r}="",1,{prob}{r})', "money"),
        ("INC_KN", '={act}{r}*IF({bas}{r}="nominal",1,0)*{amt}{r}*IF({prob}{r}="",1,{prob}{r})', "money"),
        ("INC_KRT", '={kr}{r}*IF({txf}{r}="",1,{txf}{r})', "money"),
        ("INC_KNT", '={kn}{r}*IF({txf}{r}="",1,{txf}{r})', "money"),
        ("INC_SV", '=IF({sv}{r}="",0,{sv}{r})', "pct"),
        ("INC_CAT", '=IFERROR(MATCH({cat}{r},{catlist},0),0)', "int"),
    ]
    return c, calc


INCOME_SAMPLE = [
    [None, "Yes", "Salary - person 1", 1, "employment", 95000, "real", 0.01, "plan start",
     45, 65, 1, 0, 1, "Grows 1% above inflation"],
    [None, "Yes", "Salary - person 2", 2, "employment", 62000, "real", 0.005, "plan start",
     43, 65, 1, 0, 1, ""],
    [None, "Yes", "State pension - person 1", 1, "state_pension", 11500, "real", 0,
     "plan start", 67, 130, 1, 0.5, 1, "Indexed, half continues to survivor"],
    [None, "Yes", "State pension - person 2", 2, "state_pension", 11500, "real", 0,
     "plan start", 67, 130, 1, 0.5, 1, ""],
    [None, "Yes", "Final salary pension", 1, "db_pension", 9000, "real", 0, "plan start",
     65, 130, 1, 0.5, 1, "CPI linked, 50% survivor"],
    [None, "Yes", "Rental income (net)", 1, "rental", 8400, "real", 0, "plan start",
     45, 130, 1, 1, 1, "After voids and maintenance"],
    [None, "No", "Inheritance", 1, "one_off", 150000, "real", 0, "plan start", 70, 70,
     0, 1, 0.6, "60% likely - off by default"],
    [None, "Yes", "Part-time consulting", 1, "self_employment", 18000, "real", 0,
     "plan start", 65, 70, 1, 0, 1, "Phased retirement"],
]


def expense_columns():
    c = [
        dict(header="#", kind="id", width=800),
        dict(header="On?", kind="text", enum="YESNO", width=1200, name="EXP_EN"),
        dict(header="Label", kind="text", width=W["label"]),
        dict(header="Amount\nper year", kind="money", lo=0, hi=1e12, width=2600,
             fmt="money", name="EXP_AMT"),
        dict(header="Basis", kind="text", enum="BASIS", width=1600, name="EXP_BASIS"),
        dict(header="Essential?", kind="text", enum="YESNO", width=1800, name="EXP_ESS",
             help="Essential spending is a floor: no flexible policy is allowed to cut it."),
        dict(header="Real growth\nabove CPI", kind="pct", lo=-0.1, hi=0.15, width=2000,
             fmt="pct2", name="EXP_D",
             help="Healthcare and care costs typically run 1-3% above general inflation."),
        dict(header="Age\ncurve?", kind="text", enum="YESNO", width=1500, name="EXP_SM",
             help="Apply the spending smile - real spending drifts down through retirement."),
        dict(header="Start\nage", kind="age", lo=0, hi=120, width=1400, name="EXP_A0"),
        dict(header="End\nage", kind="age", lo=0, hi=130, width=1400, name="EXP_A1"),
        dict(header="Every\nN years", kind="int", lo=0, hi=50, width=1500, name="EXP_REC",
             help="0 or 1 = every year. 8 = a car every eight years."),
        dict(header="Whose\nage", kind="int", lo=1, hi=2, width=1400, name="EXP_OWN"),
        dict(header="Prob.", kind="pct", lo=0, hi=1, width=1300, fmt="pct", name="EXP_PROB"),
        dict(header="Notes", kind="text", width=4000),
    ]
    calc = [
        ("EXP_AGE0", '=IF({own}{r}=2,IN_P2_AGE,IN_P1_AGE)', "age"),
        ("EXP_T0", '=MAX(0,{a0}{r}-{age0}{r})', "num"),
        ("EXP_T1", '=IF({a1}{r}="",999,{a1}{r}-{age0}{r})', "num"),
        ("EXP_ACT", '=IF(AND({en}{r}="Yes",N({amt}{r})>0),1,0)', "int"),
        ("EXP_R", '=MAX(1,IF({rec}{r}="",1,{rec}{r}))', "int"),
        ("EXP_SM0", '=IF({sm}{r}="Yes",1,0)', "int"),
        ("EXP_KER", '={act}{r}*IF({bas}{r}="real",1,0)*IF({ess}{r}="Yes",1,0)*{amt}{r}*IF({prob}{r}="",1,{prob}{r})', "money"),
        ("EXP_KDR", '={act}{r}*IF({bas}{r}="real",1,0)*IF({ess}{r}="Yes",0,1)*{amt}{r}*IF({prob}{r}="",1,{prob}{r})', "money"),
        ("EXP_KEN", '={act}{r}*IF({bas}{r}="nominal",1,0)*IF({ess}{r}="Yes",1,0)*{amt}{r}*IF({prob}{r}="",1,{prob}{r})', "money"),
        ("EXP_KDN", '={act}{r}*IF({bas}{r}="nominal",1,0)*IF({ess}{r}="Yes",0,1)*{amt}{r}*IF({prob}{r}="",1,{prob}{r})', "money"),
        ("EXP_DD", '=IF({d}{r}="",0,{d}{r})', "pct"),
    ]
    return c, calc


EXPENSE_SAMPLE = [
    [None, "Yes", "Housing, utilities, council tax", 14000, "real", "Yes", 0, "No", 45, 130, 0, 1, 1, ""],
    [None, "Yes", "Food and household", 9000, "real", "Yes", 0, "No", 45, 130, 0, 1, 1, ""],
    [None, "Yes", "Transport", 5200, "real", "Yes", 0, "Yes", 45, 130, 0, 1, 1, ""],
    [None, "Yes", "Insurance and health", 3600, "real", "Yes", 0.02, "No", 45, 130, 0, 1, 1,
     "Rises 2% above CPI"],
    [None, "Yes", "Travel and leisure", 9000, "real", "No", 0, "Yes", 45, 85, 0, 1, 1,
     "Discretionary, fades with age"],
    [None, "Yes", "Hobbies, gifts, everything else", 6000, "real", "No", 0, "Yes", 45, 130, 0, 1, 1, ""],
    [None, "Yes", "Car replacement", 22000, "real", "No", 0, "No", 46, 86, 8, 1, 1,
     "Every 8 years"],
    [None, "Yes", "Home maintenance fund", 3000, "real", "Yes", 0, "No", 45, 130, 0, 1, 1, ""],
    [None, "Yes", "University support", 12000, "real", "No", 0.03, "No", 50, 54, 0, 1, 1,
     "Education inflation 3% above CPI"],
    [None, "No", "Long-term care", 55000, "real", "Yes", 0.02, "No", 88, 93, 0, 1, 0.4,
     "Off by default - switch on to stress the plan"],
]


def loan_columns():
    c = [
        dict(header="#", kind="id", width=800),
        dict(header="On?", kind="text", enum="YESNO", width=1200, name="LN_EN"),
        dict(header="Label", kind="text", width=W["label"]),
        dict(header="Balance\nnow", kind="money", lo=0, hi=1e12, width=2600, fmt="money",
             name="LN_BAL"),
        dict(header="Rate\n%/yr", kind="pct", lo=0, hi=0.5, width=1600, fmt="pct2", name="LN_R"),
        dict(header="Years\nleft", kind="int", lo=1, hi=60, width=1400, name="LN_N"),
        dict(header="Type", kind="text", enum="LOANKIND", width=2200, name="LN_KIND"),
        dict(header="Extra\npayment", kind="money", lo=0, hi=1e9, width=2000, fmt="money",
             name="LN_EX", help="Overpayment per year, nominal."),
        dict(header="Starts in\nyear", kind="int", lo=0, hi=60, width=1600, name="LN_ST"),
        dict(header="Notes", kind="text", width=4000),
    ]
    calc = [
        ("LN_ACT", '=IF(AND({en}{r}="Yes",N({bal}{r})>0),1,0)', "int"),
        ("LN_PAY", '=IF({act}{r}=0,0,IF({kind}{r}="interest_only",{bal}{r}*{rate}{r},'
                   'IF({kind}{r}="bullet",0,IF({rate}{r}<0.000001,{bal}{r}/{n}{r},'
                   '{bal}{r}*{rate}{r}/(1-(1+{rate}{r})^-{n}{r})))))', "money"),
    ]
    return c, calc


LOAN_SAMPLE = [
    [None, "Yes", "Mortgage", 185000, 0.042, 17, "amortising", 0, 0, "Main home"],
    [None, "No", "Car loan", 12000, 0.069, 4, "amortising", 0, 0, ""],
]


def wrapper_columns():
    c = [
        dict(header="#", kind="id", width=800),
        dict(header="Label", kind="text", width=3000, name="WR_LAB"),
        dict(header="Contribution\ndeductible", kind="pct", lo=0, hi=1, width=2100,
             fmt="pct", name="WR_DED",
             help="Share of a contribution that reduces taxable income (the first E in EET)."),
        dict(header="Growth taxed\nyearly?", kind="text", enum="YESNO", width=2000,
             name="WR_GTX", help="Interest and dividends taxed as they arise."),
        dict(header="Growth taxable\nfraction", kind="pct", lo=0, hi=1, width=2100,
             fmt="pct", name="WR_GTXF"),
        dict(header="Withdrawal\ntaxable fraction", kind="pct", lo=0, hi=1, width=2300,
             fmt="pct", name="WR_WTXF",
             help="1 = fully taxed on the way out (EET). 0 = tax free (TEE). "
                  "0.75 = a 25% tax-free lump sum."),
        dict(header="Realises\ncapital gains?", kind="text", enum="YESNO", width=2100,
             name="WR_CG"),
        dict(header="Cap type", kind="text", enum="CAPTYPE", width=1900, name="WR_CAPT"),
        dict(header="Cap value", kind="money", lo=0, hi=1e9, width=2000, fmt="money",
             name="WR_CAPV"),
        dict(header="Catch-up\nfrom age", kind="age", lo=0, hi=130, width=1700, name="WR_CUA"),
        dict(header="Catch-up\namount", kind="money", lo=0, hi=1e9, width=1800, fmt="money",
             name="WR_CUV"),
        dict(header="Penalty\nbefore age", kind="age", lo=0, hi=130, width=1800, name="WR_EA"),
        dict(header="Early\npenalty", kind="pct", lo=0, hi=0.5, width=1600, fmt="pct",
             name="WR_EP"),
        dict(header="Forced\ndraw from age", kind="age", lo=0, hi=130, width=1900,
             name="WR_MRDA", help="Minimum distributions start here. 999 = never."),
        dict(header="Locked\nuntil age", kind="age", lo=0, hi=130, width=1700, name="WR_LOCK"),
        dict(header="Liquid?", kind="text", enum="YESNO", width=1500, name="WR_LIQ"),
        dict(header="Notes", kind="text", width=4200),
    ]
    return c, []


WRAPPER_SAMPLE = [
    [None, "Taxable brokerage (TEE)", 0, "Yes", 1.0, 0, "Yes", "none", 0, 999, 0, 0, 0,
     999, 0, "Yes", "Taxed on income and on gains when sold"],
    [None, "Pension / 401k style (EET)", 1.0, "No", 0, 1.0, "No", "pct_income", 0.20, 50,
     8000, 60, 0.10, 75, 55, "Yes", "Deductible in, taxed out, forced draws from 75"],
    [None, "Roth / ISA style (TEE)", 0, "No", 0, 0, "No", "absolute", 20000, 999, 0, 0, 0,
     999, 0, "Yes", "No relief in, nothing taxed ever again"],
    [None, "Cash savings", 0, "Yes", 1.0, 0, "No", "none", 0, 999, 0, 0, 0, 999, 0, "Yes",
     "Interest taxed yearly"],
    [None, "Property (illiquid)", 0, "No", 0, 0, "Yes", "none", 0, 999, 0, 0, 0, 999, 0,
     "No", "Excluded from drawdown unless sold"],
]


def ledger_columns():
    c = [
        dict(header="#", kind="id", width=800),
        dict(header="On?", kind="text", enum="YESNO", width=1200, name="LG_EN"),
        dict(header="Account label", kind="text", width=3400),
        dict(header="Owner", kind="int", lo=1, hi=2, width=1300, name="LG_OWN"),
        dict(header="Wrapper #", kind="int", lo=1, hi=N_WRAPPER, width=1600, name="LG_WR",
             help="Row number from In-Wrappers. This is what makes the model generic: "
                  "the account carries a balance, the wrapper carries the tax rules."),
        dict(header="Opening\nbalance", kind="money", lo=0, hi=1e12, width=2600,
             fmt="money", name="LG_OPEN"),
        dict(header="Cost\nbasis", kind="money", lo=0, hi=1e12, width=2200, fmt="money",
             name="LG_BASIS"),
    ] + [
        dict(header=f"w{i+1}\nnow", kind="pct", lo=0, hi=1, width=1200, fmt="pct",
             name=f"LG_W{i+1}") for i in range(N_ASSET)
    ] + [
        dict(header=f"w{i+1}\nend", kind="pct", lo=0, hi=1, width=1200, fmt="pct",
             name=f"LG_V{i+1}") for i in range(N_ASSET)
    ] + [
        dict(header="Glide\nfrom age", kind="age", lo=0, hi=130, width=1600, name="LG_GA0"),
        dict(header="Glide\nto age", kind="age", lo=0, hi=130, width=1600, name="LG_GA1"),
        dict(header="Draw\norder", kind="int", lo=1, hi=N_LEDGER, width=1500, name="LG_WPRI",
             help="1 is drawn from first. Ties are broken by row order."),
        dict(header="Pay-in\norder", kind="int", lo=1, hi=N_LEDGER, width=1500, name="LG_CPRI"),
        dict(header="Contribution\nper year", kind="money", lo=0, hi=1e9, width=2200,
             fmt="money", name="LG_CONTR"),
        dict(header="% of\nearnings", kind="pct", lo=0, hi=1, width=1600, fmt="pct",
             name="LG_CPCT"),
        dict(header="Employer\nmatch %", kind="pct", lo=0, hi=2, width=1700, fmt="pct",
             name="LG_MATCH"),
        dict(header="Match\ncap %", kind="pct", lo=0, hi=1, width=1500, fmt="pct",
             name="LG_MCAP"),
        dict(header="Rebalance", kind="text", enum="REBAL", width=1800, name="LG_REB"),
    ]
    calc = [
        ("LG_ACT", '=IF({en}{r}="Yes",1,0)', "int"),
        ("LG_WSUM", '=SUM({w1}{r}:{w6}{r})', "pct"),
        ("LG_VSUM", '=SUM({v1}{r}:{v6}{r})', "pct"),
        ("LG_MU0", '=SUMPRODUCT({w1}{r}:{w6}{r},AST_MU)', "pct2"),
        ("LG_MU1", '=IF({vsum}{r}=0,{mu0}{r},SUMPRODUCT({v1}{r}:{v6}{r},AST_MU))', "pct2"),
        ("LG_TER0", '=SUMPRODUCT({w1}{r}:{w6}{r},AST_TER)', "pct2"),
        ("LG_TER1", '=IF({vsum}{r}=0,{ter0}{r},SUMPRODUCT({v1}{r}:{v6}{r},AST_TER))', "pct2"),
        ("LG_CHK", '=IF({act}{r}=0,"-",IF(ABS({wsum}{r}-1)>0.001,"WEIGHTS<>100%","OK"))', "text"),
    ]
    return c, calc


LEDGER_SAMPLE = [
    #      on   label                   own wr  open    basis  w1..w6                       v1..v6                       ga0 ga1  wp cp contr cpct match mcap rebal
    [None, "Yes", "Joint brokerage",      1,  1, 120000, 95000, 0.70, 0.20, 0.05, 0.05, 0, 0, 0.45, 0.40, 0.10, 0.05, 0, 0, 55, 75, 1, 4, 6000, 0,    0,   0,   "annual"],
    [None, "Yes", "Workplace pension P1", 1,  2, 310000, 0,     0.80, 0.15, 0.00, 0.05, 0, 0, 0.45, 0.45, 0.05, 0.05, 0, 0, 55, 70, 3, 1, 0,    0.08, 1.0, 0.05, "annual"],
    [None, "Yes", "Workplace pension P2", 2,  2, 185000, 0,     0.80, 0.15, 0.00, 0.05, 0, 0, 0.45, 0.45, 0.05, 0.05, 0, 0, 55, 70, 4, 2, 0,    0.06, 1.0, 0.04, "annual"],
    [None, "Yes", "Tax-free account",     1,  3,  95000, 95000, 0.85, 0.10, 0.00, 0.05, 0, 0, 0.55, 0.35, 0.05, 0.05, 0, 0, 55, 75, 2, 3, 4000, 0,    0,   0,   "annual"],
    [None, "Yes", "Cash reserve",         1,  4,  35000, 35000, 0,    0,    0,    1.0,  0, 0, 0,    0,    0,    1.0,  0, 0, 55, 75, 5, 5, 0,    0,    0,   0,   "annual"],
    [None, "Yes", "Rental property",      1,  5, 240000, 180000, 0,   0,    1.0,  0,    0, 0, 0,    0,    1.0,  0,    0, 0, 55, 75, 6, 6, 0,    0,    0,   0,   "none"],
]
