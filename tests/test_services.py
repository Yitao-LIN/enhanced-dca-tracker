"""@file
@brief Service-layer tests for CSV parsing, portfolio math, market data, and DCA logic.
"""

import io
import unittest
import zipfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from app.domain import Transaction, TransactionType
from app.services.csv_import import parse_transactions_csv, preview_transactions_csv
from app.services.dca import build_dca_allocation_suggestions, calculate_enhanced_dca, calculate_normal_dca
from app.services.market_data import normalize_yfinance_history, normalize_yfinance_search_quotes
from app.services.portfolio import build_holdings, summarize_portfolio
from app.services.portfolio_analytics import AllocationTargetInput, build_portfolio_analytics
from app.services.portfolio_history import build_portfolio_history
from app.services.portfolio_intraday import build_portfolio_intraday_history


FIXTURES_DIR = Path(__file__).parent / "fixtures"


class CsvImportTests(unittest.TestCase):
    def test_parse_fortuneo_style_csv(self):
        csv_text = """Date operation;Operation;Code valeur;Quantite;Prix unitaire;Frais;Devise
15/01/2026;Achat;CW8.PA;3;470,50;1,95;EUR
20/02/2026;Vente;CW8.PA;1;490,00;1,95;EUR
"""
        transactions = parse_transactions_csv(csv_text)

        self.assertEqual(len(transactions), 2)
        self.assertEqual(transactions[0].ticker, "CW8.PA")
        self.assertEqual(transactions[0].quantity, Decimal("3"))
        self.assertEqual(transactions[0].price, Decimal("470.50"))
        self.assertEqual(transactions[1].transaction_type.value, "sell")

    def test_parse_fortuneo_bourse_zip_with_enriched_security_code(self):
        csv_text = (
            "libellé;Opération;Place;Date;Qté;Prix d'éxé;Montant brut;"
            "Courtage/Prélèvement;Montant net;Devise;Code valeur;\n"
            "AMUNDI MSCI WORLD;Achat comptant;Paris;15/01/2026;3;470,50;"
            "1411,50;1,95;-1413,45;EUR;CW8.PA;\n"
        )
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, mode="w") as zip_file:
            zip_file.writestr("HistoriqueOperationsBourse_2026.csv", csv_text.encode("iso-8859-1"))

        transactions = parse_transactions_csv(archive.getvalue())

        self.assertEqual(len(transactions), 1)
        self.assertEqual(transactions[0].ticker, "CW8.PA")
        self.assertEqual(transactions[0].transaction_type, TransactionType.BUY)
        self.assertEqual(transactions[0].quantity, Decimal("3"))
        self.assertEqual(transactions[0].price, Decimal("470.50"))
        self.assertEqual(transactions[0].fees, Decimal("1.95"))
        self.assertEqual(transactions[0].description, "AMUNDI MSCI WORLD")

    def test_preview_fortuneo_bourse_without_security_code_reports_mapping_error(self):
        csv_text = (
            "libellé;Opération;Place;Date;Qté;Prix d'éxé;Montant brut;"
            "Courtage/Prélèvement;Montant net;Devise;\n"
            "AMUNDI MSCI WORLD;Achat comptant;Paris;15/01/2026;3;470,50;"
            "1411,50;1,95;-1413,45;EUR;\n"
        )

        rows = preview_transactions_csv(csv_text.encode("iso-8859-1"))

        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0].transaction)
        self.assertEqual(rows[0].security_label, "AMUNDI MSCI WORLD")
        self.assertIn("AMUNDI MSCI WORLD", rows[0].error)
        self.assertIn("needs a ticker mapping", rows[0].error)

    def test_preview_fortuneo_bourse_zip_reports_mapping_row(self):
        rows = preview_transactions_csv((FIXTURES_DIR / "fortuneo_bourse_mapping.zip").read_bytes())

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].security_label, "AMUNDI PEA S&P 500 UCITS ETF ACC")
        self.assertTrue(all(row.transaction is None for row in rows))

        transactions = parse_transactions_csv(
            (FIXTURES_DIR / "fortuneo_bourse_mapping.zip").read_bytes(),
            security_mappings={
                "amundi pea s p 500 ucits etf acc": "PSP5.PA",
            },
        )

        self.assertEqual([transaction.ticker for transaction in transactions], ["PSP5.PA"])
        self.assertEqual([transaction.transaction_type for transaction in transactions], [TransactionType.BUY])

    def test_parse_fortuneo_bourse_with_security_mapping(self):
        csv_text = (
            "libell\u00e9;Op\u00e9ration;Place;Date;Qt\u00e9;Prix d'\u00e9x\u00e9;Montant brut;"
            "Courtage/Pr\u00e9l\u00e8vement;Montant net;Devise;\n"
            "AMUNDI MSCI WORLD;Achat comptant;Paris;15/01/2026;3;470,50;"
            "1411,50;1,95;-1413,45;EUR;\n"
        )

        transactions = parse_transactions_csv(csv_text, security_mappings={"amundi msci world": "cw8.pa"})

        self.assertEqual(len(transactions), 1)
        self.assertEqual(transactions[0].ticker, "CW8.PA")
        self.assertEqual(transactions[0].description, "AMUNDI MSCI WORLD")

    def test_existing_security_code_wins_over_mapping(self):
        csv_text = """Date operation;Operation;Code valeur;Quantite;Prix unitaire;Frais;Devise;Libelle
15/01/2026;Achat;EWLD.PA;3;32,50;1,95;EUR;AMUNDI MSCI WORLD
"""

        transactions = parse_transactions_csv(csv_text, security_mappings={"amundi msci world": "CW8.PA"})

        self.assertEqual(transactions[0].ticker, "EWLD.PA")

    def test_fortuneo_account_export_is_rejected_clearly(self):
        csv_text = (
            "Date op\u00e9ration;Date valeur;libell\u00e9;D\u00e9bit;Cr\u00e9dit;\n"
            "13/12/2019;13/12/2019;CARTE 12/12 EXAMPLE;-6,40;\n"
        )

        rows = preview_transactions_csv(csv_text.encode("iso-8859-1"))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].row_number, 1)
        self.assertIsNone(rows[0].transaction)
        self.assertIn("Fortuneo bank-account export", rows[0].error)
        self.assertIn("bourse investment export", rows[0].error)

        with self.assertRaisesRegex(ValueError, "Fortuneo bank-account export"):
            parse_transactions_csv(csv_text.encode("iso-8859-1"))

    def test_parse_zip_without_fortuneo_csv_fails_clearly(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, mode="w") as zip_file:
            zip_file.writestr("notes.txt", "not a Fortuneo export")

        with self.assertRaisesRegex(ValueError, "HistoriqueOperations CSV"):
            parse_transactions_csv(archive.getvalue())


