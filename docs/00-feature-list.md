# RetPlan — Feature Catalogue

Scannable inventory of what the web application does today. Each feature has an ID
and the module or route that implements it. Normative detail lives in
[01-requirements.md](01-requirements.md); the maths in
[04-math-and-simulation.md](04-math-and-simulation.md).

---

## 1. The plan model — `F-PLAN-*`

A plan is one `retplan.plan.Plan`, stored as JSON in the `plans` table.

| ID | Feature | Where |
|---|---|---|
| F-PLAN-1 | One to four people (the wizard asks for up to two), each with current age, retirement age, planning age and an include flag | `Person` |
| F-PLAN-2 | Horizon of up to 80 annual periods; the plan always starts in the current calendar year | `Plan.horizon`, `web/viewmodel.plan_start` |
| F-PLAN-3 | Unlimited income rows: owner, category (employment, self-employment, rental, DB pension, state pension, annuity, other taxable, tax-free, one-off), amount, real or nominal basis, growth, start/end age, taxable fraction, survivor fraction, probability | `IncomeRow` |
| F-PLAN-4 | Unlimited spending rows: essential or discretionary, real or nominal, real growth above CPI, age-curve ("smile") flag, start/end age, recurrence every *n* years, probability | `ExpenseRow`, `SmileCurve` |
| F-PLAN-5 | Loans: amortising, interest-only or bullet; rate, term, extra payment, start year | `Loan` |
| F-PLAN-6 | User-defined tax wrappers: taxable fraction of withdrawals, capital-gains realisation, contribution cap (none / absolute / % of earnings), catch-up, early-withdrawal penalty, minimum-distribution age and divisor table, lock-in age, liquidity | `Wrapper` |
| F-PLAN-7 | Accounts ("ledgers"): wrapper, owner, balance, cost basis, asset mix, linear glide path between two ages, withdrawal and contribution priority, fixed or %-of-earnings contribution, employer match and match cap, annual or no rebalancing | `Ledger` |
| F-PLAN-8 | Market assumptions: asset classes (return, volatility, income yield, fund cost, crash beta), correlation matrix, regimes with transition matrix, crash process, inflation model, return mode (fixed, path, Monte Carlo, historical bootstrap), distribution (lognormal, normal, Student-t), fixed-return basis (typical or average), calibration, antithetic variates | `retplan/markets.py` |
| F-PLAN-9 | Tax: one progressive band table with allowance, taper and cap; a surtax above a threshold; capital-gains inclusion rate; indexed or frozen bands | `retplan/tax.py` |
| F-PLAN-10 | Withdrawal policy: fixed real, fixed nominal, % of portfolio, VPW, remaining-years table, guardrails; legacy target; sweep account for surplus; confidence target; discount rate | `Policy` |
| F-PLAN-11 | Platform and adviser fees on top of fund costs; a seed | `Plan` |
| F-PLAN-13 | Conversions between two accounts: a fixed real amount a year, or just enough to fill taxable income to a target, between two ages; taxed as a withdrawal from the source wrapper | `Conversion` |
| F-PLAN-12 | A worked sample household used for new workspaces and "reset" | `retplan/samples.py` |

## 2. Plan editor — `F-EDIT-*`

| ID | Feature | Where |
|---|---|---|
| F-EDIT-1 | Ten sections: Household, Income, Spending, Debt, Tax wrappers, Accounts, Markets, Tax, Policy, Conversions | `/plan/{section}` |
| F-EDIT-2 | Rows added and removed in place; rarely changed columns behind *Show advanced columns* | `routes/plan_routes.py` |
| F-EDIT-3 | A section rail with a one-line summary of what each section holds | `plan_routes.completeness` |
| F-EDIT-4 | Contextual help link from every section to its help topic | `web/help_catalog.CONTEXT_HELP` |
| F-EDIT-5 | Export the active plan as JSON; import a JSON plan (replace or as a new scenario); reset to the sample; clear to a blank plan | `routes/export_routes.py` |

## 3. Quick-start wizard — `F-WIZ-*`

| ID | Feature | Where |
|---|---|---|
| F-WIZ-1 | Six steps — you, income, savings, spending, assumptions, review — kept as a draft in the session | `/start`, `web/wizard.py` |
| F-WIZ-2 | Optional partner, salaries, pensions, other income, four balances (taxable, tax-deferred, tax-free, cash), saving % and employer %, spending and retirement spending %, mortgage | `wizard.DEFAULTS` |
| F-WIZ-3 | Risk choice (conservative / balanced / growth) and tax choice (example bands / flat / none) | `wizard.RISK`, `wizard.TAX` |
| F-WIZ-4 | Everything not asked is borrowed from the sample household; the result replaces the active plan or becomes a new scenario | `wizard.build_plan` |

