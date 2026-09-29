#!/usr/bin/env bash
# Create the virtual environment and install RetPlan's dependencies.
#
#   ./scripts/setup.sh          # venv + requirements
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

cat <<'MSG'

Next:
    .venv/bin/python run_retplan_web.py        # http://127.0.0.1:5007
    make test                                  # engine, database, portfolio and web tests
MSG