class PortfolioTests(unittest.TestCase):
    def test_build_holdings_reduces_cost_basis_on_sell(self):
        transactions = parse_transactions_csv(
            """Date operation;Operation;Code valeur;Quantite;Prix unitaire;Frais;Devise;Libelle
15/01/2026;Achat;CW8.PA;3;100,00;3,00;EUR;AMUNDI MSCI WORLD
20/02/2026;Vente;CW8.PA;1;120,00;1,00;EUR;AMUNDI MSCI WORLD
"""
        )

        holdings = build_holdings(transactions)

        self.assertEqual(len(holdings), 1)
        self.assertEqual(holdings[0].quantity, Decimal("2"))
        self.assertEqual(holdings[0].average_cost, Decimal("101.00"))
        self.assertEqual(holdings[0].name, "AMUNDI MSCI WORLD")

    def test_summarize_portfolio_prices_holdings(self):
        transactions = parse_transactions_csv(
            """Date operation;Operation;Code valeur;Quantite;Prix unitaire;Frais;Devise
15/01/2026;Achat;CW8.PA;2;100,00;0;EUR
"""
        )

        summary = summarize_portfolio(transactions, {"CW8.PA": Decimal("125")})

        self.assertEqual(summary.total_value, Decimal("250.00"))
        self.assertEqual(summary.total_invested, Decimal("200.00"))
        self.assertEqual(summary.total_gain_percent, Decimal("25.00"))

    def test_summarize_empty_portfolio_returns_zeroes(self):
        summary = summarize_portfolio([], {})

        self.assertEqual(summary.total_value, Decimal("0.00"))
        self.assertEqual(summary.total_invested, Decimal("0.00"))
        self.assertEqual(summary.total_gain, Decimal("0.00"))
        self.assertEqual(summary.total_gain_percent, Decimal("0"))
        self.assertEqual(summary.cash_flow, Decimal("0.00"))
        self.assertEqual(summary.holdings, [])

    def test_build_portfolio_history_with_normalized_benchmarks(self):
        transactions = [
            Transaction(
                transaction_date=date(2026, 1, 15),
                ticker="ABC",
                transaction_type=TransactionType.BUY,
                quantity=Decimal("2"),
                price=Decimal("100"),
            )
        ]

        history = build_portfolio_history(
            transactions,
            prices_by_symbol={"ABC": {date(2026, 1, 15): Decimal("110"), date(2026, 1, 16): Decimal("120")}},
            benchmarks_by_symbol={
                "^GSPC": {date(2026, 1, 15): Decimal("4000"), date(2026, 1, 16): Decimal("4040")},
                "^NDX": {date(2026, 1, 15): Decimal("18000"), date(2026, 1, 16): Decimal("18180")},
            },
        )

        self.assertEqual([point.price_date for point in history], [date(2026, 1, 15), date(2026, 1, 16)])
        self.assertEqual(history[0].market_value, Decimal("220.00"))
        self.assertEqual(history[1].market_value, Decimal("240.00"))
        self.assertEqual(history[1].benchmarks["^GSPC"], Decimal("222.20"))
        self.assertEqual(history[1].benchmarks["^NDX"], Decimal("222.20"))

    def test_portfolio_history_starts_at_first_transaction(self):
        transactions = [
            Transaction(
                transaction_date=date(2026, 6, 4),
                ticker="PSP5.PA",
                transaction_type=TransactionType.BUY,
                quantity=Decimal("2"),
                price=Decimal("55.62"),
            )
        ]

        history = build_portfolio_history(
            transactions,
            prices_by_symbol={"PSP5.PA": {date(2026, 6, 4): Decimal("55.62"), date(2026, 6, 5): Decimal("56")}},
            benchmarks_by_symbol={"^GSPC": {date(2025, 12, 31): Decimal("6000"), date(2026, 6, 4): Decimal("6500")}},
        )

        self.assertEqual([point.price_date for point in history], [date(2026, 6, 4), date(2026, 6, 5)])

    def test_portfolio_history_carries_forward_prior_prices_for_newer_transaction(self):
        transactions = [
            Transaction(
                transaction_date=date(2026, 6, 28),
                ticker="PSP5.PA",
                transaction_type=TransactionType.BUY,
                quantity=Decimal("5"),
                price=Decimal("57.20"),
            )
        ]

        history = build_portfolio_history(
            transactions,
            prices_by_symbol={"PSP5.PA": {date(2026, 6, 26): Decimal("56.77")}},
            benchmarks_by_symbol={
                "^GSPC": {date(2026, 6, 26): Decimal("7354.02")},
                "^NDX": {date(2026, 6, 26): Decimal("29118.24")},
            },
            start_date=date(2026, 5, 29),
            end_date=date(2026, 6, 28),
        )

        self.assertEqual([point.price_date for point in history], [date(2026, 6, 28)])
        self.assertEqual(history[0].market_value, Decimal("283.85"))
        self.assertEqual(history[0].benchmarks["^GSPC"], Decimal("283.85"))
        self.assertEqual(history[0].benchmarks["^NDX"], Decimal("283.85"))

    def test_build_portfolio_intraday_history_with_normalized_benchmarks(self):
        transactions = [
            Transaction(
                transaction_date=date(2026, 6, 9),
                ticker="PSP5.PA",
                transaction_type=TransactionType.BUY,
                quantity=Decimal("2"),
                price=Decimal("55"),
            )
        ]
        first_tick = datetime(2026, 6, 9, 9, 0)
        second_tick = datetime(2026, 6, 9, 9, 30)

        history = build_portfolio_intraday_history(
            transactions,
            prices_by_symbol={"PSP5.PA": {first_tick: Decimal("56"), second_tick: Decimal("57")}},
            benchmarks_by_symbol={"^GSPC": {first_tick: Decimal("6000"), second_tick: Decimal("6060")}},
            start_at=datetime(2026, 6, 8, 9, 0),
            end_at=second_tick,
        )

        self.assertEqual([point.timestamp for point in history], [first_tick, second_tick])
        self.assertEqual(history[0].invested_amount, Decimal("110.00"))
        self.assertEqual(history[0].market_value, Decimal("112.00"))
        self.assertEqual(history[1].market_value, Decimal("114.00"))
        self.assertEqual(history[1].benchmarks["^GSPC"], Decimal("113.12"))

    def test_portfolio_intraday_history_carries_forward_prior_ticks(self):
        transactions = [
            Transaction(
                transaction_date=date(2026, 6, 28),
                ticker="PSP5.PA",
                transaction_type=TransactionType.BUY,
                quantity=Decimal("5"),
                price=Decimal("57.20"),
            )
        ]
        prior_tick = datetime(2026, 6, 27, 16, 0)
        visible_tick = datetime(2026, 6, 28, 9, 0)

        history = build_portfolio_intraday_history(
            transactions,
            prices_by_symbol={"PSP5.PA": {prior_tick: Decimal("56.77")}},
            benchmarks_by_symbol={"^GSPC": {visible_tick: Decimal("7354.02")}},
            start_at=visible_tick,
            end_at=visible_tick,
        )

        self.assertEqual([point.timestamp for point in history], [visible_tick])
        self.assertEqual(history[0].market_value, Decimal("283.85"))
        self.assertEqual(history[0].benchmarks["^GSPC"], Decimal("283.85"))


