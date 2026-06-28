# Testing Guide

This document explains the tests and manual checks used by this project. Update it whenever a new test, smoke check, or required verification step is added.

The goal is not only to know which command to run, but also why the check exists and what a healthy result looks like.

## Test Environment

Most commands assume you are at the repository root:

```powershell
cd "X:\My Finance\Tracker"
```

Use the backend virtual environment on Windows:

```powershell
.\backend\.venv\Scripts\Activate.ps1
```

For Python imports, the backend package path must be available:

```powershell
$env:PYTHONPATH = "backend"
```

On Linux/WSL:

```sh
cd /path/to/enhanced-dca-tracker
cd backend
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
cd ..
export PYTHONPATH=backend
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
- verify Normal and Enhanced DCA recommendation logic;
- verify SQLAlchemy repository persistence;
- verify portfolio/account isolation;
- verify duplicate-safe CSV imports.
- verify historical market price upsert and range filtering.
- verify intraday market price upsert, backfill, and fallback history behavior.
- verify hidden security filtering and ticker-level transaction deletion/re-import.
- verify allocation target persistence and portfolio analytics.
- verify DCA plan persistence.
- verify portfolio history and benchmark normalization.
- verify yfinance historical response normalization.
- verify synthetic golden fixtures stay aligned with parser, portfolio summary, portfolio history, and duplicate-preview expectations.
- verify FastAPI route contracts, response-model serialization, manual transaction behavior, preview/upload behavior, portfolio summaries, portfolio analytics, allocation targets, DCA plans, market history, intraday history, hidden securities, and validation errors.
- verify the Vite frontend source calls analytics endpoints and does not render demo analytics as backend data.
- verify the Vite shell, stylesheet, backend-only manual transaction entry, security search, and CSV/ZIP import endpoints.

Expected output:

```text
test_allocation_target_routes_replace_and_validate_payloads ... ok
test_dca_plan_crud_and_recommendation_routes ... ok
test_dca_plan_routes_validate_errors ... ok
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
test_manual_amount_style_transactions_are_accepted ... ok
test_manual_buy_creates_account_summary_and_reports_duplicates ... ok
test_manual_transaction_ui_searches_security_mapping ... ok
test_manual_transaction_validation_rejects_invalid_payloads ... ok
test_market_history_and_portfolio_history_match_golden_fixture ... ok
test_market_history_backfill_rejects_reversed_date_range ... ok
test_market_history_backfill_skips_failed_symbols ... ok
test_portfolio_analytics_respects_targets_hidden_securities_and_empty_states ... ok
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
test_analytics_ui_calls_backend_endpoints ... ok
test_backend_empty_analytics_does_not_render_demo_activity ... ok
test_backend_empty_dca_plans_do_not_render_demo_plans_as_backend_data ... ok
test_backend_empty_history_does_not_render_demo_monthly_chart ... ok
test_dca_strategy_ui_uses_plan_endpoints ... ok
test_manual_transaction_entry_is_backend_only ... ok
test_manual_transaction_keeps_fortuneo_import_available ... ok
test_manual_transaction_ui_searches_security_mapping ... ok
test_manual_transaction_ui_uses_backend_create_endpoint ... ok
test_market_price_parser_keeps_dot_decimal_prices ... ok
test_vite_frontend_has_release_layout_styles ... ok
test_vite_frontend_mounts_react_app ... ok
test_allocation_targets_replace_and_validate_per_portfolio ... ok
test_dca_plans_are_persisted_per_portfolio_and_default_is_exclusive ... ok
test_hidden_securities_are_persisted_per_portfolio ... ok
test_import_allows_same_security_with_different_quantity ... ok
test_import_skips_duplicate_transactions ... ok
test_intraday_market_prices_upsert_and_filter_ranges ... ok
test_keeps_portfolios_isolated ... ok
test_legacy_dca_settings_bootstrap_into_default_plan ... ok
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
test_dca_allocation_split_falls_back_to_target_percent ... ok
test_dca_allocation_split_returns_empty_without_targets ... ok
test_dca_allocation_split_uses_underweight_buy_values ... ok
test_normal_dca_keeps_base_amount ... ok
test_allocation_drift_with_partial_and_target_only_allocations ... ok
test_allocation_drift_without_targets_keeps_current_allocation_read_only ... ok
test_benchmark_comparison_handles_complete_missing_and_zero_start_history ... ok
test_normalize_yfinance_history ... ok
test_normalize_yfinance_search_quotes ... ok
test_build_holdings_reduces_cost_basis_on_sell ... ok
test_build_portfolio_history_with_normalized_benchmarks ... ok
test_build_portfolio_intraday_history_with_normalized_benchmarks ... ok
test_monthly_activity_groups_contributions_proceeds_dividends_and_fees ... ok
test_portfolio_history_carries_forward_prior_prices_for_newer_transaction ... ok
test_portfolio_history_starts_at_first_transaction ... ok
test_portfolio_intraday_history_carries_forward_prior_ticks ... ok
test_summarize_empty_portfolio_returns_zeroes ... ok
test_summarize_portfolio_prices_holdings ... ok

Ran 87 tests

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
- run `npm run build` when Node.js and `frontend/node_modules` are available;
- print the important paths, environment variables, commands, and migration inspection output for debugging.