## 4. Scenarios — `F-SCN-*`

| ID | Feature | Where |
|---|---|---|
| F-SCN-1 | Several named plans per workspace, exactly one active; create, duplicate, rename, activate, delete | `/scenarios` |
| F-SCN-2 | Side-by-side comparison of every scenario, simulated with one trial count (1,500) and one seed so differences are the plans' | `/compare`, `/api/compare/run` |

## 5. Dashboard and simulation — `F-SIM-*`

| ID | Feature | Where |
|---|---|---|
| F-SIM-1 | Fixed-return projection recomputed on every view, no run needed: net worth, balances by wrapper, money in/out, funded ratio, depletion age | `viewmodel.base_view` |
| F-SIM-2 | Monte Carlo of 500–25,000 trials from the dashboard (API accepts 100–50,000), run through a JSON API with progress | `/api/simulate` |
| F-SIM-3 | Verdict hero: success probability with its standard error and 95% interval, and the trial count needed for ±1% | `metrics.kpis` |
| F-SIM-4 | KPI tiles: median and P5 terminal wealth, failure rate, depletion ages, worst drawdown, lifetime tax | `metrics.kpis` |
| F-SIM-5 | Charts: percentile fan, sample of 20 paths, terminal-wealth histogram, cumulative chance of depletion by age | `web/charts.py` |
| F-SIM-6 | "What you are actually assuming": effective mean and volatility per asset after regimes and crashes, realised regime mix against the stationary distribution, expected regime durations, correlation shrinkage applied | `MarketModel.effective_moments` |
| F-SIM-7 | Results cached in memory per plan and dropped when the plan changes | `web/store.PlanStore` |

## 6. Solvers — `F-SOL-*`

| ID | Feature | Where |
|---|---|---|
| F-SOL-1 | Maximum sustainable first-year spending at the confidence target | `solvers.max_sustainable_spend` |
| F-SOL-2 | Earliest retirement age at the confidence target | `solvers.earliest_retirement_age` |
| F-SOL-3 | Extra yearly saving into the sweep account needed to reach the target | `solvers.required_extra_saving` |
| F-SOL-4 | Success probability against spending level (17 points, 50%–150%) | `solvers.success_curve` |
| F-SOL-5 | Tornado of eight drivers ranked by their effect on success | `solvers.tornado` |
| F-SOL-6 | All of the above in one "full analysis" run | `/api/analysis` |

## 6a. Deciding — `F-DEC-*`

| ID | Feature | Where |
|---|---|---|
| F-DEC-1 | What-if sliders on the dashboard: retirement age, spending, extra saving until retiring, share of shares, fees, public-pension start; 800 trials on one seed per move, with a "within noise" flag | `web/levers.py`, `/api/whatif` |
| F-DEC-2 | Keep any what-if combination as a new scenario | `/api/whatif/save` |
| F-DEC-3 | Your biggest levers: each common change tried alone with 1,500 trials and ranked by its effect on the odds; a click loads it into the sliders | `/api/levers` |
| F-DEC-4 | Public-pension claiming-age explorer: every age with user-set early and late adjustment rates, on the whole plan, with break-even ages | `/tools/claiming` |
| F-DEC-5 | Conversion explorer: fixed amounts or fill-to levels between two accounts and two ages, compared on after-tax final wealth; "try it" saves a scenario | `/tools/conversions` |
| F-DEC-6 | Life timeline: people, retirements, income streams, time-limited costs, loans, conversions by age | `charts.life_timeline` |
| F-DEC-7 | Spending check: success at spending from 30% to 160% of today's, guardrails around the target, a raise / hold / trim verdict with the amount; savings can be restated after a market move | `levers.spending_check`, `/tools/spending` |
| F-DEC-8 | Draw order: every order of the plan's wrappers screened at fixed returns, the best few simulated, compared on success, lifetime tax and after-tax wealth; applied to the plan or a scenario | `levers.draw_orders`, `/tools/draw-order` |
| F-DEC-9 | Health and care: bridge health cover, later-life health costs above inflation, and long-term care as a stochastic risk (happens per future with its probability, random start age); tested before it is added | `retplan.plan.CareRisk`, `Projection._care`, `/tools/health` |
| F-DEC-10 | Net worth history: dated snapshots of accounts, portfolios, other assets and debts; each portfolio's value recorded after every price run and kept; a snapshot can update the plan's balances | `portfolio/networth.py`, `/networth` |

## 7. Reports and audit — `F-RPT-*`

