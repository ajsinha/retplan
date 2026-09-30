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
| F-EDIT-2a | Cards in plain language for income, spending, debt, accounts, care and conversions; adding asks *what kind* first, then a few questions a step at a time with presets, rarely used fields last; duplicate, pause and remove per item; the table stays as *Table view* | `web/plan_items.py`, `/plan/{section}/dialog` |
| F-EDIT-3 | A section rail with a one-line summary of what each section holds | `plan_routes.completeness` |
| F-EDIT-4 | Contextual help link from every section to its help topic | `web/help_catalog.CONTEXT_HELP` |
| F-EDIT-5 | Export the active plan as JSON; import a JSON plan (replace or as a new scenario); reset to the sample; clear to a blank plan | `routes/export_routes.py` |

## 3. Quick-start wizard — `F-WIZ-*`

| ID | Feature | Where |
|---|---|---|
| F-WIZ-1 | Six steps — you, income, savings, spending, assumptions, review — kept as a draft in the session | `/start`, `web/wizard.py` |
| F-WIZ-2 | Optional partner, salaries, pensions, other income, accounts by type (401(k), Roth 401(k), IRA, Roth IRA, HSA, brokerage, savings, pension pot, tax-free savings) with balances and saving, employer match, spending and retirement spending %, mortgage | `wizard.DEFAULTS` |
| F-WIZ-5 | Savings from a portfolio: the portfolio's investment and cash accounts listed, asking only what goes into each a year (workplace plans as % of pay plus match, others as an amount; 529s skipped); no mortgage question, debts come from the portfolio; the plan built is linked to it | `/start`, `web/plan_link.py` |
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
| F-DEC-10 | Net worth history: assets, debts and a breakdown by kind (investments, cash, property, debt) recorded after every price run for every account together (each once) and for each portfolio, one row a day, kept for good; "Record today's net worth" on a portfolio records both; "Every account" first, then each portfolio, with today's split and a history chart | `portfolio/networth.py`, `/networth` |

## 7. Reports and audit — `F-RPT-*`

| ID | Feature | Where |
|---|---|---|
| F-RPT-1 | Year-by-year cash flow: income, forced distributions, spending, tax, withdrawals, contributions, fees, shortfall | `/reports/cashflow` |
| F-RPT-2 | Year-by-year balance sheet: portfolio by wrapper, debt, net worth | `/reports/balance` |
| F-RPT-3 | Year-by-year tax: taxable income and tax | `/reports/tax` |
| F-RPT-4 | Audit: balance roll-forward reconciliation plus input sanity checks, each PASS / FAIL / REVIEW | `/audit`, `viewmodel.audit_checks` |
| F-RPT-5 | Method page describing the model | `/method` |
| F-RPT-6 | One-page plan report to print or save as PDF | `/report/plan` |

## 8. Accounts and portfolios — `F-AC-*`, `F-PF-*`