class PortfolioAnalyticsTests(unittest.TestCase):
    def test_allocation_drift_with_partial_and_target_only_allocations(self):
        transactions = [
            Transaction(date(2026, 1, 1), "AAA", TransactionType.BUY, Decimal("2"), Decimal("100")),
            Transaction(date(2026, 1, 1), "BBB", TransactionType.BUY, Decimal("1"), Decimal("100")),
        ]
        summary = summarize_portfolio(transactions, {"AAA": Decimal("120"), "BBB": Decimal("80")})

        analytics = build_portfolio_analytics(
            transactions,
            summary=summary,
            allocation_targets=[
                AllocationTargetInput("AAA", Decimal("50")),
                AllocationTargetInput("BBB", Decimal("30")),
                AllocationTargetInput("CCC", Decimal("20")),
            ],
            history_points=[],
            benchmark_names={},
        )

        rows = {row.ticker: row for row in analytics.allocation_drift}
        self.assertEqual(analytics.total_target_percent, Decimal("100.00"))
        self.assertEqual(rows["AAA"].action, "trim")
        self.assertEqual(rows["AAA"].current_percent, Decimal("75.00"))
        self.assertEqual(rows["AAA"].target_value, Decimal("160.00"))
        self.assertEqual(rows["AAA"].trim_value, Decimal("80.00"))
        self.assertEqual(rows["BBB"].action, "buy")
        self.assertEqual(rows["BBB"].buy_value, Decimal("16.00"))
        self.assertEqual(rows["CCC"].current_value, Decimal("0.00"))
        self.assertEqual(rows["CCC"].buy_value, Decimal("64.00"))

    def test_allocation_drift_without_targets_keeps_current_allocation_read_only(self):
        transactions = [Transaction(date(2026, 1, 1), "AAA", TransactionType.BUY, Decimal("2"), Decimal("100"))]
        summary = summarize_portfolio(transactions, {"AAA": Decimal("120")})

        analytics = build_portfolio_analytics(
            transactions,
            summary=summary,
            allocation_targets=[],
            history_points=[],
            benchmark_names={},
        )

        self.assertEqual(analytics.unassigned_target_percent, Decimal("100.00"))
        self.assertIsNone(analytics.allocation_drift[0].target_percent)
        self.assertEqual(analytics.allocation_drift[0].action, "unassigned")

    def test_monthly_activity_groups_contributions_proceeds_dividends_and_fees(self):
        transactions = [
            Transaction(date(2026, 1, 1), "AAA", TransactionType.BUY, Decimal("2"), Decimal("100"), fees=Decimal("1")),
            Transaction(date(2026, 1, 5), "AAA", TransactionType.SELL, Decimal("1"), Decimal("120"), fees=Decimal("2")),
            Transaction(date(2026, 2, 1), "AAA", TransactionType.DIVIDEND, Decimal("1"), Decimal("5")),
            Transaction(date(2026, 2, 3), "CASH", TransactionType.FEE, Decimal("0"), Decimal("0"), fees=Decimal("3")),
        ]

        analytics = build_portfolio_analytics(
            transactions,
            summary=summarize_portfolio(transactions, {"AAA": Decimal("120")}),
            allocation_targets=[],
            history_points=[],
            benchmark_names={},
        )

        january, february = analytics.monthly_activity
        self.assertEqual(january.month, "2026-01")
        self.assertEqual(january.buy_contributions, Decimal("201.00"))
        self.assertEqual(january.sell_proceeds, Decimal("118.00"))
        self.assertEqual(january.fees, Decimal("3.00"))
        self.assertEqual(january.net_cash_flow, Decimal("-83.00"))
        self.assertEqual(february.dividends, Decimal("5.00"))
        self.assertEqual(february.fees, Decimal("3.00"))
        self.assertEqual(february.net_cash_flow, Decimal("2.00"))

    def test_benchmark_comparison_handles_complete_missing_and_zero_start_history(self):
        transactions = [Transaction(date(2026, 1, 1), "AAA", TransactionType.BUY, Decimal("1"), Decimal("100"))]
        history = build_portfolio_history(
            transactions,
            prices_by_symbol={"AAA": {date(2026, 1, 1): Decimal("100"), date(2026, 1, 2): Decimal("110")}},
            benchmarks_by_symbol={"^GSPC": {date(2026, 1, 1): Decimal("1000"), date(2026, 1, 2): Decimal("1100")}},
        )

        analytics = build_portfolio_analytics(
            transactions,
            summary=summarize_portfolio(transactions, {"AAA": Decimal("110")}),
            allocation_targets=[],
            history_points=history,
            benchmark_names={"^GSPC": "S&P 500", "^NDX": "Nasdaq 100"},
        )

        self.assertEqual(len(analytics.benchmark_comparison), 1)
        self.assertEqual(analytics.benchmark_comparison[0].portfolio_return_percent, Decimal("10.00"))
        self.assertEqual(analytics.benchmark_comparison[0].benchmark_return_percent, Decimal("10.00"))
        self.assertEqual(analytics.benchmark_comparison[0].relative_return_percent, Decimal("0.00"))

        zero_start = type(
            "Point",
            (),
            {"market_value": Decimal("0"), "benchmarks": {"^GSPC": Decimal("100")}, "price_date": date(2026, 1, 1)},
        )()
        zero_end = type(
            "Point",
            (),
            {"market_value": Decimal("100"), "benchmarks": {"^GSPC": Decimal("110")}, "price_date": date(2026, 1, 2)},
        )()
        empty = build_portfolio_analytics(
            transactions,
            summary=summarize_portfolio(transactions, {"AAA": Decimal("110")}),
            allocation_targets=[],
            history_points=[zero_start, zero_end],
            benchmark_names={"^GSPC": "S&P 500"},
        )
        self.assertEqual(empty.benchmark_comparison, [])


