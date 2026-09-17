#!/usr/bin/env bash
# Create the virtual environment and install RetPlan's dependencies.
#
#   ./scripts/setup.sh          # venv + requirements
#   ./scripts/setup.sh --dev    # also installs the LibreOffice-side macros
set -euo pipefail
cd "$(dirname "$0")/.."

PY=${PYTHON:-python3}
if [ ! -d .venv ]; then
    echo "creating .venv with $PY"
    "$PY" -m venv .venv
fi
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt
echo "dependencies installed"

if [ "${1:-}" = "--dev" ]; then
    "$PY" tools/install_macros.py || echo "macro install skipped (LibreOffice not found)"
    "$PY" tools/trust_folder.py   || echo "trust step skipped (close LibreOffice and re-run)"
fi

cat <<'MSG'

Next:
    .venv/bin/python run_retplan_web.py        # http://127.0.0.1:5007
    .venv/bin/python tests/run_tests.py        # 91 assertions
MSG
