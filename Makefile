# RetPlan build and verification

PY      ?= python3
OUT     ?= RetPlan.ods
TRIALS  ?= 5000
PORT    ?= 5007

.PHONY: all build install trust untrust test verify simulate clean check setup web

all: check

## run the web application on port 5007
web:
	.venv/bin/python run_retplan_web.py --port $(PORT)

## build the workbook from source
build:
	$(PY) build/build_ods.py -o $(OUT)

## install the macro module and engine into the LibreOffice profile
install:
	$(PY) tools/install_macros.py

## let this checkout's documents run macros (this folder and everything under it)
trust:
	$(PY) tools/trust_folder.py

## undo the above
untrust:
	$(PY) tools/trust_folder.py --remove

## one-command setup after cloning anywhere: macros installed and folder trusted
setup: install trust

## unit, engine and statistical tests (no LibreOffice needed)
test:
	$(PY) tests/run_tests.py

## prove the workbook's formulas and the Python engine agree exactly
verify:
	$(PY) tools/crosscheck.py $(OUT)
	$(PY) tools/inspect_ods.py $(OUT) | head -5

## run the Monte Carlo and write the results into the workbook
simulate:
	$(PY) tools/simulate.py $(OUT) --trials $(TRIALS) --full

## the full gate: tests, build, cross-check, simulate
check: test build verify simulate

clean:
	rm -f $(OUT)
	find . -name __pycache__ -type d -exec rm -rf {} +