| ID | Feature | Where |
|---|---|---|
| F-RPT-1 | Year-by-year cash flow: income, forced distributions, spending, tax, withdrawals, contributions, fees, shortfall | `/reports/cashflow` |
| F-RPT-2 | Year-by-year balance sheet: portfolio by wrapper, debt, net worth | `/reports/balance` |
| F-RPT-3 | Year-by-year tax: taxable income and tax | `/reports/tax` |
| F-RPT-4 | Audit: balance roll-forward reconciliation plus input sanity checks, each PASS / FAIL / REVIEW | `/audit`, `viewmodel.audit_checks` |
| F-RPT-5 | Method page describing the model | `/method` |
| F-RPT-6 | One-page plan report to print or save as PDF | `/report/plan` |

## 8. Portfolios — `F-PF-*`

| ID | Feature | Where |
|---|---|---|
| F-PF-1 | Any number of portfolios per workspace, each with a base currency; create, edit, duplicate, delete | `/portfolios` |
| F-PF-2 | Holdings by symbol with quantity, total cost basis, account, asset class and notes; the symbol `CASH` is a cash balance priced at 1 | `holdings` table |
| F-PF-3 | Ticker autocomplete from Yahoo search | `/api/tickers` |
| F-PF-4 | Paste or CSV import of holdings, with or without a header row, previewed before saving | `portfolio/importer.py` |
| F-PF-5 | Bulk edit of holdings on one form | `/portfolios/{pid}/holdings/save` |
| F-PF-6 | Valuation in the base currency with day change, gain and gain % where a cost is known | `PortfolioRepo.valuation` |
| F-PF-7 | Currency conversion through Yahoo FX pairs, including minor-unit quotes (GBp, ZAc, ILA, KWF) | `portfolio/fx.py` |
| F-PF-8 | Allocation by asset class and by account | `Valuation.by` |
| F-PF-9 | A year of value: today's holdings valued on each stored day (a back-cast) | `PortfolioRepo.value_history` |
| F-PF-10 | Checks ("X-ray"): unpriced holdings, missing FX, stale prices, single-company concentration, large cash, crypto share, home bias, share/other split, missing cost basis, unclassified holdings | `portfolio/checks.py` |
| F-PF-11 | Target mix by asset class, drift against it, rebalancing trades including new money, and a new-money-only plan that never sells | `checks.rebalance` |
| F-PF-12 | Copy a portfolio's value, cost and mix into an account of the active plan | `/portfolios/{pid}/to-plan` |
| F-PF-13 | Nine asset classes with long-run return and volatility assumptions; a class guessed from Yahoo's instrument type and name, editable per holding | `portfolio/assets.py` |

## 9. Prices — `F-PX-*`

| ID | Feature | Where |
|---|---|---|
| F-PX-1 | Daily closes for every held symbol and every FX pair a portfolio needs, from Yahoo's chart endpoint | `portfolio/prices.PriceCollector` |
| F-PX-2 | A new symbol gets a year of history; a known one gets only the gap since its last close | `prices._range_for` |
| F-PX-3 | Background scheduler: daily at a configured local time, and at start-up when the last run is more than 20 hours old | `PriceScheduler` |
| F-PX-4 | Closes older than the retention window (365 days by default) deleted after every run | `PortfolioRepo.prune` |
| F-PX-5 | Long-run return and volatility from up to 20 years of monthly bars, refreshed every 30 days, stored as three numbers | `yahoo.long_run_stats` |
| F-PX-6 | Refresh on demand per portfolio or for everything; a status page with the schedule, tracked securities and run log | `/prices` |
| F-PX-7 | One collection run from the command line for cron | `tools/fetch_prices.py` |

## 10. Portfolio builder — `F-BLD-*`

| ID | Feature | Where |
|---|---|---|
| F-BLD-1 | Upload a broker or bank export (.xlsx, .xlsm, .csv or text, up to 10 MB); every sheet of an .xlsx is read | `/portfolios/build`, `portfolio/builder.py` |
| F-BLD-2 | Finds the header row below any preamble and maps columns to roles by vocabulary: symbol, identifier (ISIN / CUSIP / SEDOL), name, quantity, price, value, cost (total or per unit), account, class, currency | `builder.find_header` |
| F-BLD-3 | Skips totals, blank lines and headings; turns cash and money-market lines into `CASH`; derives quantity from value ÷ price | `builder.extract` |
| F-BLD-4 | Identifies each security by cleaned symbol, then identifier lookup, then name search with similarity scoring; records a confidence and the alternatives | `builder.resolve` |
| F-BLD-5 | Compares the file's stated value with price × quantity and flags large gaps (share class, pence/pound, wrong match); merges duplicates | `builder._check_value`, `builder.merge` |
| F-BLD-6 | Review screen: every proposed holding editable; confirm into a new portfolio, or merge into / replace an existing one; nothing saved before confirmation | `/portfolios/build/{did}` |
| F-BLD-7 | Drafts kept between upload and confirmation, deleted after a week | `import_drafts` table |

## 11. Securities and administration — `F-SEC-*`

