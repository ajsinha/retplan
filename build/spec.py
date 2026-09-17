"""Workbook dimensions and the declarative input specification.

Sizes are build parameters, not constants scattered through the code: raising
N_INCOME or N_WRAPPER and rebuilding is all it takes to grow the model.
"""

T = 60              # planning horizon in years (rows 0..T in the engine)
N_INCOME = 100      # reserved income rows
N_EXPENSE = 100     # reserved expense rows
N_LOAN = 10
N_LEDGER = 6        # account ledgers, each mapped to a wrapper
N_WRAPPER = 6       # tax wrapper definitions
N_ASSET = 6
N_BAND = 8          # tax bands per schedule
N_REGIME = 3
N_SCENARIO = 6
N_SMILE = 6
N_MRD = 12

SH = dict(
    readme="Read Me", start="Start Here", house="In-Household", income="In-Income",
    expense="In-Expenses", debt="In-Debt", acct="In-Accounts", wrap="In-Wrappers",
    market="In-Markets", tax="In-Tax", policy="In-Policy", scen="Scenarios",
    lists="Lists", eng="Eng-Core", engd="Eng-Debt", sim="Sim-Control",
    simres="Sim-Results", simpaths="Sim-Paths", chart="ChartData", dash="Dashboard",
    repcf="Rep-Cashflow", repbal="Rep-Balance", reptax="Rep-Tax",
    repass="Rep-Assumptions", audit="Audit",
)

ENUMS = {
    "YESNO": ["Yes", "No"],
    "BASIS": ["real", "nominal"],
    "CATEGORY": ["employment", "self_employment", "rental", "db_pension",
                 "state_pension", "annuity", "other_taxable", "tax_free", "one_off"],
    "GROWTH": ["plan start", "stream start"],
    "CAPTYPE": ["none", "absolute", "pct_income"],
    "REBAL": ["annual", "none"],
    "POLICY": ["fixed_real", "fixed_nominal", "pct_portfolio", "vpw", "guardrails",
               "table"],
    "RETMODE": ["fixed", "mc", "historical", "path"],
    "DIST": ["lognormal", "normal", "t"],
    "INFLMODE": ["fixed", "stochastic", "path"],
    "STARTREG": ["stationary", "random", "0", "1", "2"],
    "DISPLAY": ["real", "nominal"],
    "TIMING": ["begin", "mid", "end"],
    "MODE": ["Basic", "Advanced", "Expert"],
    "FILING": ["individual", "joint"],
    "LOANKIND": ["amortising", "interest_only", "bullet"],
}

# --- scalar input sheets: (key, label, default, kind, unit, lo, hi, help) ---
# kind: money | pct | num | int | age | list:<ENUM> | text | header | note

HOUSEHOLD = [
    ("header", "Who the plan is for", None, None, None, None, None, None),
    ("P1_NAME", "Person 1 name", "Person 1", "text", "", None, None,
     "A label only - no personal data is needed anywhere in this file."),
    ("P1_AGE", "Person 1 age now", 45, "age", "years", 0, 110,
     "Age at the plan start date. Every age-based rule is measured from here."),
    ("P1_RETIRE", "Person 1 retirement age", 65, "age", "years", 30, 90,
     "The age at which employment income stops and drawdown may begin."),
    ("P1_DEATH", "Person 1 planning age", 95, "age", "years", 50, 115,
     "Plan to this age. Longevity risk is the one risk you cannot diversify: "
     "planning to life expectancy leaves roughly half the outcomes short."),
    ("P2_NAME", "Person 2 name", "Person 2", "text", "", None, None,
     "Leave the age blank if the plan covers one person."),
    ("P2_AGE", "Person 2 age now", 43, "age", "years", 0, 110, "Blank = no second person."),
    ("P2_RETIRE", "Person 2 retirement age", 65, "age", "years", 30, 90, ""),
    ("P2_DEATH", "Person 2 planning age", 97, "age", "years", 50, 115, ""),
    ("header", "Timeline and presentation", None, None, None, None, None, None),
    ("START_YEAR", "Plan start year", 2026, "int", "year", 1900, 2200,
     "Year zero of the projection."),
    ("HORIZON", "Years to project", T, "int", "years", 1, T,
     f"Capped at the built horizon of {T} years."),
    ("DISPLAY", "Show money as", "real", "list:DISPLAY", "",  None, None,
     "Real = today's purchasing power (recommended). Nominal = future currency, "
     "which flatters every long-horizon number."),
    ("TIMING", "Cash-flow timing", "end", "list:TIMING", "", None, None,
     "When within each year flows are assumed to happen."),
    ("CURRENCY", "Currency symbol", "$", "text", "", None, None,
     "Presentation only - it never affects a calculation."),
    ("MODE", "Detail level", "Advanced", "list:MODE", "", None, None,
     "Basic hides the advanced rows; nothing is switched off, only hidden."),
    ("header", "Survivor assumptions", None, None, None, None, None, None),
    ("SURV_EXP", "Expenses after first death", 0.70, "pct", "of joint", 0.3, 1.0,
     "Two cannot live as cheaply as one, but nor does spending halve. 65-75% is typical."),
    ("SURV_FILING", "Tax filing after first death", "individual", "list:FILING", "",
     None, None, "Many systems tax a survivor more harshly than a couple."),
]

