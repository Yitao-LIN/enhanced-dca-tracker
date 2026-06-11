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

## Automated Tests

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
- verify intraday market price upsert, backfill, and fallback history behavior.
- verify hidden security filtering and ticker-level transaction deletion/re-import.
- verify DCA settings persistence.
- verify portfolio history and benchmark normalization.
- verify yfinance historical response normalization.
- verify synthetic golden fixtures stay aligned with parser, portfolio summary, portfolio history, and duplicate-preview expectations.
- verify FastAPI route contracts, response-model serialization, preview/upload behavior, portfolio summaries, market history, intraday history, DCA settings, hidden securities, and validation errors.

Expected output:

```text
test_dca_settings_and_recommendation_routes ... ok
test_dca_settings_rejects_inverted_multiplier_bounds ... ok
test_delete_ticker_transactions_allows_reimport ... ok
test_empty_portfolio_summary_returns_zeroes ... ok
test_fortuneo_account_export_preview_and_upload_report_wrong_export_type ... ok
test_health_and_reference_routes ... ok
test_hidden_security_routes_filter_summary_without_deleting_transactions ... ok
test_intraday_backfill_feeds_portfolio_history ... ok
test_intraday_backfill_rejects_reversed_datetime_range ... ok
test_intraday_history_rejects_invalid_interval ... ok
test_intraday_history_uses_daily_fallback_when_intraday_rows_are_missing ... ok
test_invalid_csv_preview_returns_row_errors_without_bad_request ... ok
test_invalid_csv_upload_returns_bad_request ... ok
test_market_history_and_portfolio_history_match_golden_fixture ... ok
test_market_history_backfill_rejects_reversed_date_range ... ok
test_market_history_backfill_skips_failed_symbols ... ok
test_portfolio_history_respects_range_and_hidden_securities ... ok
test_portfolio_summary_matches_golden_fixture ... ok
test_preview_golden_csv_matches_fixture_without_persisting ... ok
test_preview_keeps_mapping_row_editable_when_search_fails ... ok
test_preview_marks_duplicate_rows_and_existing_transactions ... ok
test_preview_retries_cleaned_query_when_raw_search_has_no_results ... ok
test_preview_returns_mapping_suggestions_for_unresolved_fortuneo_label ... ok
test_security_mapping_management_routes_are_portfolio_scoped ... ok
test_security_search_route_uses_provider ... ok
test_upload_deduplicates_repeated_confirmed_mapping_labels ... ok
test_upload_persists_confirmed_mapping_and_reuses_it ... ok
test_upload_transactions_skips_duplicates_and_lists_accounts ... ok
test_duplicate_preview_fixture_marks_duplicate_rows ... ok
test_golden_fixture_matches_expected_portfolio_history ... ok
test_golden_fixture_matches_expected_summary ... ok
test_backend_empty_history_does_not_render_demo_monthly_chart ... ok
test_market_price_parser_keeps_dot_decimal_prices ... ok
test_dca_settings_are_persisted_per_portfolio ... ok
test_hidden_securities_are_persisted_per_portfolio ... ok
test_import_allows_same_security_with_different_quantity ... ok
test_import_skips_duplicate_transactions ... ok
test_intraday_market_prices_upsert_and_filter_ranges ... ok
test_keeps_portfolios_isolated ... ok
test_market_price_history_upserts_and_filters_ranges ... ok
test_persists_transactions_and_prices ... ok
test_security_mappings_are_persisted_per_portfolio ... ok
test_existing_security_code_wins_over_mapping ... ok
test_fortuneo_account_export_is_rejected_clearly ... ok
test_parse_fortuneo_bourse_with_security_mapping ... ok
test_parse_fortuneo_bourse_zip_with_enriched_security_code ... ok
test_parse_fortuneo_style_csv ... ok
test_parse_zip_without_fortuneo_csv_fails_clearly ... ok
test_preview_fortuneo_bourse_without_security_code_reports_mapping_error ... ok
test_preview_fortuneo_bourse_zip_reports_mapping_row ... ok
test_enhanced_dca_applies_settings_multiplier_bounds ... ok
test_enhanced_dca_increases_on_market_drawdown ... ok
test_normalize_yfinance_history ... ok
test_normalize_yfinance_search_quotes ... ok
test_build_holdings_reduces_cost_basis_on_sell ... ok
test_build_portfolio_history_with_normalized_benchmarks ... ok
test_build_portfolio_intraday_history_with_normalized_benchmarks ... ok
test_portfolio_history_starts_at_first_transaction ... ok
test_summarize_empty_portfolio_returns_zeroes ... ok
test_summarize_portfolio_prices_holdings ... ok

Ran 60 tests

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
INFO  [alembic.runtime.migration] Running upgrade 20260523_0001 -> 20260524_0002, Add market price history.
INFO  [alembic.runtime.migration] Running upgrade 20260524_0002 -> 20260524_0003, Add DCA settings.
INFO  [alembic.runtime.migration] Running upgrade 20260524_0003 -> 20260530_0004, Add security mappings.
INFO  [alembic.runtime.migration] Running upgrade 20260530_0004 -> 20260607_0005, Add hidden securities.
INFO  [alembic.runtime.migration] Running upgrade 20260607_0005 -> 20260609_0006, Add intraday market price history.
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
hidden_securities
import_sessions
market_price_history
market_price_intraday
market_prices
portfolios
security_mappings
transaction_fingerprints
transactions
```

