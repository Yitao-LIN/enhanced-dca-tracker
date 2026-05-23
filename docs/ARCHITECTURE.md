# Architecture Guide

This guide explains how the project is organized and how data moves through the app. It is written for someone new to this repository, FastAPI, SQLAlchemy, or this style of development environment.

## Big Picture

The project currently has two main parts:

```text
frontend/index.html
    Browser UI prototype

backend/app/
    FastAPI API
    SQLAlchemy database layer
    Business logic services
```

The backend is intentionally split into layers:

```text
API routes
  -> repositories
    -> database tables

API routes
  -> services
    -> pure business calculations
```

This separation matters because portfolio math, CSV parsing, and DCA logic should be testable without running FastAPI or touching a database.

## Frontend

```text
frontend/index.html
```

The frontend is currently a standalone React prototype loaded from a CDN. It does not need a Node build step yet.

It can:

- load demo Fortuneo-like CSV data;
- import a CSV file in the browser;
- connect to the FastAPI backend at `http://127.0.0.1:8000`;
- load portfolios, accounts, and portfolio summaries from the API;
- upload Fortuneo CSV files through the backend import endpoint;
- save manually edited market prices through the API;
- compute holdings locally;
- let the user manually edit current market prices;
- display total value, invested amount, gains, allocation, and DCA recommendation.

If the backend is unavailable, the frontend falls back to demo mode and computes locally. This keeps the prototype useful even before the API is running.

```text
index.html
```

The root `index.html` is a tiny redirect page that opens `frontend/index.html`.

## Backend Entry Point

```text
backend/app/main.py
```

This file defines the FastAPI application and its HTTP routes.

Current API routes:

```text
GET  /api/health
GET  /api/portfolios
POST /api/portfolios
GET  /api/accounts
POST /api/accounts
GET  /api/transactions
POST /api/transactions
POST /api/transactions/upload
PUT  /api/market/prices
GET  /api/market/{ticker}
GET  /api/portfolio
POST /api/dca/recommendation
```

Each route that needs persistence receives a SQLAlchemy database session:

```python
db: Session = Depends(get_db)
```

FastAPI creates the session for the request, passes it into the route, and closes it afterward.

The app creates database tables on startup:

```python
@app.on_event("startup")
def on_startup() -> None:
    create_db_and_tables()
```

This is simple and useful for the early MVP. Later, once the schema gets more serious, this should be replaced by Alembic migrations.

## Domain Models

```text
backend/app/domain.py
```

This file contains the core business objects as dataclasses. These are not database tables and not API request schemas. They represent investment concepts used by the app.

Main classes:

```python
Transaction
Holding
PricedHolding
PortfolioSummary
MarketSnapshot
DcaRecommendation
```

For example, `Transaction` represents one buy, sell, dividend, fee, or cash operation.

It also has useful computed properties:

```python
gross_amount
cash_impact
```

Keeping these objects separate from SQLAlchemy makes the financial logic easier to test and change.

## API Schemas

```text
backend/app/schemas.py
```

This file contains Pydantic models used for validating API request bodies.

Current schemas:

```python
PortfolioIn
AccountIn
TransactionIn
PriceMap
DcaRequest
```

When the frontend sends JSON to FastAPI, FastAPI validates it with these schemas before the data reaches repositories or services.

Example request body for `DcaRequest`:

```json
{
  "base_amount": 1000,
  "market_change_percent": -2.3,
  "volatility_index": 18.5
}
```

## Database Setup

```text
backend/app/database.py
```

This file owns the SQLAlchemy database connection.

It defines:

```python
Base
engine
SessionLocal
create_db_and_tables()
get_db()
```

By default, the backend creates a SQLite database here:

```text
data/tracker.sqlite3
```

The database URL can be overridden with an environment variable:

```powershell
$env:INVESTMENT_TRACKER_DATABASE_URL = "sqlite:///C:/path/to/tracker.sqlite3"
```

Later this same layer can point to PostgreSQL:

```text
postgresql://user:password@localhost:5432/investment_tracker
```

## Database Tables

```text
backend/app/models.py
```

This file defines SQLAlchemy ORM tables.

Current tables:

```python
PortfolioRecord
AccountRecord
TransactionRecord
TransactionFingerprintRecord
ImportSessionRecord
MarketPriceRecord
```

`PortfolioRecord` stores a named portfolio, such as the default personal portfolio or a future strategy-specific portfolio.

Important fields:

- `slug`
- `name`
- `base_currency`
- `created_at`

`AccountRecord` stores brokerage/account containers inside a portfolio, such as `PEA` or `CTO`.

Important fields:

- `portfolio_record_id`
- `name`
- `institution`
- `account_type`
- `currency`

`TransactionRecord` stores imported or manually added investment transactions.

Important fields:

- `transaction_date`
- `ticker`
- `transaction_type`
- `quantity`
- `price`
- `fees`
- `currency`
- `account`
- `description`

`TransactionFingerprintRecord` stores a stable hash for each transaction inside a portfolio. It is used to skip duplicates during CSV imports without adding new columns to the existing `transactions` table.

Important fields:

- `portfolio_id`
- `fingerprint`
- `transaction_record_id`

`ImportSessionRecord` stores one row for each CSV import attempt.

Important fields:

- `portfolio_id`
- `filename`
- `file_hash`
- `row_count`
- `imported_count`
- `duplicate_count`
- `created_at`

