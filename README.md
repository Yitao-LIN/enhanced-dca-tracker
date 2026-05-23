# Enhanced DCA Investment Tracker

A personalized investment tracker for an Enhanced Dollar Cost Averaging workflow:

- import historical Fortuneo transactions from CSV;
- compute open holdings, average cost, allocation, and unrealized performance;
- track market prices manually in the MVP, with a backend adapter for `yfinance`;
- compute the next investment amount from market performance and volatility;
- grow toward a React + FastAPI + PostgreSQL application.

This repository now contains a working local prototype plus a backend service skeleton.

## Project Layout

```text
.
|-- index.html                         # redirects to the frontend prototype
|-- frontend/
|   `-- index.html                     # standalone React dashboard
|-- backend/
|   |-- requirements.txt
|   `-- app/
|       |-- main.py                    # FastAPI routes
|       |-- domain.py                  # core dataclasses
|       |-- schemas.py                 # API request schemas
|       `-- services/
|           |-- csv_import.py          # Fortuneo-like CSV parser
|           |-- portfolio.py           # holdings and performance calculations
|           |-- dca.py                 # Enhanced DCA recommendation engine
|           `-- market_data.py         # static and yfinance market providers
|-- samples/
|   `-- fortuneo_transactions_sample.csv
`-- tests/
    `-- test_services.py
```

## Frontend Demo

Open `index.html` or `frontend/index.html` in a browser.

The frontend currently runs without a build step. It uses React from a CDN and includes:

- demo Fortuneo-style transactions;
- CSV upload and local parsing;
- editable current prices;
- portfolio metrics and holdings table;
- allocation visualization;
- Enhanced DCA recommendation controls.

## Backend Setup

Python 3.10+ is available in this workspace. Create a virtual environment before installing runtime dependencies:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API will expose:

```text
GET    /api/health
GET    /api/transactions
POST   /api/transactions
POST   /api/transactions/upload
PUT    /api/market/prices
GET    /api/market/{ticker}
GET    /api/portfolio
POST   /api/dca/recommendation
```

Current storage is in-memory so the API is easy to iterate on. The next backend step is to add PostgreSQL persistence for users, portfolios, transactions, cached market data, and DCA settings.

## Run Service Tests

The service tests do not require FastAPI or network access.

```powershell
$env:PYTHONPATH = "backend"
python -m unittest discover -s tests
```

Covered behavior:

- Fortuneo-style semicolon CSV with French number formats;
- buy/sell cost-basis handling;
- portfolio value and return calculations;
- Enhanced DCA amount adjustment.

## CSV Import Format

The importer accepts common French and English headers. For Fortuneo exports, this shape is supported:

```csv
Date operation;Operation;Code valeur;Quantite;Prix unitaire;Frais;Devise;Compte;Libelle
15/01/2026;Achat;CW8.PA;3;470,50;1,95;EUR;PEA;Amundi MSCI World
```

Required fields are date, operation type, and security identifier. Quantity, price, fees, amount, currency, account, and description are optional or inferred when possible.

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

1. Add persistent PostgreSQL models and migrations.
2. Connect the frontend to the FastAPI routes.
3. Add background market fetching for tracked tickers and benchmarks.
4. Add authentication once local portfolio persistence is working.
5. Add French tax reporting fields for realized gains and account type, especially PEA vs CTO.
