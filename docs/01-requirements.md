# RetPlan — Requirements Specification

Normative, testable requirements for the web application as built. Keywords MUST,
SHOULD and MAY follow RFC 2119. Priorities use MoSCoW (**M**ust / **S**hould /
**C**ould). Feature IDs refer to [00-feature-list.md](00-feature-list.md).

---

## 1. Purpose and scope

RetPlan is a self-hosted web application for retirement planning and portfolio
analysis. It answers two kinds of question:

- **Plan questions** — will this household's savings, income and spending last,
  with what probability, and what would change the answer? Answered by the engine
  in `retplan/`.
- **Portfolio questions** — what do I hold, what is it worth, how concentrated is
  it, and what might it do over the next decades or in a crisis? Answered by
  `portfolio/`.

The model is jurisdiction-agnostic: no country, currency, tax code or account type
is built in. Everything that varies by country is data the user edits.

Out of scope: user accounts, multi-tenant hosting, transaction ledgers, tax inside
portfolio projections, and financial advice.

## 2. Users and workspaces

- **FR-WS-1 (M).** Every browser MUST get its own workspace, keyed by an opaque id
  in a signed session cookie. No sign-up is required to plan.
- **FR-WS-2 (M).** A workspace MUST see only its own plans, portfolios, drafts and
  projections; a request for another workspace's portfolio MUST return 404.
- **FR-WS-3 (M).** A new workspace MUST start with the sample household as its
  active plan.
- **FR-WS-4 (M).** The session secret MUST persist across restarts (from
  `RETPLAN_SECRET`, or generated once into the data directory with mode 0600), so a
  restart does not orphan workspaces.
- **FR-WS-5 (M).** Changing the shared securities list MUST require the
  administrator (§11).

## 3. Plan editing (F-PLAN, F-EDIT)

- **FR-ED-1 (M).** The editor MUST expose the ten sections of F-EDIT-1, each saving
  independently.
- **FR-ED-2 (M).** Rows MUST be addable and removable in income, spending, debt,
  wrappers, accounts and conversions; people up to four. Tax bands (up to 12) MAY be added,
  deleted and entered in any order; they are sorted on save and a 0% band from zero
  is inserted when missing.
- **FR-ED-3 (S).** Columns rarely changed SHOULD be hidden until the user asks for
  advanced columns.
- **FR-ED-4 (M).** Saving a plan MUST invalidate that plan's cached simulation
  results.
- **FR-ED-5 (M).** A plan MUST round-trip through JSON export and import without
  loss; unknown keys in an imported file MUST be ignored rather than rejected.
- **FR-ED-6 (M).** Reset MUST restore the sample household; clear MUST leave a
  blank plan.

## 4. Quick-start wizard (F-WIZ)

- **FR-WZ-1 (M).** Six steps MUST build a complete plan from a handful of answers;
  every unasked assumption MUST come from the sample household.
- **FR-WZ-2 (M).** The draft MUST survive moving between steps and MAY be reset.
- **FR-WZ-3 (M).** Finishing MUST either replace the active plan or add a new
  scenario, as the user chooses.

## 5. Scenarios (F-SCN)

- **FR-SC-1 (M).** A workspace MUST hold one or more plans with exactly one active.
  The editor, dashboard and reports MUST show the active plan.
- **FR-SC-2 (M).** Deleting the last remaining plan MUST NOT leave the workspace
  without an active plan.
- **FR-SC-3 (M).** The comparison MUST simulate every scenario with the same trial
  count and seed.

## 6. Projection engine (F-SIM)

