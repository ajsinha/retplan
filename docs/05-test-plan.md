# RetPlan — Test and Verification Plan

## 1. Suites

Two plain-assert scripts, no test framework, both fully offline: no server process,
no network, no Yahoo.

| Suite | Covers | Database |
|---|---|---|
| `tests/run_tests.py` | The engine in `retplan/`: random numbers, tax, debt, golden scenarios, policies, determinism, serialisation, edge cases, solvers, convergence, market statistics | none |
| `tests/test_portfolio.py` | Schema files, repository, classification, FX, price collection and retention, configuration, paste import, portfolio projection, stress replays, rebalancing, plan store and wizard, portfolio builder, securities administration, administrator gate, web pages through the FastAPI test client | SQLite in memory, or any URL given |

Each check prints `ok` or `FAIL` with its name; the script exits non-zero if any
check failed.

## 2. Running

```bash
make test                                   # both suites, SQLite in memory (~5 s)
make test-pg PG=postgresql+psycopg://user:pass@host/empty_db
                                            # the portfolio/web suite on PostgreSQL
.venv/bin/python tests/run_tests.py --slow  # market statistics at 200,000 trials
```

`make test-pg` needs an **empty** PostgreSQL database: the suite builds the schema
from `schema/postgres.sql` and writes to it.

## 3. Engine suite (`tests/run_tests.py`)

| Section | What is checked |
|---|---|
| Random numbers | Uniforms in (0,1) with the right mean and variance; reproducible by seed; streams independent; `Φ⁻¹(0.975)`; symmetry; triangular mean and bounds; Student-t unit variance and fatter tails; Cholesky reproduces the matrix; shrinkage only when needed |
| Tax | Exact tax in each band; marginal rate; gross-up exact for every taxable fraction; homogeneity at several scales; band and rate validation |
| Debt | Level payment equals the annuity formula; first-year interest; cleared on schedule; principal equals balance; interest-only; overpayment shortens the term |
| Golden scenarios | See §4 |
| Policies | Every withdrawal method gives a finite, non-negative path and never spends below the essential floor |
| Determinism | Same seed, same result; different seed, different result; trial 0 unchanged by the trial count |
| Serialisation | A plan survives a JSON round trip and projects identically |
| Edge cases | Zero portfolio, zero spending, one period, a 100% band, all accounts illiquid, huge spending, ν just above 2 |
| Solvers | Bisection finds a known root and reports an unbracketed target; max sustainable spend is bracketed and monotone |
| Convergence | Standard error shrinks as trials grow; success probability stabilises |
| Model fixes | Employer match on top of surplus and following the saving actually made; reconciliation with employer money; funded ratio excludes forced draws; typical vs average fixed-return basis; retirement solver moves only the right earnings; tornado drivers stay in range; sample accounts invested as labelled |
| Conversions | Amount and fill-to conversions move money, tax them by the gross-up, and keep the reconciliation |
| Market statistics | Stationary distribution; regime durations and occupancy; crash frequency and depth; calibration holds the stated mean; bonds gain in a crash; inflation mean; realised volatility and correlation without regimes; lognormal closed form for median terminal wealth. 40,000 trials by default, 200,000 with `--slow` |

## 4. Golden scenarios

Closed-form cases the engine must hit exactly (1e-9 relative unless stated).

| ID | Scenario | Expectation |
|---|---|---|
| G1 | Zero return, no inflation, no tax, flat spend | Depletion at exactly `P₀ / spend`; balance steps down by the spend |
| G2 | Fixed 5% return, annuity-level spending | The portfolio lands on zero at year 30 (< 1e-6) |
| G3 | Progressive bands, fully taxable wrapper | Withdrawal minus tax equals the need; no shortfall while money remains |
| G3b | As G3 with a 10% early-withdrawal penalty | Penalty handled inside the same inversion |
| G6 | Pension income, mortgage, inflation, returns | Reconciliation ties every period; debt cleared at term |
| G7 | Minimum distributions from age 70 | Start at the stated age; equal balance ÷ divisor; unspent draws reinvested |
| G9 | Legacy target | Redefines success; the same plan succeeds without it |

