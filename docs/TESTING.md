# Testing Guide

This document explains the tests and manual checks used by this project. Update it whenever a new test, smoke check, or required verification step is added.

The goal is not only to know which command to run, but also why the check exists and what a healthy result looks like.

## Test Environment

Most commands assume you are at the repository root:

```powershell
cd "X:\My Finance\Tracker"
```

Use the backend virtual environment:

```powershell
.\backend\.venv\Scripts\Activate.ps1
```

For Python imports, the backend package path must be available:

```powershell
$env:PYTHONPATH = "backend"
```

## Automated Unit And Repository Tests

Run:

```powershell
$env:PYTHONPATH = "backend"
.\backend\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Purpose:

- verify Fortuneo-style CSV parsing;
- verify portfolio math and cost-basis behavior;
- verify Enhanced DCA recommendation logic;
- verify SQLAlchemy repository persistence;
- verify portfolio/account isolation;
- verify duplicate-safe CSV imports.
- verify historical market price upsert and range filtering.
- verify DCA settings persistence.
- verify portfolio history and benchmark normalization.
- verify yfinance historical response normalization.
- verify synthetic golden fixtures stay aligned with parser, portfolio summary, portfolio history, and duplicate-preview expectations.

Expected output:

```text
test_import_allows_same_security_with_different_quantity ... ok
test_import_skips_duplicate_transactions ... ok
test_keeps_portfolios_isolated ... ok
test_persists_transactions_and_prices ... ok
test_parse_fortuneo_style_csv ... ok
test_enhanced_dca_increases_on_market_drawdown ... ok
test_build_holdings_reduces_cost_basis_on_sell ... ok
test_summarize_portfolio_prices_holdings ... ok
test_market_price_history_upserts_and_filters_ranges ... ok
test_dca_settings_are_persisted_per_portfolio ... ok
test_build_portfolio_history_with_normalized_benchmarks ... ok
test_enhanced_dca_applies_settings_multiplier_bounds ... ok
test_normalize_yfinance_history ... ok
test_duplicate_preview_fixture_marks_duplicate_rows ... ok
test_golden_fixture_matches_expected_portfolio_history ... ok
test_golden_fixture_matches_expected_summary ... ok

Ran 16 tests

OK
```

If a test is skipped, it usually means the command is not using the project `.venv` or a dependency such as SQLAlchemy is missing.

## Windows Test Runner

Run this from the repository root:

```powershell
.\run_tests.bat
```

Purpose:

- run the automated unit and repository tests;
- run the Python compile check;
- run a fresh SQLite Alembic migration smoke test;
- print the important paths, environment variables, commands, and migration inspection output for debugging.

Expected final output:

```text
[PASS] All automated checks passed.
```

This script intentionally covers stable automated checks. Manual API and frontend smoke tests are still listed below, and the script should be updated when those checks become safe to automate.

## Compile Check

Run:

```powershell
$env:PYTHONPATH = "backend"
.\backend\.venv\Scripts\python.exe -m compileall backend\app backend\alembic tests
```

Purpose:

- catch Python syntax errors;
- catch malformed migration files;
- verify modules can be imported and compiled.

Expected output:

```text
Listing 'backend\app'...
Listing 'backend\alembic'...
Listing 'tests'...
```

There should be no traceback or `SyntaxError`.

After running compile checks, Python may create `__pycache__` directories. They are ignored by Git, but you can remove them with:

```powershell
Remove-Item -LiteralPath 'X:\My Finance\Tracker\backend\app\__pycache__','X:\My Finance\Tracker\backend\app\services\__pycache__','X:\My Finance\Tracker\backend\alembic\__pycache__','X:\My Finance\Tracker\backend\alembic\versions\__pycache__','X:\My Finance\Tracker\tests\__pycache__' -Recurse -Force
```

## Alembic Migration Smoke Test

Run this with a temporary SQLite database so your real local database is not touched:

```powershell
$db = "X:\My Finance\Tracker\.local\migration-test.sqlite3"
if (Test-Path $db) { Remove-Item -LiteralPath $db -Force }

$env:INVESTMENT_TRACKER_DATABASE_URL = "sqlite:///X:/My Finance/Tracker/.local/migration-test.sqlite3"

.\backend\.venv\Scripts\alembic.exe -c backend\alembic.ini upgrade head
```

Purpose:

- verify Alembic can create a fresh database from migrations;
- verify `backend/alembic.ini`, `backend/alembic/env.py`, and migration files are wired correctly;
- verify the initial schema can be recreated from versioned migration history.

Expected output:

```text
INFO  [alembic.runtime.migration] Context impl SQLiteImpl.
INFO  [alembic.runtime.migration] Will assume non-transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 20260523_0001, Initial schema.
```

Then inspect the tables:

```powershell
@'
import sqlite3

con = sqlite3.connect(r".local\migration-test.sqlite3")
rows = con.execute("select name from sqlite_master where type='table' order by name")
print([row[0] for row in rows])
'@ | .\backend\.venv\Scripts\python.exe
```

Expected output includes:

```text
accounts
alembic_version
dca_settings
import_sessions
market_price_history
market_prices
portfolios
transaction_fingerprints
transactions
```

The `alembic_version` table is important because it proves Alembic has marked the database with the migration revision it applied.

## App Startup Migration Smoke Test

Run:

```powershell
$env:INVESTMENT_TRACKER_DATABASE_URL = "sqlite:///X:/My Finance/Tracker/.local/startup-test.sqlite3"
cd "X:\My Finance\Tracker\backend"
.\.venv\Scripts\uvicorn.exe app.main:app --reload
```

Then open:

```text
http://127.0.0.1:8000/api/health
```

Purpose:

- verify FastAPI startup calls database initialization;
- verify startup migrations do not block the app from serving requests;
- verify a new SQLite database can be created through normal app startup.

Expected API response:

```json
{"status":"ok"}
```

Expected terminal behavior:

- Uvicorn starts normally;
- no migration traceback appears;
- `/api/health` returns `200 OK`.

## Duplicate-Safe CSV Import Smoke Test

Start the backend:

```powershell
cd "X:\My Finance\Tracker\backend"
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