- **FR-EN-1 (M).** The engine MUST compute in real (today's money) terms and derive
  nominal values from each trial's own realised price index.
- **FR-EN-2 (M).** The fixed-return projection and the Monte Carlo MUST run the same
  code (a single trial is `n = 1`).
- **FR-EN-3 (M).** Net spending, debt service and tax on income MUST be met by
  withdrawals grossed up exactly for tax and early-withdrawal penalty, in the
  accounts' withdrawal priority, skipping illiquid and locked wrappers.
- **FR-EN-4 (M).** Minimum distributions MUST be taken from the wrapper's MRD age by
  the divisor table (step lookup by whole age), counted as income and, if unspent,
  reinvested.
- **FR-EN-5 (M).** Surplus income MUST fund contributions in contribution priority,
  within wrapper caps and catch-up, only while the household is not fully retired;
  any remainder MUST sweep into the policy's sweep account.
- **FR-EN-6 (M).** Employer match MUST be new money on top of the surplus, paid on
  the percentage-of-pay saving actually made, up to the match cap and inside the
  wrapper cap.
- **FR-EN-7 (M).** Unmet need MUST be recorded as shortfall; balances MUST never go
  negative.
- **FR-EN-8 (M).** Success MUST mean no period with shortfall and real terminal net
  worth at or above the legacy target.
- **FR-EN-9 (M).** Frozen tax bands MUST produce fiscal drag exactly (§10 of the
  maths document), without rebuilding bands per trial.
- **FR-EN-10 (M).** The fixed-return projection MUST use each asset's typical
  (median) growth rate by default, with the arithmetic mean available as an option.

## 7. Dashboard and solvers (F-SIM, F-SOL)

- **FR-DB-1 (M).** The fixed-return KPIs and charts MUST be shown without running a
  simulation.
- **FR-DB-2 (M).** A Monte Carlo run MUST be started through the JSON API, clamped
  to 100–50,000 trials, and its failure MUST return an error message, not a hung
  request.
- **FR-DB-3 (M).** Success probability MUST be shown with its standard error; a
  bare percentage without an error bar is not acceptable.
- **FR-DB-4 (M).** The dashboard MUST report the effective return and volatility
  the market model actually produces after regimes and crashes, beside the inputs.
- **FR-DB-5 (M).** Solvers MUST re-run the whole model rather than approximate it,
  and MUST report when the target could not be bracketed.
- **FR-DB-6 (M).** The earliest-retirement solver MUST move earnings that ended at
  the old retirement age to the new one, in both directions, and MUST NOT extend
  earnings that ended earlier.

## 8. Reports and audit (F-RPT)

- **FR-RP-1 (M).** Cash-flow, balance-sheet and tax reports MUST show every year of
  the fixed-return projection.
- **FR-RP-2 (M).** The audit MUST prove the balance roll-forward
  `close = (open − withdrawals − MRD + contributions − fees) × (1 + r)` to `1e-6`
  relative in every period.
- **FR-RP-3 (M).** The audit MUST check the inputs the engine relies on (ages in
  order, allocations sum to 100%, correlations in range and symmetric, regime rows
  sum to 1, tax bands ascend, rates in [0, 1]) and flag implausible assumptions for
  review.

## 9. Portfolios and prices (F-PF, F-PX)

- **FR-PF-1 (M).** Holdings MUST be valued at the latest close converted to the
  portfolio's base currency; a holding without a price MUST count as zero and be
  reported.
- **FR-PF-2 (M).** A holding's own asset class MUST override the security's guessed
  class; setting a class from a security page MUST change only this workspace's
  holdings.
- **FR-PF-3 (M).** Pasted and uploaded holdings MUST be previewed before anything is
  saved.
- **FR-PF-4 (M).** Rebalancing MUST produce per-class trades that sum to the new
  money, and a new-money-only alternative that never sells.
- **FR-PF-5 (M).** Copying a portfolio into the plan MUST set the chosen account's
  balance, cost basis (holdings without a cost assumed bought at today's value) and
  asset mix.
- **FR-PX-1 (M).** The collector MUST price every held symbol and every FX pair a
  portfolio needs, and MUST report a failure for one symbol without aborting the run.
- **FR-PX-2 (M).** Closes older than `prices.retention_days` MUST be deleted after
  every run. Monthly history MUST NOT be stored; only the three long-run numbers.
- **FR-PX-3 (M).** The scheduler MUST run daily at `prices.run_at` and at start-up
  when the last successful run is older than 20 hours; a failed run MUST NOT stop the
  thread.
- **FR-PX-4 (S).** Requests to Yahoo SHOULD be spaced (0.4 s between symbols).

## 10. Portfolio builder (F-BLD)

- **FR-BL-1 (M).** The builder MUST accept .xlsx/.xlsm and delimited text up to
  10 MB and MUST reject legacy .xls with an instruction to re-save.
- **FR-BL-2 (M).** Every proposed holding MUST carry a confidence and the way it was
  identified; doubtful matches and value mismatches MUST be flagged.
- **FR-BL-3 (M).** Nothing MUST reach a portfolio until the review is confirmed.
- **FR-BL-4 (M).** At most 2,000 positions are read from one file.

## 11. Securities and administration (F-SEC)

- **FR-SE-1 (M).** Any user MAY look up any symbol; nothing is stored by a lookup.
- **FR-SE-2 (M).** Adding, amending or deleting a security, and typing in or deleting
  prices, MUST require an administrator.
- **FR-SE-3 (M).** A security held in any portfolio MUST NOT be deletable.
- **FR-SE-4 (M).** A manually priced security MUST never be fetched from Yahoo.
- **FR-SE-5 (M).** Administrator passwords changed in the app MUST be stored only as
  a salted PBKDF2-SHA256 hash; while the shipped default password is in force, every
  administrator page MUST say so.

## 12. Portfolio projection and stress (F-PRJ, F-STR)

- **FR-PJ-1 (M).** Settings MUST be clamped: 1–60 years, 200–50,000 trials, inflation
  −5% to 25%, fee 0–5%, withdrawal rate 0–50%.
- **FR-PJ-2 (M).** Expected return MUST NOT be taken from one year of sample mean.
- **FR-PJ-3 (M).** The same settings and seed MUST reproduce the same result.
- **FR-PJ-4 (M).** A portfolio with no priced holdings MUST be refused with a reason.
- **FR-PJ-5 (M).** A bootstrap with too few common trading days MUST fall back to the
  lognormal model and say so.
- **FR-PJ-6 (M).** Saved runs MUST re-render from stored numbers alone; the last 10
  per portfolio are kept.
- **FR-ST-1 (M).** A replay MUST follow each holding's class proxy, scaling the excess
  return over cash by the class beta.

## 13. Web rules

- **WR-1 (M).** No CDN. Bootstrap, Bootstrap Icons, fonts and every other front-end
  library MUST be vendored under `web/static/vendor/`.
- **WR-2 (M).** No inline JavaScript: every script is a file under `web/static/js/`
  or `web/static/vendor/`, and templates carry no `on*=` handlers.
- **WR-3 (M).** Colours MUST be defined only in `web/static/css/tokens.css`; each
  theme redefines the same `--rp-*` and `--viz-*` roles.
- **WR-4 (M).** Charts MUST be server-rendered SVG with a table view, so no value is
  reachable only by hovering.
- **WR-5 (M).** Templates MUST name routes through `url_for`, never hard-coded paths.
- **WR-6 (M).** Every route MUST belong to a handler class in `routes/`, registered by
  the application singleton; shared services live on `app.state`, not module globals.
- **WR-7 (M).** Redirect targets taken from a request (`next=`) MUST be same-site
  relative paths.
- **WR-8 (M).** An unhandled error MUST render an honest error page (or JSON for API
  callers) and log the full trace.

## 14. Non-functional requirements

- **NFR-1 (M) Performance — simulation.** 2,000 trials of the sample household MUST
  render the dashboard payload in under 2 s on a desktop machine; 10,000 engine trials
  in under 5 s.
- **NFR-2 (S) Performance — analysis.** A full analysis at 2,000 trials SHOULD finish
  in under 30 s.
- **NFR-3 (M) Determinism.** The same inputs and seed MUST give identical results
  across runs and processes.
- **NFR-4 (M) Numerical hygiene.** No iterative tax solving; divisions guarded;
  balances clamped at zero.
- **NFR-5 (M) Portability of data.** SQLite and PostgreSQL MUST be interchangeable by
  configuration alone; queries MUST use only SQL both accept.
- **NFR-6 (M) Schema integrity.** A database missing a declared table or column MUST
  be refused at start-up with a message naming it; the schema is never altered
  silently.
- **NFR-7 (M) Privacy.** No personal identifier is required. The only outbound
  traffic MUST be price and symbol requests to Yahoo Finance.
- **NFR-8 (M) Offline operation.** Everything except price collection and symbol
  lookup MUST work without a network.
- **NFR-9 (M) Accessibility.** No information by colour alone; the chart palette is
  validated for colour-vision separation on light and dark surfaces.
- **NFR-10 (M) Testability.** Both test suites MUST run offline, without a server
  and without Yahoo (see [05-test-plan.md](05-test-plan.md)).
- **NFR-11 (M) Honesty.** Known limits MUST be stated in the application (help topic
  *What this model does not do* and the about page).
