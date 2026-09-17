# RetPlan — Delivery Notes (v1.0.0)

What was actually built, measured rather than asserted, and where the
implementation departs from the specification. The specs describe the target;
this file is the honest reconciliation against it.

## What ships

| Item | Detail |
|---|---|
| `RetPlan.ods` | 24 worksheets, ~510 named ranges, 10 charts, 6 macro buttons |
| `retplan/` | The engine: RNG, tax, markets, projection, metrics, solvers, sheet reader |
| `build/` | The generator that produces the workbook through the UNO API |
| `macros/` | The in-document Python macros |
| `tools/` | Installer, external simulation runner, cross-check, inspectors |
| `tests/` | 91 assertions, all passing, ~3 s |

## Verification actually performed

| Check | Result |
|---|---|
| **TR-4 cross-implementation equality** | Worst relative difference **7.3e-12** across income, spending, tax, withdrawals, contributions, fees, balances, shortfall and net worth, over 61 years, on the full sample household |
| **TR-6 reconciliation** | `max abs` error **0.0** on every period; the Audit sheet reports PASS |
| **TR-10 error-free display** | Whole-workbook scan: **0** error cells |
| **TR-5 determinism** | Identical results from the same seed; trial 0 unchanged by trial count |
| **TR-7 statistics** | Regime occupancy, crash frequency and depth, calibration, volatility, correlation and the lognormal closed form all within tolerance |
| **NFR-2 performance** | 10,000 trials × 61 years × 6 accounts in **4.1 s**; full analysis with solvers in **15 s** |
| **Gross-up exactness** | Net delivered equals the need to ~1e-15 relative, including penalties and partial taxable fractions |

## Deliberate departures from the spec

1. **Tier B (`.xlsx`) is not built.** The workbook targets LibreOffice, as agreed
   mid-build. The formula core avoids banned constructs, so a portable export
   remains feasible, but it is not produced or tested and is therefore not claimed.
2. **Annual periods only.** `FR-TL-1`'s monthly option is not implemented.
3. **Household-level tax.** Income is taxed as one unit. Jurisdictions that tax
   individuals separately are overstated for couples with uneven incomes.
4. **Allowances and tapers are entered as bands**, not as separate mechanisms.
   This is what makes the schedule exactly invertible; it is a modelling gain, but
   it means the `allowance`/`taper` fields on `Schedule` are unused by the
   shipped data.
5. **Capital gains** are taxed as `gain fraction × inclusion rate` under the
   ordinary bands. There is no separate gains schedule or annual gains exemption.
6. **The sheet assumes annual rebalancing**; the `none` option is honoured by the
   Python engine but not by the formula engine.
7. **Built sizes are smaller than the spec's reserved sizes**: 100 income rows,
   100 expense rows, 10 loans, 6 accounts, 6 wrappers, 6 asset classes, 60-year
   horizon. All are build parameters in `build/spec.py`; raising them and
   rebuilding is the only change needed.
8. **Scenarios store scalar assumptions only**, not the tables.
9. **Long-term care, annuity purchase, equity release, wrapper conversions and
   bracket-filling optimisation** are specified but not implemented. LTC can be
   modelled today as an expense row with a probability, which is how the sample
   data does it.

## The buttons: requirements and verification

The buttons are now **verified end-to-end** through LibreOffice's own Python
script provider (`tools/run_macro.py RetPlan.ods run_quick` resolves the same
`vnd.sun.star.script:` URL a button fires and completes a 500-trial run).

Two things must be true for them to work:

1. `libreoffice-script-provider-python` is installed.
2. The document is allowed to run macros. Because the workbook binds button
   events to scripts, LibreOffice's macro security applies even though the
   scripts live in the user profile rather than inside the file. At the default
   **High** level with no trusted location, macros are disabled on open and the
   buttons silently do nothing. `make setup` (or `tools/trust_folder.py`) adds the
   checkout to LibreOffice's trusted file locations through its own configuration
   API. Trust is matched by URL prefix, so one entry covers every subfolder, and
   the macro security *level* is left alone — only a location is added. The tool
   resolves the repo root at run time, so it stays correct wherever the project is
   cloned, and `--remove` reverses it.

   Two operational notes: LibreOffice must be closed when the tool runs, because a
   running instance owns the profile and rewrites it on exit; and `SecureURL` is a
   `[]string` property that configmgr rejects unless it is passed as an explicitly
   typed `uno.Any`.

`tools/simulate.py` remains the no-configuration path: identical code, identical
results, needs only `python3-uno`.

### Two macro defects found by that verification

Both were masked while the script provider was absent, and both would have made
the buttons appear "disabled" even once macros were allowed:

- **`__file__` is not defined** in a provider-loaded module. The module set its
  import path from `__file__`, so it raised `NameError` at import and never
  loaded. It now asks LibreOffice for the user profile path instead.
- **`XSCRIPTCONTEXT.getDocument()` returns `None`** for a document with no frame
  (hidden or headless). Document resolution now falls back to the desktop's
  current component, then to the first open spreadsheet, and raises a clear
  error instead of failing silently.

## Known rough edges

- `tools/simulate.py` must be given the workbook path; it saves in place.
- The tornado and spending sweep only populate after **Full analysis**.
- Very large trial counts (>20,000) with the full solver pass take a few minutes.
- Chart colours are applied per series; LibreOffice occasionally re-orders the
  legend on reload.
