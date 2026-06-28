"""@file
@brief Repository tests for persistence, duplicate detection, and scoped settings.
"""

import importlib.util
import unittest
from datetime import date, datetime
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

    def test_security_mappings_are_persisted_per_portfolio(self):
        from app.repositories import (
            SecurityMapping,
            create_portfolio,
            delete_security_mapping,
            get_security_mapping_symbols,
            list_security_mappings,
            upsert_security_mapping,
        )

        with self.Session() as db:
            create_portfolio(db, name="Long Term", slug="long-term")
            default_record = upsert_security_mapping(
                db,
                SecurityMapping(
                    security_label="AMUNDI MSCI WORLD",
                    ticker="cw8.pa",
                    provider="yfinance",
                    provider_name="Amundi MSCI World UCITS ETF",
                    provider_exchange="PAR",
                    provider_quote_type="ETF",
                    provider_currency="eur",
                ),
            )
            long_term_record = upsert_security_mapping(
                db,
                SecurityMapping(security_label="AMUNDI MSCI WORLD", ticker="WRD.PA"),
                portfolio_id="long-term",
            )
            default_mappings = get_security_mapping_symbols(db)
            long_term_mappings = get_security_mapping_symbols(db, portfolio_id="long-term")
            listed = list_security_mappings(db)
            deleted = delete_security_mapping(db, "AMUNDI MSCI WORLD")
            default_after_delete = get_security_mapping_symbols(db)
            long_term_after_delete = get_security_mapping_symbols(db, portfolio_id="long-term")

        self.assertEqual(default_record.ticker, "CW8.PA")
        self.assertEqual(default_record.provider, "yfinance")
        self.assertEqual(default_record.provider_currency, "EUR")
        self.assertEqual(long_term_record.ticker, "WRD.PA")
        self.assertEqual(default_mappings, {"amundi msci world": "CW8.PA"})
        self.assertEqual(long_term_mappings, {"amundi msci world": "WRD.PA"})
        self.assertEqual([record.display_label for record in listed], ["AMUNDI MSCI WORLD"])
        self.assertTrue(deleted)
        self.assertEqual(default_after_delete, {})
        self.assertEqual(long_term_after_delete, {"amundi msci world": "WRD.PA"})

    def test_hidden_securities_are_persisted_per_portfolio(self):
        from app.repositories import (
            create_portfolio,
            delete_hidden_security,
            get_hidden_security_symbols,
            list_hidden_securities,
            upsert_hidden_security,
        )

        with self.Session() as db:
            create_portfolio(db, name="Long Term", slug="long-term")
            default_record = upsert_hidden_security(db, "cw8.pa")
            duplicate_record = upsert_hidden_security(db, "CW8.PA")
            long_term_record = upsert_hidden_security(db, "wrd.pa", portfolio_id="long-term")
            default_hidden = get_hidden_security_symbols(db)
            long_term_hidden = get_hidden_security_symbols(db, portfolio_id="long-term")
            listed = list_hidden_securities(db)
            deleted = delete_hidden_security(db, "cw8.pa")
            default_after_delete = get_hidden_security_symbols(db)
            long_term_after_delete = get_hidden_security_symbols(db, portfolio_id="long-term")

        self.assertEqual(default_record.id, duplicate_record.id)
        self.assertEqual(default_record.ticker, "CW8.PA")
        self.assertEqual(long_term_record.ticker, "WRD.PA")
        self.assertEqual(default_hidden, {"CW8.PA"})
        self.assertEqual(long_term_hidden, {"WRD.PA"})
        self.assertEqual([record.ticker for record in listed], ["CW8.PA"])
        self.assertTrue(deleted)
        self.assertEqual(default_after_delete, set())
        self.assertEqual(long_term_after_delete, {"WRD.PA"})

    def test_allocation_targets_replace_and_validate_per_portfolio(self):
        from app.repositories import AllocationTarget, create_portfolio, list_allocation_targets, replace_allocation_targets

        with self.Session() as db:
            create_portfolio(db, name="Long Term", slug="long-term")
            default_targets = replace_allocation_targets(
                db,
                [
                    AllocationTarget("cw8.pa", Decimal("70")),
                    AllocationTarget("ewld.pa", Decimal("10")),
                ],
            )
            replace_allocation_targets(
                db,
                [AllocationTarget("wrd.pa", Decimal("60"))],
                portfolio_id="long-term",
            )
            replaced = replace_allocation_targets(db, [AllocationTarget("VEUR.AS", Decimal("20"))])
            default_after_replace = list_allocation_targets(db)
            long_term_targets = list_allocation_targets(db, portfolio_id="long-term")

            with self.assertRaisesRegex(ValueError, "Ticker is required"):
                replace_allocation_targets(db, [AllocationTarget("", Decimal("10"))])
            with self.assertRaisesRegex(ValueError, "between 0 and 100"):
                replace_allocation_targets(db, [AllocationTarget("CW8.PA", Decimal("-1"))])
            with self.assertRaisesRegex(ValueError, "less than or equal to 100"):
                replace_allocation_targets(
                    db,
                    [
                        AllocationTarget("CW8.PA", Decimal("70")),
                        AllocationTarget("EWLD.PA", Decimal("40")),
                    ],
                )

        self.assertEqual([target.ticker for target in default_targets], ["CW8.PA", "EWLD.PA"])
        self.assertEqual([target.ticker for target in replaced], ["VEUR.AS"])
        self.assertEqual([(target.ticker, target.target_percent) for target in default_after_replace], [("VEUR.AS", Decimal("20.0000"))])
        self.assertEqual([(target.ticker, target.target_percent) for target in long_term_targets], [("WRD.PA", Decimal("60.0000"))])

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

    def test_intraday_market_prices_upsert_and_filter_ranges(self):
        from app.repositories import (
            IntradayMarketPricePoint,
            list_intraday_market_prices,
            upsert_intraday_market_prices_many,
        )

        first_tick = datetime(2026, 6, 9, 9, 0)
        second_tick = datetime(2026, 6, 9, 9, 30)
        with self.Session() as db:
            updated = upsert_intraday_market_prices_many(
                db,
                [
                    IntradayMarketPricePoint(
                        symbol="psp5.pa",
                        price_at=first_tick,
                        interval="30M",
                        close=Decimal("55.5"),
                        currency="eur",
                        source="yfinance",
                    ),
                    IntradayMarketPricePoint(
                        symbol="PSP5.PA",
                        price_at=second_tick,
                        interval="30m",
                        close=Decimal("56"),
                        currency="EUR",
                        source="yfinance",
                    ),
                ],
            )
            upsert_intraday_market_prices_many(
                db,
                [
                    IntradayMarketPricePoint(
                        symbol="PSP5.PA",
                        price_at=second_tick,
                        interval="30m",
                        close=Decimal("57"),
                        currency="EUR",
                        source="yfinance",
                    )
                ],
            )

            ranged = list_intraday_market_prices(
                db,
                symbol="PSP5.PA",
                start_at=second_tick,
                end_at=second_tick,
                interval="30m",
                source="yfinance",
            )
            full_history = list_intraday_market_prices(db, symbol="PSP5.PA")

        self.assertEqual(updated, 2)
        self.assertEqual(len(ranged), 1)
        self.assertEqual(ranged[0].close, Decimal("57.00000000"))
        self.assertEqual([record.price_at for record in full_history], [first_tick, second_tick])

    def test_dca_plans_are_persisted_per_portfolio_and_default_is_exclusive(self):
        from app.repositories import DcaPlan, create_dca_plan, delete_dca_plan, list_dca_plans, update_dca_plan

        with self.Session() as db:
            first = create_dca_plan(
                db,
                DcaPlan(
                    portfolio_id="default",
                    name="Monthly normal",
                    model_type="normal",
                    base_amount=Decimal("750"),
                ),
            )
            first_was_initial_default = first.is_default
            second = create_dca_plan(
                db,
                DcaPlan(
                    portfolio_id="default",
                    name="Drawdown boost",
                    model_type="enhanced",
                    base_amount=Decimal("1000"),
                    preferred_benchmark="^ndx",
                    is_default=True,
                ),
            )
            long_term = create_dca_plan(db, DcaPlan(portfolio_id="long-term", name="Monthly normal", model_type="normal"))
            with self.assertRaises(ValueError):
                create_dca_plan(db, DcaPlan(portfolio_id="default", name="Monthly normal", model_type="normal"))

            promoted = update_dca_plan(
                db,
                first.id,
                DcaPlan(name="Monthly normal", model_type="normal", base_amount=Decimal("900"), is_default=True),
            )
            deleted = delete_dca_plan(db, promoted.id)
            default_plans = list_dca_plans(db)
            long_term_plans = list_dca_plans(db, portfolio_id="long-term")

        self.assertTrue(first_was_initial_default)
        self.assertTrue(second.is_default)
        self.assertEqual(long_term.name, "Monthly normal")
        self.assertEqual(promoted.base_amount, Decimal("900.00000000"))
        self.assertTrue(deleted)
        self.assertEqual([(plan.name, plan.is_default) for plan in default_plans], [("Drawdown boost", True)])
        self.assertEqual([plan.name for plan in long_term_plans], ["Monthly normal"])

    def test_legacy_dca_settings_bootstrap_into_default_plan(self):
        from sqlalchemy import text

        from app.repositories import bootstrap_reference_data, ensure_portfolio, list_dca_plans

        with self.Session() as db:
            portfolio = ensure_portfolio(db)
            db.execute(
                text(
                    """
                    CREATE TABLE dca_settings (
                        id INTEGER PRIMARY KEY,
                        portfolio_record_id INTEGER NOT NULL,
                        base_amount NUMERIC(20, 8) NOT NULL,
                        preferred_benchmark VARCHAR(32) NOT NULL,
                        min_multiplier NUMERIC(10, 4) NOT NULL,
                        max_multiplier NUMERIC(10, 4) NOT NULL,
                        contribution_frequency VARCHAR(32) NOT NULL,
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL
                    )
                    """
                )
            )
            db.execute(
                text(
                    """
                    INSERT INTO dca_settings (
                        portfolio_record_id,
                        base_amount,
                        preferred_benchmark,
                        min_multiplier,
                        max_multiplier,
                        contribution_frequency,
                        created_at,
                        updated_at
                    ) VALUES (:portfolio_record_id, '850', '^NDX', '0.8', '1.4', 'weekly', '2026-06-14T00:00:00', '2026-06-14T00:00:00')
                    """
                ),
                {"portfolio_record_id": portfolio.id},
            )
            db.commit()
            bootstrap_reference_data(db)
            plans = list_dca_plans(db)

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0].name, "Default Enhanced DCA")
        self.assertEqual(plans[0].base_amount, Decimal("850.00000000"))
        self.assertTrue(plans[0].is_default)


if __name__ == "__main__":
    unittest.main()
