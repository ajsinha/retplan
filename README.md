# RetPlan — Portable Retirement Planning Workbook

A single, macro-free spreadsheet model that behaves **identically in Microsoft Excel and
LibreOffice Calc**, and that is **jurisdiction-agnostic**: no hard-coded country, currency,
tax code, pension scheme or account type. Everything that varies by country, employer or
person is data the user edits in tables, not logic baked into formulas.

## Documents

| Doc | Purpose |
|---|---|
| [docs/00-feature-list.md](docs/00-feature-list.md) | Scannable catalogue of every feature, with IDs and release phase |
| [docs/01-requirements.md](docs/01-requirements.md) | Normative, testable requirements (functional + non-functional) |
| [docs/02-platform.md](docs/02-platform.md) | Tiering (LibreOffice-first), macro architecture, allowed/banned formula constructs |
| [docs/03-data-model.md](docs/03-data-model.md) | Sheet inventory, table schemas, units, key relationships, calculation order |
| [docs/04-math-and-simulation.md](docs/04-math-and-simulation.md) | Algorithms: PRNG, distributions, regimes, crashes, tax inversion, policies |
| [docs/05-test-plan.md](docs/05-test-plan.md) | Golden scenarios, cross-implementation equivalence, acceptance criteria |
| [docs/06-delivery-notes.md](docs/06-delivery-notes.md) | What was actually built, what was measured, and every departure from the spec |

## Quick start

```bash
make test        # 91 assertions, no LibreOffice needed        (~3 s)
make build       # generate RetPlan.ods through the UNO API    (~80 s)
make verify      # prove the sheet and the engine agree exactly
make simulate    # run the Monte Carlo and write results in
make install     # put the macros in your LibreOffice profile
```

Then open `RetPlan.ods`, work through **Start Here**, and press **Run simulation**
on the Dashboard. The projection itself is live formulas and needs no macros.

To use the buttons you need LibreOffice's Python script provider
(`sudo apt install libreoffice-script-provider-python`). Without it, run
`python3 tools/simulate.py RetPlan.ods --full` instead — same code, same results.

## What is in the box

- **24 worksheets**: guided input sheets, a fully visible formula engine, simulation
  sheets, a dashboard with ten charts, three reports and an audit sheet.
- **A generic tax engine**: a table of bands you type. A tax-free allowance is a 0%
  first band; a taper is a band with the higher effective rate. Because the schedule
  stays piecewise linear it is *exactly invertible*, so "how much must I withdraw to
  spend X after tax" is solved in one pass — no circular references, no iteration.
- **A market engine with three layers**: a Markov regime (bear / normal / bull), a
  correlated diffusive shock (lognormal, normal or fat-tailed Student-t), and a jump
  process for crashes with a depth distribution, a multi-year drawdown shape and
  per-asset transmission betas — so government bonds can *gain* while equities fall.
- **The same maths twice, and proved equal**: the workbook's formulas and the numpy
  engine agree to 7e-12 relative over 61 years on the full sample household.

## The three design commitments

1. **Portability over cleverness.** No macros, no dynamic arrays, no structured references,
   no Excel Data Tables, no slicers. If a construct is not proven in both engines at the
   declared floor versions, it is not used. See [CR-*](docs/02-platform.md).
2. **Generality over presets.** Tax is a user-editable bracket engine; account types are
   user-defined *tax wrappers* (EET / TEE / TTE / ETT); asset classes, inflation series,
   life expectancy and pension indexation are all input tables. Shipping "presets" are
   sample data files, never formulas.
3. **Auditability over black boxes.** Every displayed number traces to a visible
   intermediate row. A reconciliation sheet proves sources = uses and that every balance
   rolls forward exactly, every period.

## Identifier conventions

- `F-<AREA>-<n>` — feature (catalogue)
- `FR-<AREA>-<n>` — functional requirement
- `NFR-<n>` — non-functional requirement
- `CR-<n>` — compatibility rule
- `DR-<n>` — data model rule
- `TR-<n>` — test requirement

Priority uses MoSCoW: **M**ust / **S**hould / **C**ould / **W**on't (this release).

## Repository layout

```
retplan/     the engine - rng, tax, markets, engine, metrics, solvers, reader
build/       the workbook generator (UNO): spec, theme, sheet builders
macros/      in-document Python macros
tools/       installer, simulation runner, cross-check, inspectors
tests/       91 assertions covering units, golden scenarios and statistics
docs/        specification and delivery notes
```

## Licence

MIT. **Not financial advice** — this is an educational model, and its output is
only as good as the assumptions you type into it.
