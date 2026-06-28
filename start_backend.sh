#!/usr/bin/env sh
set -eu

# Quick FastAPI launcher for Linux/WSL/macOS.
# Optional first argument: port number. Example: ./start_backend.sh 8766

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BACKEND_DIR="$ROOT/backend"
LOCAL_DIR="$ROOT/.local"
PYTHON="$BACKEND_DIR/.venv/bin/python"

if [ ! -x "$PYTHON" ]; then
  echo "[FAIL] Backend Python executable was not found:"
  echo "       $PYTHON"
  echo "[HINT] Create the backend virtual environment and install requirements:"
  echo "       cd \"$BACKEND_DIR\""
  echo "       python3 -m venv .venv"
  echo "       ./.venv/bin/python -m pip install -r requirements.txt"
  exit 1
fi

mkdir -p "$LOCAL_DIR"

: "${TRACKER_BACKEND_HOST:=127.0.0.1}"
: "${TRACKER_BACKEND_PORT:=8000}"
if [ "${1:-}" != "" ]; then
  TRACKER_BACKEND_PORT="$1"
fi

if [ "${INVESTMENT_TRACKER_DATABASE_URL:-}" = "" ]; then
  export INVESTMENT_TRACKER_DATABASE_URL="sqlite:///$LOCAL_DIR/tracker-dev.sqlite3"
fi

export PYTHONPATH="$BACKEND_DIR"

echo
echo "============================================================"
echo " Investment Tracker Backend"
echo "============================================================"
echo "[INFO] Backend dir : $BACKEND_DIR"
echo "[INFO] Python      : $PYTHON"
echo "[INFO] Database    : $INVESTMENT_TRACKER_DATABASE_URL"
echo "[INFO] URL         : http://$TRACKER_BACKEND_HOST:$TRACKER_BACKEND_PORT"
echo "[INFO] Health      : http://$TRACKER_BACKEND_HOST:$TRACKER_BACKEND_PORT/api/health"
echo "[INFO] Stop        : Press Ctrl+C"
echo

cd "$BACKEND_DIR"
exec "$PYTHON" -m uvicorn app.main:app --host "$TRACKER_BACKEND_HOST" --port "$TRACKER_BACKEND_PORT" --reload