class DcaTests(unittest.TestCase):
    def test_normal_dca_keeps_base_amount(self):
        recommendation = calculate_normal_dca(base_amount=Decimal("850"))

        self.assertEqual(recommendation.model_type, "normal")
        self.assertEqual(recommendation.adjusted_amount, Decimal("850.00"))
        self.assertEqual(recommendation.multiplier, Decimal("1.0"))

    def test_enhanced_dca_increases_on_market_drawdown(self):
        recommendation = calculate_enhanced_dca(
            base_amount=Decimal("1000"),
            market_change_percent=Decimal("-4"),
            volatility_index=Decimal("18"),
        )

        self.assertEqual(recommendation.adjusted_amount, Decimal("1300.00"))
        self.assertEqual(recommendation.multiplier, Decimal("1.3"))

    def test_enhanced_dca_applies_settings_multiplier_bounds(self):
        recommendation = calculate_enhanced_dca(
            base_amount=Decimal("1000"),
            market_change_percent=Decimal("-6"),
            volatility_index=Decimal("32"),
            max_multiplier=Decimal("1.5"),
        )

        self.assertEqual(recommendation.adjusted_amount, Decimal("1500.00"))
        self.assertEqual(recommendation.multiplier, Decimal("1.5"))

    def test_dca_allocation_split_uses_underweight_buy_values(self):
        rows = [
            SimpleNamespace(ticker="CW8.PA", target_percent=Decimal("70"), current_percent=Decimal("60"), buy_value=Decimal("300")),
            SimpleNamespace(ticker="EWLD.PA", target_percent=Decimal("20"), current_percent=Decimal("15"), buy_value=Decimal("100")),
            SimpleNamespace(ticker="VEUR.AS", target_percent=Decimal("10"), current_percent=Decimal("25"), buy_value=Decimal("0")),
        ]

        suggestions = build_dca_allocation_suggestions(Decimal("800"), rows)

        self.assertEqual([(row.ticker, row.suggested_amount) for row in suggestions], [("CW8.PA", Decimal("600.00")), ("EWLD.PA", Decimal("200.00"))])
        self.assertEqual({row.reason for row in suggestions}, {"underweight target allocation"})

    def test_dca_allocation_split_falls_back_to_target_percent(self):
        rows = [
            SimpleNamespace(ticker="CW8.PA", target_percent=Decimal("70"), current_percent=Decimal("75"), buy_value=Decimal("0")),
            SimpleNamespace(ticker="EWLD.PA", target_percent=Decimal("30"), current_percent=Decimal("25"), buy_value=Decimal("0")),
        ]

        suggestions = build_dca_allocation_suggestions(Decimal("1000"), rows)

        self.assertEqual([(row.ticker, row.suggested_amount) for row in suggestions], [("CW8.PA", Decimal("700.00")), ("EWLD.PA", Decimal("300.00"))])
        self.assertEqual({row.reason for row in suggestions}, {"target allocation percent"})

    def test_dca_allocation_split_returns_empty_without_targets(self):
        rows = [
            SimpleNamespace(ticker="CW8.PA", target_percent=None, current_percent=Decimal("100"), buy_value=Decimal("0")),
        ]

        self.assertEqual(build_dca_allocation_suggestions(Decimal("1000"), rows), [])