## 5. Portfolio and web suite (`tests/test_portfolio.py`)

Yahoo is replaced by synthetic price histories (geometric Brownian motion with a
fixed seed), so every run is identical.

| Section | What is checked |
|---|---|
| Schema files | `sqlite.sql` and `postgres.sql` declare identical tables, per-table column lists and indexes; an empty database is built from its schema file |
| Schema mismatch | A database missing a declared table is refused, not migrated |
| Repository | Currency upper-cased and symbols normalised; cash cost defaults to its amount; another workspace can neither read, add to nor list a portfolio; settings round-trip as JSON; a holding knows its account; only investment accounts hold positions; another workspace cannot read its accounts; duplicate copies accounts and holdings; delete removes accounts, holdings and projections; only the last ten projections are kept |
| Accounts | A debt's payment is worked out from its rate and term, and it pays itself down month by month; investable assets are investments plus cash accounts; property and debts are kept apart; net worth is assets less debts; a cash account is a cash position in every analysis; removing an account removes its holdings; one account can be valued alone; names give an account's type away; an import finds an account by name or makes one of the guessed type |
| Classification, FX | Class guesses for typical ETFs, a stock, crypto and a money-market fund; pence of GBP; FX pair names and the 1/100 scale |
| Prices and valuation | The collector prices every held symbol plus the FX pairs it discovers; a failing symbol is recorded, not fatal; a first fetch asks for a year, a later one for the gap; nothing past retention is stored and prune deletes it; long-run statistics and dividend yield kept as numbers; pence holdings converted; unpriced holdings count as zero and are listed; weights sum to one; the back-cast ends at today's value; checks flag unpriced holdings and a single company over 25% |
| Importer | Header and header-less paste; tab, comma and semicolon; loose broker headers; bad lines carry a reason |
| Configuration | A relative data directory is resolved from the project root, and the default SQLite file moves with it |
| Projection, closed forms | Cash compounds at its assumption; expected path agrees; real value deflates by inflation; contributions add up at zero return; withdrawals exhaust the portfolio; % withdrawal compounds quarterly; a 1% fee takes 1% a year |
| Projection, statistics | For each model, percentiles are ordered and the mean ending value matches `(1+μ)^T` within 4%; parametric median matches the lognormal closed form within 2%; the three models agree on the median within 5%; annual returns centre on the assumption |
| Projection, structure | Quarterly reporting; goal probability non-decreasing; three representative futures; risk shares sum to one; symmetric unit-diagonal correlation; the blend weight at 20 years; same seed, same answer; an empty portfolio refused with a reason |
| Stress | A 100% equity replay compounds the index path; drawdown is the worst point; a beta above one deepens the fall; a stressed projection opens with the crisis in every trial |
| Rebalancing | Trades sum to the new money and reach the target; new-money-only never sells |
| Plan store and wizard | A legacy JSON plan is imported on first sight; duplicate activates the copy; activate switches back; editing drops cached results; deleting the active plan activates another; the last plan cannot be deleted; every wizard step's defaults validate; retirement before today refused; the wizard's plan has two people and a loan, allocations summing to one, a flat tax as one band, and runs |
| Builder | Header below a preamble; exchange-prefixed and Bloomberg-style tickers; ISIN and name-only lines resolved (through a fake resolver); repeated lines merged; per-share cost made a total, a position-sized total kept; quantity from value ÷ price; money-market line becomes cash; pounds-versus-pence flagged; sheet name becomes the account; unknown security left unticked; subtotals skipped; header-less CSV; a file with no positions says so; .xls refused with advice |
| Securities admin | Typed prices set the latest price, skip dates past retention, and roll back when the latest close is deleted; a manual security is never fetched; a held security cannot be deleted, an unheld one is deleted with its prices; invalid symbols rejected; pasted prices parse dates, thousands separators and tabs |
| Administrator gate | Password hashes verify and differ per salt; a visitor cannot add a security; wrong credentials fail; the default administrator signs in and the default password is warned about on every page; another browser is not administrator; a password change needs the current password and a minimum length, is stored as a hash, removes the warning, and retires the old default; after signing out, delete is refused |
| Web | Every top-level page renders; portfolio pages render; a projection runs from the form and downloads as CSV; another browser cannot open the portfolio (404); the wizard builds a plan and adds a scenario |
| Accounts on the web | Adding an account starts with its type, grouped by kind; a debt asks what is owed, the rate and the years left; a new investment account goes straight to its page; the portfolio page groups accounts by kind with net worth; an upload into an account puts every line there; a multi-account file lists its accounts with guessed types, and each is made with its type or joined by name |
| Linked plans | Linking brings every account into the plan with its wrapper, the partner's account to the partner, debts as loans; the accounts page says it is linked; a change in the portfolio reaches the plan, keeping what the plan added; simulation results survive reading a linked plan and are dropped once the portfolio moves; a removed account leaves the plan; the portfolio lists the plans that use it; unlinking freezes today's figures; the quick start offers the portfolio's accounts and builds a linked plan with the saving on each account and its debts from the portfolio |
| Net worth | Each portfolio's net worth is recorded after a price run and on demand; the net-worth page shows the history |