`MarketPriceRecord` stores the latest known market price for each symbol.

Important fields:

- `symbol`
- `close`
- `previous_close`
- `currency`
- `as_of`
- `source`

Right now, the app stores one latest price per symbol. Later, it should also store historical market prices.

## Repositories

```text
backend/app/repositories.py
```

Repositories are the bridge between database rows and domain objects.

They know how to:

- create or resolve portfolios;
- create or resolve accounts;
- save a `Transaction` into a `TransactionRecord`;
- create transaction fingerprints;
- save import sessions;
- skip duplicate transaction imports;
- load database rows back into `Transaction` dataclasses;
- save or update market prices;
- return current prices as a `{ticker: price}` dictionary.

Current repository functions:

```python
ensure_portfolio()
create_portfolio()
list_portfolios()
ensure_account()
list_accounts()
add_transaction()
add_transactions()
import_transactions()
list_transactions()
count_transactions()
upsert_market_price()
get_market_prices()
```

This keeps SQLAlchemy code out of `main.py` and out of the business calculation services.

## CSV Import Service

```text
backend/app/services/csv_import.py
```

This file parses Fortuneo-like CSV exports.

It handles:

- semicolon and comma delimiters;
- French number formats such as `470,50`;
- French headers such as `Date operation`, `Quantite`, `Prix unitaire`, and `Frais`;
- operation types such as `Achat` and `Vente`;
- text encodings such as UTF-8 and Windows `cp1252`.

The main function is:

```python
parse_transactions_csv(raw_csv)
```

It returns a list of domain `Transaction` objects.

## Portfolio Service

```text
backend/app/services/portfolio.py
```

This file does portfolio math.

Main functions:

```python
build_holdings(transactions)
summarize_portfolio(transactions, current_prices)
```

`build_holdings()` takes raw transactions and computes open positions.

Example:

```text
Buy 3 shares at 100
Sell 1 share
Result: 2 shares left
```

The service also reduces the cost basis correctly after a sell.

`summarize_portfolio()` adds market prices and computes:

- total value;
- total invested;
- total gain;
- return percentage;
- market value per holding;
- allocation per holding.

This is one of the core engines of the app.

## DCA Service

```text
backend/app/services/dca.py
```

This computes the Enhanced DCA recommendation.

Main function:

```python
calculate_enhanced_dca(base_amount, market_change_percent, volatility_index)
```

Current rule:

```text
Market <= -5%      invest 150%
Market -5% to -3%  invest 130%
Market -3% to -1%  invest 120%
Stable             invest 100%
Market +3% to +5%  invest 80%
Market >= +5%      invest 70%
```

If volatility is high, the service can increase the recommendation further. If volatility is low, it trims the increase.

The rule is intentionally simple for now, but it is isolated so it can become configurable later.

## Market Data Service

```text
backend/app/services/market_data.py
```

This file defines market data providers.

Current providers:

```python
StaticMarketDataProvider
YFinanceMarketDataProvider
```

`StaticMarketDataProvider` is useful for tests or manual prices.

`YFinanceMarketDataProvider` uses `yfinance` to fetch quotes.

The API route:

```text
GET /api/market/{ticker}
```

uses this provider, saves the result into SQLite, then returns the quote.

## Tests

```text
tests/test_services.py
```

Tests the pure business logic:

- CSV parsing;
- holdings after buy/sell;
- portfolio summary;
- DCA recommendation.

```text
tests/test_repositories.py
```

Tests the SQLAlchemy repository layer with an in-memory SQLite database.

It is skipped if SQLAlchemy is not installed. Inside the project `.venv`, it should run.

## Current Data Flows

CSV upload:

```text
Frontend or API client
  -> POST /api/transactions/upload?portfolio_id=default
    -> parse_transactions_csv()
      -> list[Transaction]
        -> import_transactions()
          -> ensure_portfolio()
          -> ensure_account()
          -> transaction_fingerprint()
          -> skip duplicates already in SQLite
          -> ImportSessionRecord
          -> SQLite transactions table
```

Upload responses include an import summary:

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

Portfolio summary:

```text
GET /api/portfolio?portfolio_id=default
  -> list_transactions()
    -> SQLite rows converted to Transaction dataclasses
  -> get_market_prices()
    -> latest prices from SQLite
  -> summarize_portfolio()
    -> PortfolioSummary
```

Manual price update:

```text
PUT /api/market/prices
  -> upsert_market_price()
    -> SQLite market_prices table
```

DCA recommendation:

```text
POST /api/dca/recommendation
  -> calculate_enhanced_dca()
    -> DcaRecommendation
```

## Why This Architecture Works

The backend has a useful separation:

```text
main.py
```

handles HTTP.

```text
repositories.py
```

handles persistence.

```text
services/
```

handles business logic.

```text
domain.py
```

defines the core financial concepts.

That means SQLite can later become PostgreSQL without rewriting portfolio math. The DCA formula can also evolve without touching database code.

## What Is Still Missing

The current architecture is a good foundation, but still early.

Important next pieces:

- import preview before saving;
- a historical price table, not only latest prices;
- DCA settings stored in the database;
- deeper frontend API integration, especially DCA settings and historical charts;
- database migrations with Alembic;
- stronger API response schemas;
- authentication later, once the local portfolio workflow feels right.

The best next technical step is probably to connect the frontend to the backend API, now that CSV imports are safer to repeat.
