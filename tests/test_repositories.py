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
        from app.repositories import add_transaction, get_market_prices, list_transactions, upsert_market_price
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
                ),
            )
            upsert_market_price(db, symbol="cw8.pa", close=Decimal("125"), source="manual")

            transactions = list_transactions(db)
            prices = get_market_prices(db)
            summary = summarize_portfolio(transactions, prices)

        self.assertEqual(len(transactions), 1)
        self.assertEqual(transactions[0].ticker, "CW8.PA")
        self.assertEqual(prices["CW8.PA"], Decimal("125.00000000"))
        self.assertEqual(summary.total_value, Decimal("250.00"))
        self.assertEqual(summary.total_gain, Decimal("48.50"))


if __name__ == "__main__":
    unittest.main()