class MarketDataTests(unittest.TestCase):
    def test_normalize_yfinance_search_quotes(self):
        quotes = [
            {
                "symbol": "cw8.pa",
                "longname": "Amundi MSCI World UCITS ETF",
                "exchange": "PAR",
                "quoteType": "ETF",
                "currency": "eur",
            },
            {"symbol": "CW8.PA", "shortname": "Duplicate"},
            {"shortname": "No symbol"},
        ]

        results = normalize_yfinance_search_quotes(quotes)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].symbol, "CW8.PA")
        self.assertEqual(results[0].name, "Amundi MSCI World UCITS ETF")
        self.assertEqual(results[0].currency, "EUR")

    def test_normalize_yfinance_history(self):
        frame = pd.DataFrame(
            {
                "Open": [Decimal("4000")],
                "High": [Decimal("4050")],
                "Low": [Decimal("3990")],
                "Close": [Decimal("4040")],
                "Adj Close": [Decimal("4040")],
                "Volume": [123456],
            },
            index=pd.to_datetime(["2026-01-16"]),
        )

        points = normalize_yfinance_history("^gspc", frame, currency="usd", source="yfinance")

        self.assertEqual(len(points), 1)
        self.assertEqual(points[0].symbol, "^GSPC")
        self.assertEqual(points[0].price_date, date(2026, 1, 16))
        self.assertEqual(points[0].close, Decimal("4040"))
        self.assertEqual(points[0].volume, 123456)
        self.assertEqual(points[0].currency, "USD")


if __name__ == "__main__":
    unittest.main()
