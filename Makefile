# RetPlan

PY      ?= .venv/bin/python
PORT    ?= 5007

.PHONY: all setup web test test-pg prices clean

all: test

## create the virtual environment and install the dependencies
setup:
	./scripts/setup.sh

## run the web application (http://127.0.0.1:$(PORT))
web:
	$(PY) run_retplan_web.py --port $(PORT)

## engine, database, portfolio and web tests (offline, SQLite in memory)
test:
	$(PY) tests/run_tests.py
	$(PY) tests/test_portfolio.py

## the portfolio and web tests against PostgreSQL: make test-pg PG=postgresql+psycopg://.../empty_db
test-pg:
	$(PY) tests/test_portfolio.py --database "$(PG)"

## collect today's prices once (the web app also does this on its own schedule)
prices:
	$(PY) tools/fetch_prices.py -v

clean:
	find . -name __pycache__ -type d -not -path "./.venv/*" -exec rm -rf {} +