Expected final output:

```text
[PASS] All available automated checks passed.
```

If npm or `frontend/node_modules` is unavailable, the frontend build check is skipped with an explicit `[SKIP]` line. Manual API and browser smoke tests are still listed below.

## Linux/WSL Test Runner

Run this from the repository root:

```sh
./run_tests.sh
```

Purpose:

- run the same unit/repository/API tests as the Windows runner;
- run the Python compile check;
- run a fresh SQLite Alembic migration smoke test;
- run `npm run build` when Node.js and `frontend/node_modules` are available.

Expected final output:

```text
[PASS] All available automated checks passed.
```

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
INFO  [alembic.runtime.migration] Running upgrade 20260609_0006 -> 20260614_0007, Add allocation targets.
INFO  [alembic.runtime.migration] Running upgrade 20260614_0007 -> 20260614_0008, Add DCA strategy plans.
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
allocation_targets
dca_plans
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
cd "X:\My Finance\Tracker"
.\start_backend.bat
```

Start the Vite frontend from another terminal:

```powershell
cd "X:\My Finance\Tracker"
cd frontend
npm install
cd ..
.\start_frontend.bat
```

Open:

```text
http://127.0.0.1:5173
```

Purpose:

- verify the browser can load the Vite frontend;
- verify CORS allows the frontend to talk to the backend;
- verify the page can connect to `/api/health`, `/api/portfolios`, `/api/accounts`, and `/api/portfolio`;
- verify the analytics section calls `/api/allocation-targets` and `/api/portfolio/analytics`;
- verify CSV/ZIP preview, security-label mapping, and confirmed upload use the backend when connected;
- verify chart range switching calls daily or intraday history endpoints as appropriate;
- verify hide/restore and delete/re-import controls use the backend when connected.
- verify target allocation edits save and refresh drift rows without rendering demo analytics as backend data.

Expected page behavior:

- sidebar status shows `Backend connected`;
- the Transactions view shows `Default Portfolio`;
- entering `AMUNDI MSCI WORLD` in the manual transaction `Search mapping` field and clicking `Search` returns ticker suggestions; clicking `Use` fills the manual transaction ticker.
- filling the manual transaction form with date `2026-01-15`, type `Buy`, ticker `CW8.PA`, quantity `1`, price `470.50`, fees `1.95`, currency `EUR`, and account `PEA`, then clicking `Add transaction`, shows a status like:

```text
Added buy transaction for CW8.PA.
```

- submitting the same manual row again shows a duplicate status like:

```text
Skipped duplicate transaction for CW8.PA.
```

- choosing the sample CSV shows a preview status like:

```text
Reviewed 4 row(s) from fortuneo_transactions_sample.csv.
```

- clicking `Confirm import` then shows something like:

```text
Imported 4 row(s), skipped 0 duplicate(s) from fortuneo_transactions_sample.csv.
```

- for a Fortuneo bourse CSV or ZIP that has `libelle` but no `Code valeur`, preview shows `Map` rows; confirm each ticker suggestion before clicking `Confirm import`.
- the Analytics view shows editable target inputs, allocation drift, monthly activity, and benchmark comparison cards when backend data exists.

If the page says:

```text
Demo mode
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

Run allocation target and portfolio analytics tests after changing:

- `AllocationTargetRecord`;
- allocation target repository functions;
- `/api/allocation-targets`;
- `/api/portfolio/analytics`;
- `backend/app/services/portfolio_analytics.py`;
- frontend analytics rendering in `frontend/src/main.jsx`.

Run frontend backend connection smoke tests after changing:

- `frontend/index.html`;
- `frontend/src/main.jsx`;
- `frontend/src/styles.css`;
- backend CORS config;
- API route payloads used by the frontend.

Run manual transaction smoke checks after changing:

- `POST /api/transactions`;
- `/api/securities/search`;
- `TransactionIn` or `TransactionCreateOut`;
- transaction fingerprint behavior;
- manual entry rendering or payload conversion in `frontend/src/main.jsx`.

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
- exercise the golden CSV preview/upload, mapping-assisted Fortuneo upload, duplicate-safe re-upload, account listing, price updates, hidden securities, allocation targets, ticker deletion/re-import, portfolio summary, portfolio analytics, daily and intraday market history, portfolio history, DCA plans, DCA recommendations, and validation error paths.

Run these after changing:

- `backend/app/main.py`;
- `backend/app/schemas.py`;
- API request or response payloads used by the frontend;
- database dependency wiring used by routes.

## Current Baseline

As of this guide, the healthy baseline is:

```text
Automated tests: 87 tests, OK
Alembic fresh SQLite migration: OK
Duplicate CSV upload: first import saves rows, second import skips duplicates
Historical market prices: range write/read works
Intraday market prices: backfill, range filtering, and daily fallback work
Hidden securities: filter summaries/history without deleting transactions
Allocation analytics: targets persist per portfolio, hidden securities stay excluded, missing benchmark history is an empty comparison
DCA plans: named Normal/Enhanced plans persist per portfolio and produce total plus per-ticker suggestions
Frontend: demo fallback works, backend-connected mode works when FastAPI is running
```