| ID | Feature | Where |
|---|---|---|
| F-SEC-1 | Live lookup of any symbol: a year of prices and statistics straight from Yahoo, nothing stored | `/securities/lookup` |
| F-SEC-2 | Security page: price chart, statistics, holders in this workspace; set the class on this workspace's holdings | `/securities/{symbol}` |
| F-SEC-3 | Administrator: add, amend and delete securities; type in or delete prices; manually priced securities (`source = manual`) for private funds or property, never fetched | `routes/security_routes.py` |
| F-SEC-4 | A security still held in any portfolio cannot be deleted | `PortfolioRepo.holders` |
| F-SEC-5 | One administrator account: sign in, sign out, change password (stored as a salted PBKDF2 hash); a warning while the shipped default password is in force; optional "this computer is administrator" | `web/admin.py`, `/admin/*` |

## 12. Portfolio projection — `F-PRJ-*`

| ID | Feature | Where |
|---|---|---|
| F-PRJ-1 | Monte Carlo over 1–60 years and 200–50,000 trials on a quarterly clock; yearly or quarterly reporting | `portfolio/projection.py` |
| F-PRJ-2 | Three return models: correlated lognormal, fat-tailed Student-t (5 df), block bootstrap of stored daily returns | `projection.METHODS` |
| F-PRJ-3 | Expected return from the class assumption, the security's long-run history, or a blend; volatility blended from one year of daily and up to 20 years of monthly data; per-holding overrides | `projection.estimate` |
| F-PRJ-4 | Contributions and withdrawals by year range, indexed or not, with extra growth; a % withdrawal; a fee; rebalancing annual, quarterly or never; inflation; a goal in today's money | `projection.Settings` |
| F-PRJ-5 | Results: real and nominal percentile table, fan chart with expected path and goal, return and drawdown distributions, CAGR, probabilities of loss, real loss, depletion and reaching the goal, three representative futures (P10, P50, P90), per-asset risk share | `projection._summarise` |
| F-PRJ-6 | Runs saved (last 10 per portfolio), re-rendered from stored numbers, downloadable as CSV | `projections` table |

## 13. Stress tests — `F-STR-*`

| ID | Feature | Where |
|---|---|---|
| F-STR-1 | Five crisis replays on the current mix: 2008 financial crisis, dot-com bust, Covid crash, 2022 rate shock, 1973–74 stagflation | `portfolio/stress.py` |
| F-STR-2 | Each replay reports drawdown, crisis return, trough, and quarters to recover at expected returns | `projection.replay` |
| F-STR-3 | Any replay can open every trial of a projection | `Settings.stress` |

## 14. Help and interface — `F-UI-*`

| ID | Feature | Where |
|---|---|---|
| F-UI-1 | Help centre: 29 topics in five categories, searchable, with siblings and next/previous links | `/help`, `web/help_catalog.py` |
| F-UI-7 | Guides: two tutorials and two catalogues (configuration, HTTP API) in Markdown with a contents rail | `/help/guides`, `web/guides/` |
| F-UI-8 | Case studies: three worked households, figures computed live, each openable as a scenario | `/help/case-studies`, `web/cases.py` |
| F-UI-9 | Landing page with three drawn figures (futures, sequence risk, audit ledger) and an SVG chain; comparison page by product category | `landing.html`, `landing.js`, `/about/compare` |
| F-UI-2 | Site search (`Ctrl-K`) over pages, help topics, scenarios, portfolios and holdings | `/search` |
| F-UI-3 | Four themes (Crimson, Dark, Blue, Green) over one design, remembered per browser | `web/static/css/tokens.css` |
| F-UI-4 | Mega-menu navigation, gradient page heroes, about page | `_nav.html`, `about.html` |
| F-UI-5 | Server-rendered SVG charts with a hover layer and a table view | `web/charts.py` |
| F-UI-6 | Friendly 404 and 500 pages; JSON errors for API callers | `RetPlanWebApp._install_error_handlers` |

## 15. System — `F-SYS-*`

| ID | Feature | Where |
|---|---|---|
| F-SYS-1 | SQLite (default) or PostgreSQL, chosen by one URL | `config/retplan.toml`, `portfolio/db.py` |
| F-SYS-2 | Configuration file with `RETPLAN_*` environment overrides; launcher flags for host, port, reload, log level and data directory | `web/config.py`, `run_retplan_web.py` |
| F-SYS-3 | Workspaces keyed by an opaque id in a signed session cookie; no user accounts | `web/store.session_id` |
| F-SYS-4 | System page: database URL (password masked), row counts, scheduler status, versions | `/system` |
| F-SYS-5 | Health check and OpenAPI docs | `/healthz`, `/api/docs` |
| F-SYS-6 | Copy all data between databases (e.g. SQLite to PostgreSQL) | `tools/copy_db.py` |
