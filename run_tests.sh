#!/usr/bin/env sh
set -eu

# Project test runner for Linux/WSL/macOS.

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BACKEND_DIR="$ROOT/backend"
TESTS_DIR="$ROOT/tests"
LOCAL_DIR="$ROOT/.local"
PYTHON="$BACKEND_DIR/.venv/bin/python"
ALEMBIC="$BACKEND_DIR/.venv/bin/alembic"
TEST_DB="$LOCAL_DIR/migration-smoke-sh.sqlite3"

echo
echo "============================================================"
echo " Investment Tracker Test Runner"
echo "============================================================"
echo "[INFO] Repository root : $ROOT"
echo "[INFO] Backend dir     : $BACKEND_DIR"
echo "[INFO] Tests dir       : $TESTS_DIR"
echo "[INFO] Python          : $PYTHON"
echo "[INFO] Alembic         : $ALEMBIC"
echo

if [ ! -x "$PYTHON" ]; then
  echo "[FAIL] Python executable was not found."
  echo "[HINT] Create the backend virtual environment and install requirements first:"
  echo "       cd \"$BACKEND_DIR\""
  echo "       python3 -m venv .venv"
  echo "       ./.venv/bin/python -m pip install -r requirements.txt"
  exit 1
fi

if [ ! -x "$ALEMBIC" ]; then
  echo "[FAIL] Alembic executable was not found in the backend virtual environment."
  echo "[HINT] Install backend requirements, then run this script again."
  exit 1
fi

mkdir -p "$LOCAL_DIR"
export PYTHONPATH="$BACKEND_DIR"

section() {
  echo
  echo "============================================================"
  echo " $1"
  echo "============================================================"
}

section "1/4 Unit and repository tests"
echo "[ENV] PYTHONPATH=$PYTHONPATH"
echo "[CMD] \"$PYTHON\" -m unittest discover -s \"$TESTS_DIR\" -v"
"$PYTHON" -m unittest discover -s "$TESTS_DIR" -v
echo "[PASS] Unit and repository tests completed."

section "2/4 Python compile check"
echo "[CMD] \"$PYTHON\" -m compileall \"$BACKEND_DIR/app\" \"$BACKEND_DIR/alembic\" \"$TESTS_DIR\""
"$PYTHON" -m compileall "$BACKEND_DIR/app" "$BACKEND_DIR/alembic" "$TESTS_DIR"
echo "[PASS] Compile check completed."

section "3/4 Alembic fresh database migration smoke test"
if [ -f "$TEST_DB" ]; then
  echo "[INFO] Removing previous smoke database: $TEST_DB"
  rm -f "$TEST_DB"
fi
export INVESTMENT_TRACKER_DATABASE_URL="sqlite:///$TEST_DB"
export TEST_DB_PATH="$TEST_DB"
echo "[ENV] INVESTMENT_TRACKER_DATABASE_URL=$INVESTMENT_TRACKER_DATABASE_URL"
echo "[CMD] \"$ALEMBIC\" -c \"$BACKEND_DIR/alembic.ini\" upgrade head"
"$ALEMBIC" -c "$BACKEND_DIR/alembic.ini" upgrade head
echo "[CMD] Inspect migration revision and expected tables"
"$PYTHON" -c "import os, sqlite3; expected={'accounts','alembic_version','allocation_targets','dca_plans','hidden_securities','import_sessions','market_price_intraday','market_price_history','market_prices','portfolios','security_mappings','transaction_fingerprints','transactions'}; con=sqlite3.connect(os.environ['TEST_DB_PATH']); version=con.execute('select version_num from alembic_version').fetchone(); tables=[row[0] for row in con.execute('select name from sqlite_master where type=? order by name', ('table',))]; missing=sorted(expected-set(tables)); print('alembic_version =', version); print('tables = ' + ', '.join(tables)); print('missing tables = ' + (', '.join(missing) if missing else 'none')); raise SystemExit(1 if missing or not version else 0)"
echo "[PASS] Alembic migration smoke test completed."

section "4/4 Frontend build check"
if command -v npm >/dev/null 2>&1 && [ -d "$ROOT/frontend/node_modules" ]; then
  echo "[CMD] npm --prefix \"$ROOT/frontend\" run build"
  npm --prefix "$ROOT/frontend" run build
  echo "[PASS] Frontend build completed."
else
  echo "[SKIP] npm or frontend/node_modules is unavailable. Run npm install in frontend/ to enable this check."
fi

section "Summary"
echo "[PASS] All available automated checks passed."
echo "[INFO] Manual/API/frontend smoke tests are documented in docs/TESTING.md."
