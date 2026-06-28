# Enhanced DCA Investment Tracker

A personalized investment tracker for an Enhanced Dollar Cost Averaging workflow:

- import historical Fortuneo transactions from CSV;
- compute open holdings, average cost, allocation, and unrealized performance;
- compare current allocations against editable per-portfolio targets;
- summarize monthly investment activity and benchmark-relative returns;
- track market prices manually or through a backend adapter for `yfinance`;
- compute the next investment amount from market performance and volatility;
- run as a local React/Vite + FastAPI application, with SQLite today and PostgreSQL-compatible models for later.

This repository now contains a working local prototype plus a backend service skeleton.

For a deeper walkthrough of the modules, data flow, and architecture, read:

```text
docs/ARCHITECTURE.md
```

For test commands, manual smoke checks, and expected outputs, read:

```text
docs/TESTING.md
```

## Project Layout

```text
.
|-- docs/
|   |-- ARCHITECTURE.md                # architecture and onboarding guide
|   |-- RELEASE_CHECKLIST.md           # first-release readiness checklist
|   `-- TESTING.md                     # test guide and expected outputs
|-- index.html                         # local launcher note for the Vite frontend
|-- frontend/
|   |-- index.html                     # Vite HTML shell
|   |-- package.json                   # frontend scripts and dependencies
|   `-- src/
|       |-- main.jsx                   # React dashboard
|       `-- styles.css                 # app styling
|-- backend/
|   |-- alembic.ini                    # migration config
|   |-- alembic/                       # database migrations
|   |-- requirements.txt
|   `-- app/
|       |-- main.py                    # FastAPI routes
|       |-- database.py                # SQLAlchemy engine/session setup
|       |-- domain.py                  # core dataclasses
|       |-- models.py                  # SQLite/PostgreSQL-compatible tables
|       |-- repositories.py            # persistence adapters
|       |-- schemas.py                 # API request/response schemas
|       `-- services/
|           |-- csv_import.py          # Fortuneo-like CSV parser
|           |-- portfolio.py           # holdings and performance calculations
|           |-- portfolio_history.py   # historical portfolio and benchmark series
|           |-- portfolio_analytics.py # target allocation, activity, and benchmark analytics
|           |-- dca.py                 # DCA strategy recommendation engine
|           `-- market_data.py         # static and yfinance market providers
|-- samples/
|   `-- fortuneo_transactions_sample.csv
|-- start_backend.bat                  # Windows backend launcher
|-- start_backend.sh                   # Linux/WSL backend launcher
|-- start_frontend.bat                 # Windows frontend launcher
|-- start_frontend.sh                  # Linux/WSL frontend launcher
|-- run_tests.bat                      # Windows test runner
|-- run_tests.sh                       # Linux/WSL test runner
`-- tests/
    |-- fixtures/                       # synthetic golden CSV/JSON data
    |-- test_api_routes.py              # FastAPI route tests
    |-- test_fixtures.py                # fixture validation
    |-- test_repositories.py
    `-- test_services.py
```

## Frontend Setup

The frontend is a Vite React app. Install Node.js LTS, then install frontend dependencies once:

```powershell
cd frontend
npm install
```

Start the frontend from the repository root:

```powershell
.\start_frontend.bat
```

On Linux/WSL:

```sh
./start_frontend.sh
```

Open:

```text
http://127.0.0.1:5173
```

The frontend includes:

- demo Fortuneo-style transactions;
- backend-persisted manual transaction entry with security search for buy, sell, dividend, fee, and cash outflow rows;
- CSV preview and confirmed upload when FastAPI is running;
- editable current prices;
- portfolio metrics and holdings table;
- portfolio/account selection from the API;
- allocation visualization and backend portfolio history charting;
- target allocation editing, drift bars, monthly activity, and benchmark comparison when the backend is connected;
- intraday portfolio ranges with daily-history fallback when intraday rows are unavailable;
- hidden/security tracking controls and ticker-level transaction deletion for clean re-imports;
- S&P 500 and Nasdaq 100 benchmark backfill controls;
- saved Normal and Enhanced DCA strategy plan controls.

If the FastAPI backend is not available at `http://127.0.0.1:8000`, the frontend stays in demo mode and computes locally.

## Backend Setup

Python 3.10+ is available in this workspace. Create a virtual environment before installing runtime dependencies:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

After the virtual environment exists, the quickest way to start the backend from the repository root is:

```powershell
.\start_backend.bat
```

It serves FastAPI at `http://127.0.0.1:8000` and stores local testing data in `.local/tracker-dev.sqlite3` unless `INVESTMENT_TRACKER_DATABASE_URL` is already set. To use another port:

```powershell
.\start_backend.bat 8766
```

On Linux/WSL:

```sh
cd backend
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
cd ..
./start_backend.sh
```

By default, FastAPI stores data in SQLite at:

```text
data/tracker.sqlite3
```

Override this with:

```powershell
$env:INVESTMENT_TRACKER_DATABASE_URL = "sqlite:///C:/path/to/tracker.sqlite3"
```

The SQLAlchemy models are intentionally PostgreSQL-compatible, so the same repository layer can later point at a PostgreSQL URL.

## Database Migrations

The backend uses Alembic for schema migrations. FastAPI runs migrations on startup when Alembic is installed.

Run migrations manually from `backend/` with:

```powershell
.\.venv\Scripts\Activate.ps1
alembic upgrade head
```

Or from the repository root:

```powershell
.\backend\.venv\Scripts\Activate.ps1
alembic -c backend/alembic.ini upgrade head
```

Existing local SQLite databases created before Alembic are automatically baselined on first startup.

The API exposes:

```text
GET    /api/health
GET    /api/portfolios
POST   /api/portfolios
GET    /api/accounts
POST   /api/accounts
GET    /api/transactions
POST   /api/transactions
DELETE /api/transactions/{ticker}
POST   /api/transactions/preview
POST   /api/transactions/upload
GET    /api/security-mappings
PUT    /api/security-mappings
DELETE /api/security-mappings
GET    /api/hidden-securities
PUT    /api/hidden-securities
DELETE /api/hidden-securities
GET    /api/allocation-targets
PUT    /api/allocation-targets
GET    /api/securities/search
PUT    /api/market/prices
GET    /api/market/{ticker}
PUT    /api/market/history
GET    /api/market/history/{ticker}
POST   /api/market/history/backfill
POST   /api/market/intraday/backfill
GET    /api/portfolio
GET    /api/portfolio/analytics
GET    /api/portfolio/history
GET    /api/portfolio/history/intraday
GET    /api/dca/plans
POST   /api/dca/plans
GET    /api/dca/plans/{plan_id}
PUT    /api/dca/plans/{plan_id}
DELETE /api/dca/plans/{plan_id}
POST   /api/dca/plans/{plan_id}/recommendation
```

Current storage is persistent SQLite for portfolios, accounts, transactions, import sessions, transaction fingerprints, security label mappings, hidden securities, allocation targets, DCA plans, latest market prices, daily market price history, and intraday market price history. Manual transaction entry and CSV imports both use transaction fingerprints to skip exact duplicates. CSV imports also return an import summary.

## Run Automated Tests

The automated tests use local fixtures and isolated SQLite databases. They do not require network access. For full testing guidance, see `docs/TESTING.md`.

```powershell
$env:PYTHONPATH = "backend"
python -m unittest discover -s tests
```

Or run the full local check script:

```powershell
.\run_tests.bat
```

On Linux/WSL:

```sh
./run_tests.sh
```

The test runner executes Python unit/repository/API tests, a Python compile check, and a fresh SQLite Alembic migration smoke test. It also runs `npm run build` when Node dependencies are installed.

Covered behavior:

- Fortuneo-style semicolon CSV with French number formats;
- manual transaction creation, validation, duplicate detection, and amount-style dividend/fee/cash rows;
- buy/sell cost-basis handling;
- portfolio value and return calculations;
- target allocation drift, monthly activity, and benchmark comparison analytics.
- Normal and Enhanced DCA plan recommendations.
- SQLite repository persistence when SQLAlchemy is installed.
- duplicate-safe CSV import sessions.
- S&P 500/Nasdaq 100 historical market price storage and range reads.
- intraday market price storage and fallback portfolio history reads.
- portfolio history and benchmark normalization.
- persisted named DCA strategy plans.
- persisted and editable per-portfolio Fortuneo security label mappings.
- hidden security tracking and ticker-level transaction deletion/re-import.
- persisted per-portfolio allocation targets.
- synthetic golden fixtures for parser, summary, history, and duplicate-preview behavior.
- FastAPI route contracts for previews, mapping-assisted uploads, portfolio summaries, portfolio analytics, allocation targets, DCA plans, market history, intraday history, hidden securities, deletion, and validation errors.
- Vite frontend static checks for backend-only manual entry, CSV/ZIP import endpoints, security search, and app layout files.

## CSV Import Format

The importer accepts common French and English headers. It accepts plain CSV files and Fortuneo ZIP exports that contain a `HistoriqueOperations*.csv` file. For Fortuneo-like investment exports, this shape is supported:

```csv
Date operation;Operation;Code valeur;Quantite;Prix unitaire;Frais;Devise;Compte;Libelle
15/01/2026;Achat;CW8.PA;3;470,50;1,95;EUR;PEA;Amundi MSCI World
```

The parser also recognizes real Fortuneo bourse headers such as `Qte`, `Prix d'exe`, `Courtage/Prelevement`, `Montant brut`, and `Montant net`, including their accented Fortuneo forms.

Required fields are date, operation type, and security identifier. Quantity, price, fees, amount, currency, account, and description are optional or inferred when possible. Some Fortuneo bourse exports provide only a security label in `libelle`; preview marks those rows as `needs_mapping`, searches Yahoo Finance with raw and cleaned label queries, and requires the user to confirm a ticker before import. Confirmed mappings are saved per portfolio, reused on later imports, and editable from the frontend holdings area.

CSV uploads return an import summary:

```json
{
  "import_session_id": 1,
  "portfolio_id": "default",
  "filename": "fortuneo.csv",
  "file_hash": "...",
  "row_count": 12,
  "imported": 10,
  "duplicates": 2,
  "total": 42
}
```

Duplicate detection is based on a transaction fingerprint: date, ticker, transaction type, quantity, price, fees, currency, and account.

## DCA Strategy Logic

Normal DCA keeps the next contribution at the saved base amount.

Enhanced DCA adjusts that base amount from benchmark movement and optional volatility:

```text
Market condition        Adjustment
<= -5%                  +50%
-5% to -3%              +30%
-3% to -1%              +20%
-1% to +3%              unchanged
+3% to +5%              -20%
>= +5%                  -30%
```

If volatility is high and the recommendation is already increasing contributions, the engine adds another 10%. If volatility is low, it trims the increase by 10%.

Saved DCA plans are named per portfolio. A plan recommendation returns a headline next investment amount and, when allocation targets exist, suggested per-ticker contribution amounts.

## Next Build Steps

1. Harden imports and add reconciliation tools against real Fortuneo exports.
2. Add basic realized gain estimates and French tax/account reporting fields, especially PEA vs CTO.
3. Package the local release experience further, including sample data restore/reset and backup helpers.
4. Add authentication after local single-user workflows are mature.

## License

MIT License. See `LICENSE`.