From another terminal, upload the sample CSV:

```powershell
curl.exe -F "file=@X:\My Finance\Tracker\samples\fortuneo_transactions_sample.csv" "http://127.0.0.1:8000/api/transactions/upload?portfolio_id=default"
```

Purpose:

- verify the upload endpoint accepts a Fortuneo-style CSV;
- verify transactions are persisted;
- verify import sessions are recorded;
- verify duplicates are skipped on repeated import.

Expected first upload:

```json
{
  "row_count": 4,
  "imported": 4,
  "duplicates": 0,
  "total": 4
}
```

Run the same command again.

Expected second upload:

```json
{
  "row_count": 4,
  "imported": 0,
  "duplicates": 4,
  "total": 4
}
```

The important signal is that `total` stays at `4`, not `8`.

## Historical Market Price Smoke Test

Start the backend:

```powershell
cd "X:\My Finance\Tracker\backend"
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

From another terminal, write two history points:

```powershell
$payload = @{
  prices = @(
    @{
      symbol = "CW8.PA"
      price_date = "2026-01-15"
      close = 470.50
      currency = "EUR"
      source = "manual"
    },
    @{
      symbol = "CW8.PA"
      price_date = "2026-01-16"
      close = 472.10
      currency = "EUR"
      source = "manual"
    }
  )
} | ConvertTo-Json -Depth 5

Invoke-RestMethod `
  -Method Put `
  -Uri "http://127.0.0.1:8000/api/market/history" `
  -ContentType "application/json" `
  -Body $payload
```

Purpose:

- verify the API can store historical price points;
- verify symbol normalization;
- verify the table can be read by date range.

Expected write response:

```json
{"updated":2}
```

Read the history back:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/market/history/CW8.PA?start_date=2026-01-15&end_date=2026-01-16"
```

Expected response contains two rows ordered by date:

```json
[
  {
    "symbol": "CW8.PA",
    "price_date": "2026-01-15",
    "close": 470.5,
    "currency": "EUR",
    "source": "manual"
  },
  {
    "symbol": "CW8.PA",
    "price_date": "2026-01-16",
    "close": 472.1,
    "currency": "EUR",
    "source": "manual"
  }
]
```

## Frontend Backend Connection Smoke Test

Start the backend:

```powershell
cd "X:\My Finance\Tracker\backend"
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

Serve the frontend from the repository root:

```powershell
cd "X:\My Finance\Tracker"
python -m http.server 8001 --bind 127.0.0.1
```

Open:

```text
http://127.0.0.1:8001/frontend/index.html
```

Purpose:

- verify the browser can load the standalone frontend;
- verify CORS allows the frontend to talk to the backend;
- verify the page can connect to `/api/health`, `/api/portfolios`, `/api/accounts`, and `/api/portfolio`;
- verify CSV upload uses the backend when connected.

Expected page behavior:

- top-right status shows `Backend connected`;
- import panel shows `Default Portfolio`;
- CSV upload status says something like:

```text
Imported 4 row(s), skipped 0 duplicate(s) from fortuneo_transactions_sample.csv.
```

If the page says:

```text
Imported 4 transaction rows from fortuneo_transactions_sample.csv in demo mode.
```

then the frontend is not connected to the backend. Check that FastAPI is running at `http://127.0.0.1:8000`, then click `Connect API`.

## When To Run Which Test

Run automated tests after any backend logic change:

```powershell
.\backend\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Run compile checks after touching Python modules or Alembic files:

```powershell
.\backend\.venv\Scripts\python.exe -m compileall backend\app backend\alembic tests
```

Run Alembic migration smoke tests after changing:

- SQLAlchemy models;
- migration files;
- database initialization logic;
- `backend/alembic.ini`;
- `backend/alembic/env.py`.

Run duplicate-safe import smoke tests after changing:

- CSV parser;
- transaction repository;
- import endpoint;
- transaction fingerprint logic.

Run historical market price smoke tests after changing:

- `MarketPriceHistoryRecord`;
- market history repository functions;
- `/api/market/history` endpoints;
- migrations that touch market price history.

Run frontend backend connection smoke tests after changing:

- `frontend/index.html`;
- backend CORS config;
- API route payloads used by the frontend.

## Synthetic Fixture Dataset

The repository includes a small synthetic golden dataset under:

```text
tests/fixtures/
```

Purpose:

- provide stable Fortuneo-style CSV data without using private real transactions;
- cover buys, sells, fees, dividends, two accounts, French number formatting, duplicate rows, historical holding prices, and benchmark prices;
- give future API response schema, route, and import-preview tests exact expected outputs.

Key files:

- `fortuneo_golden.csv`
- `fortuneo_duplicate_rows.csv`
- `market_history_basic.json`
- `expected_portfolio_summary.json`
- `expected_import_preview.json`
- `expected_duplicate_preview.json`

The fixture validation tests live in:

```text
tests/test_fixtures.py
```

Update the expected JSON files whenever intentional business logic changes alter cost basis, cash flow, portfolio history, duplicate detection, or preview payloads.

## Current Baseline

As of this guide, the healthy baseline is:

```text
Automated tests: 16 tests, OK
Alembic fresh SQLite migration: OK
Duplicate CSV upload: first import saves rows, second import skips duplicates
Historical market prices: range write/read works
Frontend: demo fallback works, backend-connected mode works when FastAPI is running
```