POLICY = [
    ("header", "How much you take, and how it flexes", None, None, None, None, None, None),
    ("POL_METHOD", "Withdrawal policy", "fixed_real", "list:POLICY", "", None, None,
     "fixed_real spends the same purchasing power every year. guardrails cuts after "
     "bad markets and raises after good ones, which historically supports a higher "
     "starting spend at the same risk."),
    ("POL_PCT", "Percentage of portfolio", 0.04, "pct", "per year", 0.0, 0.20,
     "Used by the pct_portfolio policy. Never runs out, but income swings with markets."),
    ("POL_VPW", "VPW assumed real return", 0.035, "pct", "per year", -0.02, 0.12,
     "Used by the amortisation policy to spread the portfolio over the remaining years."),
    ("POL_GUARD_UP", "Guardrail: upper trigger", 0.20, "pct", "above initial rate", 0.0, 1.0,
     "If the withdrawal rate rises this far above its starting level, spending is cut."),
    ("POL_GUARD_DN", "Guardrail: lower trigger", 0.20, "pct", "below initial rate", 0.0, 1.0,
     "If the rate falls this far below its starting level, spending is raised."),
    ("POL_CUT", "Guardrail cut", 0.10, "pct", "of spending", 0.0, 0.5, ""),
    ("POL_RAISE", "Guardrail raise", 0.10, "pct", "of spending", 0.0, 0.5, ""),
    ("POL_FINAL", "No cuts in the last N years", 15, "int", "years", 0, 40,
     "Late in a plan a high withdrawal rate is expected, not a warning sign."),
    ("POL_SKIP", "Skip inflation rise after a loss", "Yes", "list:YESNO", "", None, None,
     "The cheapest form of flexibility: hold spending flat in nominal terms for a year."),
    ("header", "Goals", None, None, None, None, None, None),
    ("POL_LEGACY", "Legacy target", 0, "money", "real, at the end", 0, 1e12,
     "Terminal wealth you want left. Success is redefined against it."),
    ("POL_CONF", "Confidence level", 0.85, "pct", "", 0.5, 0.99,
     "The success probability the solvers aim at. 100% is not a goal, it is a "
     "guarantee of underspending."),
    ("POL_DISC", "Funded-ratio discount rate", 0.03, "pct", "real per year", -0.02, 0.10, ""),
    ("POL_SWEEP", "Surplus sweeps into account #", 1, "int", "row of In-Accounts", 1,
     N_LEDGER, "Where unspent income goes."),
    ("POL_CASH_YRS", "Cash buffer target", 0.0, "num", "years of spending", 0, 10,
     "Spend from cash after a bad year instead of selling into the fall."),
]