| ID | Feature | Where |
|---|---|---|
| F-AC-1 | Accounts belong to the workspace, not to a portfolio: the Accounts page lists every account by kind (Investments, Cash, Property, Debts) with net worth over all accounts (each once), investable, property, debts, a net-worth-over-time chart, and on each card the portfolios it is in (or "in no portfolio") | `/accounts`, `routes/account_routes.py` |
| F-AC-2 | Add or update an account in a dialog: type from tiles grouped by kind, then a few questions a step at a time (name, owner, where it is held, currency; value for cash and property; owed, rate, years left and optional payment for debts), and an optional last step choosing the portfolios it is part of | `/accounts/dialog`, `/accounts/save` |
| F-AC-3 | Each account has its own currency (default: the one most accounts use), converted daily into each portfolio's currency | `accounts.currency`, `portfolio/fx.py` |
| F-AC-4 | An account page: holdings for investment accounts; value and its age (flagged after 90 days) for cash and property; owed today, rate, payment and time to pay off for debts; "In portfolios" chips (marked "through another" when included via a sub-portfolio) and checkboxes for the portfolios it is directly in; duplicate with holdings (the copy is in no portfolio); delete (removes it from every portfolio) | `/accounts/{aid}`, `/accounts/{aid}/portfolios`, `/accounts/{aid}/duplicate`, `/accounts/{aid}/delete` |
| F-PF-1 | Any number of portfolios per workspace, all equal, each with a reporting currency; create (name, currency, notes, accounts and portfolios to include), edit, duplicate (a new portfolio of the same selection; accounts are shared, not copied), delete (accounts are never deleted) | `/portfolios` |
| F-PF-1d | A portfolio is a selection of accounts (many-to-many: one account can be in any number of portfolios) and/or other portfolios; one made of others includes all their accounts, recursively, now and later, each counted once; a portfolio cannot contain itself, directly or through another | `portfolio_accounts`, `portfolio_children` tables |
| F-PF-1e | On a portfolio's page: "Choose accounts" (the same checkboxes), "New account" (created and included), cards marked "through <part>" when they come from a sub-portfolio, "Take out of <portfolio>" (the account stays) or "Delete account", a "Made of … / Part of …" line with removable parts | `/portfolios/{pid}/members`, `/portfolios/{pid}/accounts/{aid}/remove`, `/portfolios/{pid}/parts/{cid}/remove` |
| F-PF-1a | Accounts of four kinds: investments (Brokerage, 401(k) / 403(b), Roth 401(k), Traditional IRA, Roth IRA, HSA, 529 plan, Pension pot, Tax-free savings), cash (Checking, Savings, CD / fixed term, Money market), property (Home, Other real estate, Vehicle, Other asset) and debts (Mortgage, Home equity loan, Car loan, Student loan, Credit card, Other loan); each with a name, owner (you, partner, joint), institution, currency and a type that sets its tax treatment | `portfolio/account_types.py`, `accounts` table |
| F-PF-1c | Debts pay down month by month from the date the balance was set, with the level payment from rate and term when no payment is given | `portfolio/account_types.py` |
| F-PF-2 | Holdings by symbol in an investment account, with quantity, total cost basis, asset class and notes; the symbol `CASH` is a cash balance priced at 1 | `holdings` table |
| F-PF-3 | Ticker autocomplete from Yahoo search | `/api/tickers` |
| F-PF-4 | Add one holding, or paste lines (symbol, quantity[, cost basis][, asset class]) into one account, with or without a header row | `portfolio/importer.py`, `/accounts/{aid}/holdings`, `/accounts/{aid}/import` |
| F-PF-5 | Bulk edit of an account's holdings on one form, including moving a holding to another investment account | `/accounts/{aid}/holdings/save`, `/holdings/{hid}/delete` |
| F-PF-6 | Valuation of a portfolio in its currency, over every account it includes: net worth, investable assets (investments plus cash accounts) with day change, property, debts; gain and gain % where a cost is known | `PortfolioRepo.valuation` |
| F-PF-7 | Currency conversion through Yahoo FX pairs, including minor-unit quotes (GBp, ZAc, ILA, KWF) | `portfolio/fx.py` |
| F-PF-8 | Allocation of investable assets by asset class, tax treatment, account and owner | `Valuation.by` |
| F-PF-9 | A year of value: today's investable assets valued on each stored day (a back-cast); net worth over time from the daily records | `PortfolioRepo.value_history` |
| F-PF-10 | Checks ("X-ray"): unpriced holdings, missing FX, stale prices, single-company concentration, large cash, crypto share, home bias, share/other split, missing cost basis, unclassified holdings | `portfolio/checks.py` |
| F-PF-11 | Target mix by asset class, drift against it, rebalancing trades including new money, and a new-money-only plan that never sells | `checks.rebalance` |
| F-PF-12a | Live link: portfolios hold references, so a change to an account (holdings, prices, values, debts) is seen at once by every portfolio including it, directly or through a sub-portfolio, and by every plan linked to such a portfolio | `PortfolioRepo`, `web/plan_link.py` |
| F-PF-12 | Live link from a plan to a portfolio: every time the plan is read, each of the portfolio's investment, cash and property accounts becomes a plan account (value, owner, cost basis, mix, a wrapper from its type) and each debt a loan; accounts leaving or joining the portfolio leave or join the plan; what the plan adds (contributions, match, order, glide path, rebalancing, paused) is kept; simulation results are dropped when the portfolio's accounts change; link, unlink (freezes today's figures), "Start a plan from it" | `web/plan_link.py`, `/plan/link`, `/plan/unlink` |
| F-PF-13 | Nine asset classes with long-run return and volatility assumptions; a class guessed from Yahoo's instrument type and name, editable per holding | `portfolio/assets.py` |

## 8a. Strategy optimiser — `F-STG-*`

| ID | Feature | Where |
|---|---|---|
| F-STG-1 | Chooses together each person's retirement age, each public pension's claiming age, fixed or guardrail spending, the draw order, Roth-style conversions and the share in shares | `web/strategy.Optimiser` |
| F-STG-2 | Four objectives: safest, retire earliest, spend the most, leave the most after tax; a confidence target and a latest working age | `/strategy` |
| F-STG-3 | Staged coordinate search on common random numbers with caching and a time limit; confirming run of the winner and the plan on more futures | `strategy.search_trials`, `final_trials`, `max_seconds` |
| F-STG-4 | Never more years of work than planned unless needed to reach the target; beyond `enough_odds` certainty is not bought with work nor traded for wealth | `Optimiser.score` |
| F-STG-5 | Report: each decision now and recommended with its worth on its own, standing rules, alternatives within the noise, the plan year by year, saved as a scenario | `strategy/index.html` |
| F-STG-6 | Runs in the background with progress; settings in `strategy.*` of `config/retplan.yaml`, read at each search | `strategy.Jobs` |

## 9. Prices — `F-PX-*`

| ID | Feature | Where |
|---|---|---|
| F-PX-1 | Daily bars - open, high, low, close, adjusted close, volume - for every held symbol, every market-data security and every FX pair an account or portfolio needs (collected automatically), from Yahoo's chart endpoint | `portfolio/prices.PriceCollector` |
| F-PX-2 | A new symbol gets its whole window of history (a year, or its own `keep_days`); a known one gets only the gap since its last close; a lengthened window is backfilled | `prices._range_for` |
| F-PX-3 | Background scheduler: daily at a configured local time, and at start-up when the last run is more than 20 hours old | `PriceScheduler` |
| F-PX-4 | Bars older than the retention window (365 days by default, or a security's own `keep_days`) deleted after every run | `PortfolioRepo.prune` |
| F-PX-10 | Trading calendars (US with every NYSE holiday rule and special closure, London with bank holidays, currencies, crypto, other weekdays); each run fetches back to the earliest missing trading day; days Yahoo has no bar for become known gaps (at once if older than ten days, else after three tries); scheduled runs skip symbols already complete for their calendar; older adjusted closes rescaled when a dividend or split restates them | `portfolio/calendar.py`, `PriceCollector._plan`, `price_gaps` table |
| F-PX-8 | Market data: indices, stocks, ETFs, funds, futures, currencies and crypto collected daily whether held or not; added by Yahoo search, a pasted list or ready-made sets (US and world indices, index funds, sector ETFs, rates and bonds, commodities, currencies, crypto); history of 1, 2, 5, 10 or 20 years per symbol; grouped by kind with last close, day change, volume and 52-week range; administrator-only changes, open to all to browse | `/market`, `portfolio/market.py` |
| F-PX-9 | Any security's stored bars downloadable as CSV (date, open, high, low, close, adj_close, volume); the security page shows the latest 60 bars | `/securities/{symbol}.csv` |
| F-PX-5 | Long-run return and volatility from up to 20 years of monthly bars, refreshed every 30 days, stored as three numbers | `yahoo.long_run_stats` |
| F-PX-6 | Refresh on demand per account, per portfolio or for everything; a status page with the schedule, tracked securities and run log | `/prices` |
| F-PX-7 | One collection run from the command line for cron | `tools/fetch_prices.py` |

## 10. Portfolio builder — `F-BLD-*`

| ID | Feature | Where |
|---|---|---|
| F-BLD-1 | Upload a broker or bank export (.xlsx, .xlsm, .csv or text, up to 10 MB); every sheet of an .xlsx is read; either from an account page into that account (every line goes there, optionally replacing its holdings) or as "Import a file of several accounts" (from the nav, the Accounts page or a portfolio's menu) | `/portfolios/build` (`?aid=` or `?pid=`), `portfolio/builder.py` |
| F-BLD-2 | Finds the header row below any preamble and maps columns to roles by vocabulary: symbol, identifier (ISIN / CUSIP / SEDOL), name, quantity, price, value, cost (total or per unit), account, class, currency | `builder.find_header` |
| F-BLD-3 | Skips totals, blank lines and headings; turns cash and money-market lines into `CASH`; derives quantity from value ÷ price | `builder.extract` |
| F-BLD-4 | Identifies each security by cleaned symbol, then identifier lookup, then name search with similarity scoring; records a confidence and the alternatives | `builder.resolve` |
| F-BLD-5 | Compares the file's stated value with price × quantity and flags large gaps (share class, pence/pound, wrong match); merges duplicates | `builder._check_value`, `builder.merge` |
| F-BLD-6 | Review screen: every proposed holding editable; for a multi-account file each account name with a guessed type to confirm, positions without an account going to "Brokerage"; one account per name found, joining an existing account of the same name; the destination is a new portfolio of them, an existing portfolio they are added to, or just the accounts; nothing saved before confirmation | `/portfolios/build/{did}` |
| F-BLD-7 | Drafts kept between upload and confirmation, deleted after a week | `import_drafts` table |

## 11. Securities and administration — `F-SEC-*`

| ID | Feature | Where |
|---|---|---|
| F-SEC-1 | Live lookup of any symbol: a year of prices and statistics straight from Yahoo, nothing stored | `/securities/lookup` |
| F-SEC-2 | Security page: price chart, statistics, holders in this workspace; set the class on this workspace's holdings | `/securities/{symbol}` |
| F-SEC-3 | Administrator: add, amend and delete securities; type in or delete prices; manually priced securities (`source = manual`) for private funds or property, never fetched | `routes/security_routes.py` |
| F-SEC-4 | A security still held in any account cannot be deleted | `PortfolioRepo.holders` |
| F-SEC-5 | One administrator account: sign in, sign out, change password (stored as a salted PBKDF2 hash); a warning while the shipped default password is in force; optional "this computer is administrator" | `web/admin.py`, `/admin/*` |

## 12. Portfolio projection — `F-PRJ-*`

| ID | Feature | Where |
|---|---|---|
| F-PRJ-1 | Monte Carlo of a portfolio's investable assets (the holdings of every investment account it includes plus cash accounts as cash; property and debts not projected) over 1–60 years and 200–50,000 trials on a quarterly clock; yearly or quarterly reporting | `portfolio/projection.py` |
| F-PRJ-2 | Three return models: correlated lognormal, fat-tailed Student-t (5 df), block bootstrap of stored daily returns | `projection.METHODS` |
| F-PRJ-3 | Expected return from the class assumption, the security's long-run history, or a blend; volatility blended from one year of daily and up to 20 years of monthly data; per-holding overrides | `projection.estimate` |
| F-PRJ-4 | Contributions and withdrawals by year range, indexed or not, with extra growth; a % withdrawal; a fee; rebalancing annual, quarterly or never; inflation; a goal in today's money | `projection.Settings` |
| F-PRJ-5 | Results: real and nominal percentile table, fan chart with expected path and goal, return and drawdown distributions, CAGR, probabilities of loss, real loss, depletion and reaching the goal, three representative futures (P10, P50, P90), per-asset risk share | `projection._summarise` |
| F-PRJ-6 | Runs saved (last 10 per portfolio), re-rendered from stored numbers, downloadable as CSV | `projections` table |

## 13. Stress tests — `F-STR-*`

| ID | Feature | Where |
|---|---|---|
| F-STR-1 | Five crisis replays on the current investable mix: 2008 financial crisis, dot-com bust, Covid crash, 2022 rate shock, 1973–74 stagflation | `portfolio/stress.py` |
| F-STR-2 | Each replay reports drawdown, crisis return, trough, and quarters to recover at expected returns | `projection.replay` |
| F-STR-3 | Any replay can open every trial of a projection | `Settings.stress` |

## 14. Help and interface — `F-UI-*`

| ID | Feature | Where |
|---|---|---|
| F-UI-1 | Help centre: 29 topics in five categories, searchable, with siblings and next/previous links | `/help`, `web/help_catalog.py` |
| F-UI-7 | Guides: two tutorials and two catalogues (configuration, HTTP API) in Markdown with a contents rail | `/help/guides`, `web/guides/` |
| F-UI-8 | Case studies: three worked households, figures computed live, each openable as a scenario | `/help/case-studies`, `web/cases.py` |
| F-UI-9 | Landing page with three drawn figures (futures, sequence risk, audit ledger) and an SVG chain; comparison page by product category | `landing.html`, `landing.js`, `/about/compare` |
| F-UI-2 | Site search (`Ctrl-K`) over pages, help topics, scenarios, accounts, portfolios and holdings | `/search` |
| F-UI-3 | Four themes (Crimson, Dark, Blue, Green) over one design, remembered per browser | `web/static/css/tokens.css` |
| F-UI-4 | Mega-menu navigation, gradient page heroes, about page | `_nav.html`, `about.html` |
| F-UI-5 | Server-rendered SVG charts with a hover layer and a table view | `web/charts.py` |
| F-UI-6 | Friendly 404 and 500 pages; JSON errors for API callers | `RetPlanWebApp._install_error_handlers` |

## 15. System — `F-SYS-*`

| ID | Feature | Where |
|---|---|---|
| F-SYS-1 | SQLite (default) or PostgreSQL, chosen by one URL | `config/retplan.yaml`, `portfolio/db.py` |
| F-SYS-2 | Configuration file with `RETPLAN_*` environment overrides; launcher flags for host, port, reload, log level and data directory | `web/config.py`, `run_retplan_web.py` |
| F-SYS-3 | Workspaces keyed by an opaque id in a signed session cookie; no user accounts | `web/store.session_id` |
| F-SYS-4 | System page: database URL (password masked), row counts, scheduler status, versions | `/system` |
| F-SYS-5 | Health check and OpenAPI docs | `/healthz`, `/api/docs` |
| F-SYS-6 | Copy all data between databases (e.g. SQLite to PostgreSQL) | `tools/copy_db.py` |