## 6. Test requirements

- **TR-1 (M).** Both suites MUST pass before a change is committed.
- **TR-2 (M).** `make test` MUST finish in under 30 s and MUST need no network.
- **TR-3 (M).** `make test-pg` MUST pass against an empty PostgreSQL database; the
  portfolio code MUST NOT branch on dialect to do so.
- **TR-4 (M).** Determinism: the same seed MUST give identical results across runs
  and processes, for both the plan engine and the portfolio projection.
- **TR-5 (M).** Reconciliation: the balance roll-forward MUST tie to 1e-6 relative
  in every period of every golden scenario that has flows.
- **TR-6 (M).** Statistical validation of the market engine as in §3, with the
  tolerances coded in `test_market_statistics`.
- **TR-7 (M).** Edge cases in §3 MUST run without error.
- **TR-8 (M).** A new schema column MUST be added to both schema files; the
  schema-files check enforces it.
- **TR-9 (M).** A new page MUST be added to the web test's page list so it is
  rendered at least once.
- **TR-10 (S).** Any behaviour fixed after a defect report SHOULD gain a named check
  (the "model fixes" section is the pattern).

## 7. Manual checklist (per release)

1. Start with an empty data directory: the sample household appears, and the
   dashboard, reports and audit render with the audit passing.
2. Run 2,000 and 25,000 trials; the error bar narrows; a full analysis completes.
3. Build a plan with the wizard only; compare it with the sample on `/compare`.
4. Create a portfolio; add an investment account and fill it by ticker search, by
   paste and by uploading a broker export; add a cash account, a home and a
   mortgage; import a multi-account file and confirm the guessed types; refresh
   prices; check FX conversion for a foreign holding.
5. Set a target mix and read the rebalancing trades; link the active plan to the
   portfolio, change an account's value and see the plan follow; unlink; start a
   plan from the portfolio with the quick start.
6. Run a projection with each return model and a stress opening; download the CSV;
   reopen a saved run.
7. As administrator, add a manual security with typed prices; confirm a held
   security cannot be deleted; change the default password.
8. Switch through all four themes; check charts and their table views in each.
9. Restart the server: every browser keeps its workspace; the price scheduler
   catches up if its last run is more than 20 hours old.
10. Point the configuration at an empty PostgreSQL database, start, and repeat
    steps 1 and 4; move data with `tools/copy_db.py`.