MARKETS = [
    ("header", "Return model", None, None, None, None, None, None),
    ("MKT_MODE", "Return mode", "fixed", "list:RETMODE", "", None, None,
     "The sheet always projects with 'fixed'. mc, historical and path drive the "
     "simulation engine on the Dashboard."),
    ("MKT_DIST", "Return distribution", "lognormal", "list:DIST", "", None, None,
     "lognormal cannot produce a return below -100%. t adds fat tails."),
    ("MKT_NU", "Student-t degrees of freedom", 5, "num", "", 2.1, 50,
     "Lower = fatter tails. Below 2 the variance is undefined, so 2.1 is the floor."),
    ("MKT_SEED", "Random seed", 20260916, "int", "", 1, 2**31 - 2,
     "Same seed, same inputs, same answer - every time, on any machine."),
    ("MKT_TRIALS", "Simulation trials", 2000, "int", "", 100, 50000,
     "2,000 gives a success probability accurate to about +/-2%. 10,000 to about +/-1%."),
    ("MKT_ANTI", "Antithetic variates", "No", "list:YESNO", "", None, None,
     "Pairs each trial with its mirror image to cut sampling noise."),
    ("header", "Inflation", None, None, None, None, None, None),
    ("INF_MODE", "Inflation mode", "fixed", "list:INFLMODE", "", None, None, ""),
    ("INF_MEAN", "Inflation, long run", 0.025, "pct", "per year", -0.02, 0.20, ""),
    ("INF_SD", "Inflation volatility", 0.012, "pct", "per year", 0.0, 0.10,
     "Only used in stochastic mode."),
    ("INF_PHI", "Inflation persistence", 0.55, "num", "AR(1)", 0.0, 0.98,
     "How much of last year's surprise carries into this year."),
    ("INF_CORR", "Inflation / equity correlation", -0.20, "num", "", -0.99, 0.99,
     "Usually negative: inflation shocks hurt both bonds and equities."),
    ("header", "Fees - the one return you can control", None, None, None, None, None, None),
    ("FEE_PLATFORM", "Platform / custody fee", 0.0025, "pct", "per year", 0.0, 0.05, ""),
    ("FEE_ADVISER", "Adviser fee", 0.0, "pct", "per year", 0.0, 0.05,
     "1% a year for 30 years is roughly a quarter of the final portfolio."),
    ("header", "Crash process", None, None, None, None, None, None),
    ("CR_ON", "Model random crashes", "Yes", "list:YESNO", "", None, None, ""),
    ("CR_PROB", "Probability a crash starts", 0.04, "pct", "per year", 0.0, 0.5,
     "4% a year is roughly one crash per 25 years."),
    ("CR_MIN", "Crash depth: minimum", 0.20, "pct", "fall", 0.0, 0.95, ""),
    ("CR_MODE", "Crash depth: most likely", 0.35, "pct", "fall", 0.0, 0.95, ""),
    ("CR_MAX", "Crash depth: maximum", 0.60, "pct", "fall", 0.0, 0.99, ""),
    ("CR_DUR", "Years the fall is spread over", 2, "int", "years", 1, 5, ""),
    ("CR_REC", "Fraction recovered afterwards", 0.45, "pct", "of the fall", 0.0, 1.0, ""),
    ("CR_RECY", "Years the recovery takes", 3, "int", "years", 1, 10, ""),
    ("header", "Regimes", None, None, None, None, None, None),
    ("REG_START", "Starting regime", "stationary", "list:STARTREG", "", None, None,
     "stationary starts each trial from the long-run mix."),
    ("MKT_CALIB", "Calibrate to stated returns", "Yes", "list:YESNO", "", None, None,
     "Keeps the long-run average equal to the expected returns you typed, so adding "
     "a bear regime does not silently lower every assumption."),
]

TAXCFG = [
    ("header", "Tax system", None, None, None, None, None, None),
    ("TX_INDEX", "Index tax bands to inflation", "Yes", "list:YESNO", "", None, None,
     "No = frozen bands, which produces fiscal drag: a real tax rise every year."),
    ("TX_ALLOW", "Personal allowance", 12570, "money", "per person", 0, 1e9,
     "Income taxed at zero. Set to 0 if your system has none."),
    ("TX_TAPER_ST", "Allowance taper starts at", 100000, "money", "income", 0, 1e12, ""),
    ("TX_TAPER_RT", "Allowance lost per unit", 0.5, "num", "", 0.0, 1.0, ""),
    ("TX_SUR_RATE", "Surtax / social contribution", 0.0, "pct", "of income", 0.0, 0.6, ""),
    ("TX_SUR_THR", "Surtax threshold", 1e12, "money", "income", 0, 1e12, ""),
    ("TX_CG_INCL", "Capital gains inclusion rate", 1.00, "pct", "of the gain", 0.0, 1.0,
     "The share of a realised gain that enters taxable income. 1 taxes gains at "
     "ordinary rates, 0.5 is a half-inclusion system, 0 exempts them. For a flat "
     "separate gains rate, give the account a wrapper with a fixed taxable fraction."),
    ("TX_FILING", "Filing unit", "individual", "list:FILING", "", None, None, ""),
    ("TX_ESTATE", "Estate tax rate on legacy", 0.0, "pct", "", 0.0, 0.8, ""),
    ("TX_ESTATE_AL", "Estate tax allowance", 0, "money", "", 0, 1e12, ""),
]
