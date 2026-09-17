# RetPlan build and verification

PY      ?= python3
OUT     ?= RetPlan.ods
TRIALS  ?= 5000

.PHONY: all build install test verify simulate clean check

all: check

## build the workbook from source
build:
	$(PY) build/build_ods.py -o $(OUT)

## install the macro module and engine into the LibreOffice profile
install:
	$(PY) tools/install_macros.py

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