The `alembic_version` table is important because it proves Alembic has marked the database with the migration revision it applied.

## App Startup Migration Smoke Test

Run:

```powershell
cd "X:\My Finance\Tracker"
$env:INVESTMENT_TRACKER_DATABASE_URL = "sqlite:///X:/My Finance/Tracker/.local/startup-test.sqlite3"
.\start_backend.bat
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
cd "X:\My Finance\Tracker"
.\start_backend.bat
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

## Intraday Market Price Smoke Test

Start the backend:

```powershell
cd "X:\My Finance\Tracker\backend"
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

From another terminal, backfill a short intraday range for one symbol:

```powershell
$payload = @{
  symbols = @("CW8.PA")
  start_at = "2026-06-09T09:00:00"
  end_at = "2026-06-09T10:00:00"
  interval = "30m"
  currency = "EUR"
  source = "yfinance"
} | ConvertTo-Json -Depth 5

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/market/intraday/backfill" `
  -ContentType "application/json" `
  -Body $payload
```

Purpose:

- verify the API accepts intraday ranges and intervals such as `30m` or `1h`;
- verify intraday provider rows are persisted in `market_price_intraday`;
- verify latest prices are refreshed from the latest intraday point;
- verify failures are reported per symbol instead of failing the whole request.

Expected write response shape:

```json
{
  "symbols": ["CW8.PA"],
  "source": "yfinance",
  "interval": "30m",
  "updated": 2,
  "failures": []
}
```

The exact `updated` count depends on provider availability and market hours. If a symbol has no intraday data, the response should include that symbol in `failures`.

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
- verify CSV/ZIP preview, security-label mapping, and confirmed upload use the backend when connected;
- verify chart range switching calls daily or intraday history endpoints as appropriate;
- verify hide/restore and delete/re-import controls use the backend when connected.

Expected page behavior:

- top-right status shows `Backend connected`;
- import panel shows `Default Portfolio`;
- choosing the sample CSV shows a preview status like:

```text
Reviewed 4 row(s) from fortuneo_transactions_sample.csv: 4 new, 0 mapping(s), 0 duplicate(s), 0 error(s).
```

- clicking `Confirm import` then shows something like:

```text
Imported 4 row(s), skipped 0 duplicate(s) from fortuneo_transactions_sample.csv.
```

- for a Fortuneo bourse CSV or ZIP that has `libelle` but no `Code valeur`, preview shows `Map` rows; confirm each ticker suggestion before clicking `Confirm import`.

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

Run intraday market price smoke tests after changing:

- `IntradayMarketPriceRecord`;
- intraday market history repository functions;
- `/api/market/intraday/backfill`;
- `/api/portfolio/history/intraday`;
- intraday fallback logic from daily history.

Run hidden-security and ticker deletion smoke checks after changing:

- `HiddenSecurityRecord`;
- hidden-security repository functions;
- `/api/hidden-securities` endpoints;
- `/api/transactions/{ticker}` deletion;
- portfolio summary/history filtering.

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
- cover buys, sells, fees, dividends, two accounts, French number formatting, duplicate rows, historical holding prices, benchmark prices, Fortuneo ZIP parsing, real bourse headers, unsupported bank-account exports, unmapped security-label preview errors, cleaned-query search retries, saved mapping management, mapping-assisted imports, hidden-security filtering, ticker deletion, and intraday fallback behavior;
- give API response schema, route, and import-preview tests exact expected outputs.

Key files:

- `fortuneo_golden.csv`
- `fortuneo_duplicate_rows.csv`
- `fortuneo_bourse_mapping.zip`
- `HistoriqueOperationsBourse_mapping.csv`
- `market_history_basic.json`
- `expected_portfolio_summary.json`
- `expected_import_preview.json`
- `expected_duplicate_preview.json`

The fixture validation tests live in:

```text
tests/test_fixtures.py
```

Update the expected JSON files whenever intentional business logic changes alter cost basis, cash flow, portfolio history, duplicate detection, or preview payloads.

## API Route Tests

The route-level tests live in:

```text
tests/test_api_routes.py
```

Purpose:

- call FastAPI endpoints through `TestClient` instead of calling services directly;
- use an isolated in-memory SQLite database by overriding the `get_db` dependency;
- verify response-model serialization for `Decimal`, `date`, and `datetime` fields;
- exercise the golden CSV preview/upload, mapping-assisted Fortuneo upload, duplicate-safe re-upload, account listing, price updates, hidden securities, ticker deletion/re-import, portfolio summary, daily and intraday market history, portfolio history, DCA settings, DCA recommendation, and validation error paths.

Run these after changing:

- `backend/app/main.py`;
- `backend/app/schemas.py`;
- API request or response payloads used by the frontend;
- database dependency wiring used by routes.

## Current Baseline

As of this guide, the healthy baseline is:

```text
Automated tests: 60 tests, OK
Alembic fresh SQLite migration: OK
Duplicate CSV upload: first import saves rows, second import skips duplicates
Historical market prices: range write/read works
Intraday market prices: backfill, range filtering, and daily fallback work
Hidden securities: filter summaries/history without deleting transactions
Frontend: demo fallback works, backend-connected mode works when FastAPI is running
```
