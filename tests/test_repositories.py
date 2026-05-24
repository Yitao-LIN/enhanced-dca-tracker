import importlib.util
import unittest
from datetime import date
from decimal import Decimal

SQLALCHEMY_AVAILABLE = importlib.util.find_spec("sqlalchemy") is not None


@unittest.skipUnless(SQLALCHEMY_AVAILABLE, "SQLAlchemy is not installed")
class RepositoryTests(unittest.TestCase):
    def setUp(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.database import Base
        import app.models  # noqa: F401

        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def test_persists_transactions_and_prices(self):
        from app.domain import Transaction, TransactionType
        from app.repositories import add_transaction, get_market_prices, list_accounts, list_transactions, upsert_market_price
        from app.services.portfolio import summarize_portfolio

        with self.Session() as db:
            add_transaction(
                db,
                Transaction(
                    transaction_date=date(2026, 1, 15),
                    ticker="CW8.PA",
                    transaction_type=TransactionType.BUY,
                    quantity=Decimal("2"),
                    price=Decimal("100"),
                    fees=Decimal("1.50"),
                    account="PEA",
                ),
            )
            upsert_market_price(db, symbol="cw8.pa", close=Decimal("125"), source="manual")

            transactions = list_transactions(db)
            accounts = list_accounts(db)
            prices = get_market_prices(db)
            summary = summarize_portfolio(transactions, prices)

        self.assertEqual(len(transactions), 1)
        self.assertEqual(transactions[0].ticker, "CW8.PA")
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0].name, "PEA")
        self.assertEqual(prices["CW8.PA"], Decimal("125.00000000"))
        self.assertEqual(summary.total_value, Decimal("250.00"))
        self.assertEqual(summary.total_gain, Decimal("48.50"))

    def test_keeps_portfolios_isolated(self):
        from app.domain import Transaction, TransactionType
        from app.repositories import add_transaction, create_portfolio, list_portfolios, list_transactions

        with self.Session() as db:
            create_portfolio(db, name="Long Term", slug="long-term")
            add_transaction(
                db,
                Transaction(
                    transaction_date=date(2026, 1, 15),
                    ticker="CW8.PA",
                    transaction_type=TransactionType.BUY,
                    quantity=Decimal("1"),
                    price=Decimal("100"),
                    account="PEA",
                ),
                portfolio_id="long-term",
            )
            add_transaction(
                db,
                Transaction(
                    transaction_date=date(2026, 1, 15),
                    ticker="EWLD.PA",
                    transaction_type=TransactionType.BUY,
                    quantity=Decimal("1"),
                    price=Decimal("30"),
                    account="CTO",
                ),
            )

            portfolios = list_portfolios(db)
            long_term = list_transactions(db, portfolio_id="long-term")
            default = list_transactions(db)

        self.assertEqual({portfolio.slug for portfolio in portfolios}, {"default", "long-term"})
        self.assertEqual([transaction.ticker for transaction in long_term], ["CW8.PA"])
        self.assertEqual([transaction.ticker for transaction in default], ["EWLD.PA"])

    def test_import_skips_duplicate_transactions(self):
        from app.domain import Transaction, TransactionType
        from app.repositories import import_transactions, list_transactions

        transaction = Transaction(
            transaction_date=date(2026, 1, 15),
            ticker="CW8.PA",
            transaction_type=TransactionType.BUY,
            quantity=Decimal("2"),
            price=Decimal("100"),
            fees=Decimal("1.50"),
            account="PEA",
        )

        with self.Session() as db:
            first_import = import_transactions(db, [transaction], filename="fortuneo.csv", file_content="first")
            second_import = import_transactions(db, [transaction], filename="fortuneo.csv", file_content="first")
            transactions = list_transactions(db)

        self.assertEqual(first_import.imported_count, 1)
        self.assertEqual(first_import.duplicate_count, 0)
        self.assertEqual(second_import.imported_count, 0)
        self.assertEqual(second_import.duplicate_count, 1)
        self.assertEqual(second_import.total_count, 1)
        self.assertEqual(len(transactions), 1)

    def test_import_allows_same_security_with_different_quantity(self):
        from app.domain import Transaction, TransactionType
        from app.repositories import import_transactions, list_transactions

        base = Transaction(
            transaction_date=date(2026, 1, 15),
            ticker="CW8.PA",
            transaction_type=TransactionType.BUY,
            quantity=Decimal("2"),
            price=Decimal("100"),
            account="PEA",
        )
        different_quantity = Transaction(
            transaction_date=date(2026, 1, 15),
            ticker="CW8.PA",
            transaction_type=TransactionType.BUY,
            quantity=Decimal("3"),
            price=Decimal("100"),
            account="PEA",
        )

        with self.Session() as db:
            summary = import_transactions(db, [base, different_quantity], filename="fortuneo.csv")
            transactions = list_transactions(db)

        self.assertEqual(summary.imported_count, 2)
        self.assertEqual(summary.duplicate_count, 0)
        self.assertEqual([transaction.quantity for transaction in transactions], [Decimal("2.00000000"), Decimal("3.00000000")])

    def test_market_price_history_upserts_and_filters_ranges(self):
        from app.repositories import (
            MarketPriceHistoryPoint,
            list_market_price_history,
            upsert_market_price_history_many,
        )

        with self.Session() as db:
            updated = upsert_market_price_history_many(
                db,
                [
                    MarketPriceHistoryPoint(
                        symbol="^gspc",
                        price_date=date(2026, 1, 15),
                        close=Decimal("4000"),
                        currency="USD",
                        source="yfinance",
                    ),
                    MarketPriceHistoryPoint(
                        symbol="^GSPC",
                        price_date=date(2026, 1, 16),
                        close=Decimal("4040"),
                        currency="USD",
                        source="yfinance",
                    ),
                    MarketPriceHistoryPoint(
                        symbol="^NDX",
                        price_date=date(2026, 1, 16),
                        close=Decimal("18180"),
                        currency="USD",
                        source="yfinance",
                    ),
                ],
            )
            upsert_market_price_history_many(
                db,
                [
                    MarketPriceHistoryPoint(
                        symbol="^GSPC",
                        price_date=date(2026, 1, 16),
                        close=Decimal("4050"),
                        currency="USD",
                        source="yfinance",
                    )
                ],
            )

            benchmark_history = list_market_price_history(
                db,
                symbol="^GSPC",
                start_date=date(2026, 1, 16),
                end_date=date(2026, 1, 16),
                source="yfinance",
            )
            full_history = list_market_price_history(db, symbol="^GSPC")

        self.assertEqual(updated, 3)
        self.assertEqual(len(benchmark_history), 1)
        self.assertEqual(benchmark_history[0].close, Decimal("4050.00000000"))
        self.assertEqual([record.price_date for record in full_history], [date(2026, 1, 15), date(2026, 1, 16)])

    def test_dca_settings_are_persisted_per_portfolio(self):
        from app.repositories import DcaSettings, get_dca_settings, upsert_dca_settings

        with self.Session() as db:
            default_settings = get_dca_settings(db)
            default_benchmark = default_settings.preferred_benchmark
            saved = upsert_dca_settings(
                db,
                DcaSettings(
                    portfolio_id="default",
                    base_amount=Decimal("750"),
                    preferred_benchmark="^ndx",
                    min_multiplier=Decimal("0.8"),
                    max_multiplier=Decimal("1.4"),
                    contribution_frequency="weekly",
                ),
            )
            loaded = get_dca_settings(db)

        self.assertEqual(default_benchmark, "^GSPC")
        self.assertEqual(saved.preferred_benchmark, "^NDX")
        self.assertEqual(loaded.base_amount, Decimal("750.00000000"))
        self.assertEqual(loaded.contribution_frequency, "weekly")


if __name__ == "__main__":
    unittest.main()
