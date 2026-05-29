# Enhanced DCA Investment Tracker

A personalized investment tracker for an Enhanced Dollar Cost Averaging workflow:

- import historical Fortuneo transactions from CSV;
- compute open holdings, average cost, allocation, and unrealized performance;
- track market prices manually in the MVP, with a backend adapter for `yfinance`;
- compute the next investment amount from market performance and volatility;
- grow toward a React + FastAPI + PostgreSQL application.

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
|   `-- TESTING.md                     # test guide and expected outputs
|-- index.html                         # redirects to the frontend prototype
|-- frontend/
|   `-- index.html                     # standalone React dashboard
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
|           |-- dca.py                 # Enhanced DCA recommendation engine
|           `-- market_data.py         # static and yfinance market providers
|-- samples/
|   `-- fortuneo_transactions_sample.csv
`-- tests/
    |-- fixtures/                       # synthetic golden CSV/JSON data
    |-- test_api_routes.py              # FastAPI route tests
    |-- test_fixtures.py                # fixture validation
    |-- test_repositories.py
    `-- test_services.py
```

## Frontend Demo

Open `index.html` or `frontend/index.html` in a browser.

The frontend currently runs without a build step. It uses React from a CDN and includes:

- demo Fortuneo-style transactions;
- CSV preview and confirmed upload when FastAPI is running;
- editable current prices;
- portfolio metrics and holdings table;
- portfolio/account selection from the API;
- allocation visualization and backend portfolio history charting;
- S&P 500 and Nasdaq 100 benchmark backfill controls;
- Enhanced DCA recommendation controls.

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
POST   /api/transactions/preview
POST   /api/transactions/upload
PUT    /api/market/prices
GET    /api/market/{ticker}
PUT    /api/market/history
GET    /api/market/history/{ticker}
POST   /api/market/history/backfill
GET    /api/portfolio
GET    /api/portfolio/history
GET    /api/dca/settings
PUT    /api/dca/settings
POST   /api/dca/recommendation
```

Current storage is persistent SQLite for portfolios, accounts, transactions, import sessions, transaction fingerprints, latest market prices, historical market prices, and DCA settings. CSV imports skip duplicate transactions and return an import summary.

## Run Automated Tests

The automated tests use local fixtures and isolated SQLite databases. They do not require network access. For full testing guidance, see `docs/TESTING.md`.

```powershell
$env:PYTHONPATH = "backend"
python -m unittest discover -s tests
```

Covered behavior:

- Fortuneo-style semicolon CSV with French number formats;
- buy/sell cost-basis handling;
- portfolio value and return calculations;
- Enhanced DCA amount adjustment.
- SQLite repository persistence when SQLAlchemy is installed.
- duplicate-safe CSV import sessions.
- S&P 500/Nasdaq 100 historical market price storage and range reads.
- portfolio history and benchmark normalization.
- persisted DCA settings.
- synthetic golden fixtures for parser, summary, history, and duplicate-preview behavior.
- FastAPI route contracts for previews, uploads, portfolio summaries, market history, DCA settings, and validation errors.

## CSV Import Format

The importer accepts common French and English headers. For Fortuneo exports, this shape is supported:

```csv
Date operation;Operation;Code valeur;Quantite;Prix unitaire;Frais;Devise;Compte;Libelle
15/01/2026;Achat;CW8.PA;3;470,50;1,95;EUR;PEA;Amundi MSCI World
```

Required fields are date, operation type, and security identifier. Quantity, price, fees, amount, currency, account, and description are optional or inferred when possible.

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

## Enhanced DCA Logic

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

## Next Build Steps

1. Connect the frontend CSV flow to the import preview endpoint before saving rows.
2. Add richer analytics for allocation drift, contributions, and benchmark comparison.
3. Add authentication once local portfolio persistence is working.
4. Add French tax reporting fields for realized gains and account type, especially PEA vs CTO.
5. Move the frontend to a full React/Vite app once the standalone page becomes too large to maintain comfortably.

## License

MIT License. See `LICENSE`.
