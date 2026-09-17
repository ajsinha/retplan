# RetPlan — Test and Verification Plan

## 1. Levels

| Level | What | How |
|---|---|---|
| L1 Unit | Tax engine, gross-up inversion, PRNG, distributions, Cholesky, amortisation, policies | `pytest` on `retplan/`, no LibreOffice |
| L2 Engine | Deterministic projection vs hand-computed golden cases | `pytest`, closed-form comparisons |
| L3 Document | Generated `.ods` recalculates to the same numbers as the Python engine | headless LO + UNO reader |
| L4 Statistical | Simulation distributions match theory | large-sample tolerance tests |
| L5 Portability | Tier B `.xlsx` matches Tier A deterministic output | convert + recalc + compare |
| L6 Usability | Validation, checklist, protection, accessibility | scripted + manual checklist |

## 2. Golden scenarios

| ID | Scenario | Purpose |
|---|---|---|
| G1 | Zero-return, zero-inflation, no tax, single person, flat spend | Arithmetic identity: depletion year is exactly `P₀ / spend` |
| G2 | Fixed 5% return, 0% inflation, no tax, 4% initial withdrawal | Compare against closed-form annuity formula |
| G3 | Single flat-rate tax, one wrapper, fixed return | Gross-up correctness: net spending exactly met every year |
| G4 | Progressive tax, three wrappers, ordered sourcing | Sourcing and penalty logic; marginal rate transitions |
| G5 | Two persons, staggered retirement, DB pension with survivor % | Survivor transition and continuation |
| G6 | Mortgage payoff mid-plan with extra payments | Amortisation identity, payoff detection |
| G7 | MRD forcing above spending need | Forced distributions, reinvestment of excess |
| G8 | Guardrails with a crash in year 1 of retirement | Policy rules fire in the right order, floor respected |
| G9 | Legacy target > 0 | Success redefinition |
| G10 | Full-feature kitchen sink | Reconciliation and self-test under everything at once |

Each golden scenario ships as a JSON input file under `tests/golden/` and has expected
values checked into the repository.

## 3. Requirements

- **TR-1 (M).** Every **M** requirement maps to at least one automated test or a named
  manual check; the mapping is maintained in `tests/traceability.md`.
- **TR-2 (M).** L1+L2 MUST run in under 30 s and MUST be green before any build.
- **TR-3 (M).** The build MUST fail if any generated formula contains a banned construct
  (CR-18).
- **TR-4 (M).** **Cross-implementation equality**: for all golden scenarios, the values the
  document computes MUST equal the Python engine's to `1e-9` relative. Verified by opening
  the built `.ods` headless, forcing `calculateAll()`, and reading the engine block.
- **TR-5 (M).** **Determinism**: the same seed MUST produce identical simulation output
  across two runs and across process restarts (`1e-12`).
- **TR-6 (M).** **Reconciliation**: every golden scenario MUST report PASS on the `Audit`
  sheet, with zero identity violations over all periods and wrappers.
- **TR-7 (M).** **Statistical validation** of the market engine, at 200k trials:
  - sample mean and volatility of one-period returns within 1% relative of the target;
  - regime occupancy within 1% of the stationary distribution;
  - crash frequency within 3 standard errors of `λ`;
  - depth distribution mean within 1% of the triangular mean `(min+mode+max)/3`;
  - realised correlation matrix within 0.01 of the target in every entry;
  - Student-t kurtosis in the right direction and variance still matching σ.
- **TR-8 (M).** **Analytic cross-check**: with lognormal returns, no flows and no fees,
  the simulated median terminal wealth MUST match `P₀·exp(μ_log·T)` within Monte Carlo error.
- **TR-9 (M).** **Edge cases** MUST not error: zero portfolio, zero income, 100% tax rate,
  horizon of 1 period, retirement date in the past, all accounts illiquid, correlation matrix
  of all 0.99, ν = 2.01, crash probability 0 and 1.
- **TR-10 (M).** **Error-free display**: a scan of every cell in the built document MUST find
  no error values in any golden scenario.
- **TR-11 (S).** **Performance gates**: NFR-1, NFR-2 and NFR-3 are asserted in CI with a 2×
  margin for slower machines.
- **TR-12 (S).** **Portability gate**: the Tier B file converted and recalculated MUST match
  Tier A deterministic output (PR-2).
- **TR-13 (M).** **Macro safety**: a static check MUST confirm the macro module imports no
  networking, subprocess or filesystem-write modules.
- **TR-14 (S).** **Accessibility check**: contrast ratios computed from the built file's
  styles; a failure lists the offending style.

## 4. Manual checklist (per release)

1. Open with macros disabled — the deterministic model is complete and no errors show.
2. Enter a fresh household from scratch following `Start Here` only; the checklist reaches
   100% without consulting the documentation.
3. Every dropdown offers only valid values; every out-of-range entry is rejected or flagged.
4. Switch scenarios; every chart and KPI updates and no stale label remains.
5. Run 10,000 trials; progress is visible, cancel works, results are marked fresh.
6. Change one input after a run; the staleness banner appears.
7. Print each report sheet to PDF; no clipped columns, no orphaned headers.
8. Keyboard-only pass over every input sheet in tab order.
