#!/usr/bin/env sh
set -eu

# Quick Vite launcher for Linux/WSL/macOS.
# Run npm install in frontend/ once before using this script.

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
FRONTEND_DIR="$ROOT/frontend"

if ! command -v npm >/dev/null 2>&1; then
  echo "[FAIL] npm was not found on PATH."
  echo "[HINT] Install Node.js LTS, then run:"
  echo "       cd \"$FRONTEND_DIR\""
  echo "       npm install"
  exit 1
fi

if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo "[FAIL] frontend/node_modules was not found."
  echo "[HINT] Install frontend dependencies first:"
  echo "       cd \"$FRONTEND_DIR\""
  echo "       npm install"
  exit 1
fi

echo
echo "============================================================"
echo " Investment Tracker Frontend"
echo "============================================================"
echo "[INFO] Frontend dir : $FRONTEND_DIR"
echo "[INFO] URL          : http://127.0.0.1:5173"
echo "[INFO] Stop         : Press Ctrl+C"
echo

cd "$FRONTEND_DIR"
exec npm run dev
