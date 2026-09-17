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
./scripts/setup.sh                      # venv + dependencies
.venv/bin/python run_retplan_web.py     # the web app on port 5007

make test        # 91 assertions, no LibreOffice needed        (~3 s)
make build       # generate RetPlan.ods through the UNO API    (~80 s)
make verify      # prove the sheet and the engine agree exactly
make simulate    # run the Monte Carlo and write results in
make install     # put the macros in your LibreOffice profile
```

Then open `RetPlan.ods`, work through **Start Here**, and press **Run simulation**
on the Dashboard. The projection itself is live formulas and needs no macros.

### Enabling the buttons

The projection is live formulas and needs nothing. The four Dashboard buttons need
two things:

1. **The Python script provider** — `sudo apt install libreoffice-script-provider-python`
   (already present on most desktop installs).
2. **Permission to run the document's macros.** The workbook binds its buttons to
   scripts, so LibreOffice's macro security applies. At the default **High** level
   with no trusted location, it disables them on open and the buttons do nothing.
   The portable way, from anywhere you have cloned this repo:

   ```bash
   make setup          # installs the macros and trusts this checkout
   # or, separately:
   python3 tools/install_macros.py
   python3 tools/trust_folder.py           # trusts the repo root and everything under it
   python3 tools/trust_folder.py --list    # show current trusted locations
   python3 tools/trust_folder.py --remove  # undo
   ```

   `trust_folder.py` resolves the repo root at run time, so it does the right thing
   wherever the project lives — move or re-clone it and re-run `make setup`.
   LibreOffice matches trusted locations by URL prefix, so one entry covers every
   subfolder. Your macro security **level is left untouched**; only this location is
   added. LibreOffice must be closed when you run it, since a running instance owns
   the profile and rewrites it on exit.

   Prefer the GUI? **Tools ▸ Options ▸ LibreOffice ▸ Security ▸ Macro Security… ▸
   Trusted Sources ▸ Trusted File Locations ▸ Add…**, or set Macro Security to
   **Medium** to be prompted on every open.

Prefer not to touch either setting? Run the simulation from the command line
instead — identical code, identical results:

```bash
python3 tools/simulate.py RetPlan.ods --trials 10000 --full
```

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


## The web application

A FastAPI application over the same engine, so the browser and the workbook can
never disagree about a number.

```bash
./scripts/setup.sh                      # venv + dependencies
.venv/bin/python run_retplan_web.py     # http://127.0.0.1:5007
```

`--host`, `--port`, `--reload` and `--log-level` are all flags; `RETPLAN_PORT`
and `RETPLAN_DATA` work as environment variables.

| | |
|---|---|
| **Dashboard** | verdict, stat tiles, and up to eight charts; run 500–25,000 trials from the page |
| **Plan editor** | nine sections — household, income, spending, debt, wrappers, accounts, markets, tax, policy |
| **Reports** | year-by-year cash flow, balance sheet and tax |
| **Audit** | the same discipline as the workbook's audit sheet, including the roll-forward identity |
| **Import / export** | a plan is portable JSON; download it, edit it, upload it |

Charts are **server-rendered inline SVG** — no charting library, no CDN, nothing to
load. The categorical palette is validated for colour-vision separation against
both the light and dark surfaces, every chart with two or more series carries a
legend, and each one ships a table view so no value is reachable only by hovering.
Themes (light / dark / blue) swap through CSS custom properties, including the
chart palette, without re-rendering.

Your plan is stored server-side as JSON keyed by an opaque session id, so the
cookie never carries your finances.

### Layout

```
web/         the application: app singleton, templating, charts, view model, store
web/static/  vendored Bootstrap, Bootstrap Icons, fonts (no CDN)
routes/      one handler class per area, registered by the app singleton
run_retplan_web.py   launcher (port 5007 by default)
```

## Repository layout

```
retplan/     the engine - rng, tax, markets, engine, metrics, solvers, reader, samples
web/         the FastAPI application - app, templating, charts, view model, store
routes/      one route handler class per area of the web application
build/       the workbook generator (UNO): spec, theme, sheet builders
macros/      in-document Python macros for LibreOffice
tools/       installer, trust helper, simulation runner, cross-check, inspectors
tests/       91 assertions covering units, golden scenarios and statistics
docs/        specification and delivery notes
```

## Licence

MIT. **Not financial advice** — this is an educational model, and its output is
only as good as the assumptions you type into it.
