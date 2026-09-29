# HTTP API reference

Everything the pages do goes through the same application, and a few answers are also
available as JSON. Requests belong to the **workspace** of the session cookie, exactly as
in the browser: send the cookie back (`curl -b cookie -c cookie …`) and you are working on
the same plans and portfolios. The interactive OpenAPI view is at `/api/docs`.

## Simulation

### `POST /api/simulate`

Runs the Monte Carlo on the active plan and keeps the result for the dashboard.

```bash
# run 5,000 futures of the active plan
curl -b cookie -c cookie -X POST localhost:5007/api/simulate \
     -H 'content-type: application/json' -d '{"trials": 5000}'
```

Body: `trials` (100 to 50,000; default 2,000). Answer:

| Field | Meaning |
|---|---|
| `success` | Share of futures that never ran short (and met any legacy target) |
| `success_se` | Its standard error; a 95% interval is ± 1.96 × this |
| `terminal_p50`, `terminal_p5` | Median and 5th-percentile final net worth, today's money |
| `failure_rate` | Share of futures with any unmet need |
| `worst_drawdown` | Worst fall in real net worth across all futures |
| `trials`, `seconds` | What ran, and how long it took |

### `POST /api/analysis`

The same, plus the solvers (maximum sustainable spend, earliest retirement age, saving
needed), the spending sweep and the sensitivity tornado. Slower: several seconds.
Adds `max_spend` and `earliest_age` to the answer.

### `GET /api/results` and `POST /api/clear`

The last simulation of the active plan (404 when there is none), and forgetting it.

## Deciding

### `POST /api/whatif`

The active plan's odds with adjustments, on a fixed seed, without saving anything.

```bash
# retire two years later and spend 5% less
curl -b cookie -X POST localhost:5007/api/whatif \
     -H 'content-type: application/json' -d '{"retire": 2, "spend": -0.05}'
```

Body fields, each optional: `retire` (years), `spend` (fraction), `save` (a year, until
retiring), `equity` (fraction of the mix), `fee` (fraction), `claim` (years),
`claim_early` and `claim_late` (rates per year). Answer: `base` and `adjusted`, each with
`success`, `se`, `p50`, `p5`, `depletion_age`, `tax` and `trials`; and `describe`, the
change in words.

### `POST /api/whatif/save`

The same body; saves the adjusted plan as a new scenario and makes it active. Optional
`name`.

### `POST /api/levers`

Each common change tried alone, ranked by its effect on the odds: `base`, `rows` (each
with `label`, `adjust`, `success`, `delta`, `p50`, `delta_p50`, `tax`), `trials` and
`noise` - differences smaller than this are within the simulation's noise.

### `POST /api/compare/run`

Simulates every scenario of the workspace with the same trials and seed.

## Portfolios

### `GET /api/portfolios/{id}`

A portfolio valued at the latest closes: `name`, `currency`, `as_of`, `total` (the
investable assets - investment accounts plus cash accounts), `cost`, `day_change`,
`unpriced`, `net_worth`, `property`, `debts`, `accounts` (id, name, type, kind, owner,
institution, value, as_of, rate, months_left) and `holdings` (symbol, name, quantity,
price, currency, fx, value, weight, account - the account's name - account_id, asset
class, cost basis).

### `GET /api/tickers?q=`

Symbol search on Yahoo, for autocomplete: `results`, each with `symbol`, `name`, `type`
and `exchange`. Answers are cached for ten minutes.

## Plans as files

| Request | What it does |
|---|---|
| `GET /export/plan.json` | Downloads the active plan as JSON |
| `POST /import` (form, `file`) | Replaces the active plan with an uploaded one; with `as_new=1`, adds it as a new scenario |

## Health

`GET /healthz` answers `status` (`ok` or `degraded`), `version`, `database`,
`database_ok` and the price scheduler's state - suitable for a monitor.
