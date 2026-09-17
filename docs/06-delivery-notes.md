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

## Environment note: the buttons

The in-document buttons need LibreOffice's Python script provider:

```
sudo apt install libreoffice-script-provider-python
```

It is **not** installed on the build machine, so the buttons were not fired
end-to-end here. The same code paths were exercised through
`tools/simulate.py`, which drives the identical functions over the UNO bridge
and needs only `python3-uno`. If the package is absent, use the CLI; nothing is
lost but the convenience.

## Known rough edges

- `tools/simulate.py` must be given the workbook path; it saves in place.
- The tornado and spending sweep only populate after **Full analysis**.
- Very large trial counts (>20,000) with the full solver pass take a few minutes.
- Chart colours are applied per series; LibreOffice occasionally re-orders the
  legend on reload.
