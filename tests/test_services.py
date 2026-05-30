import io
import unittest
import zipfile
from datetime import date
from decimal import Decimal

import pandas as pd

from app.domain import Transaction, TransactionType
from app.services.csv_import import parse_transactions_csv, preview_transactions_csv
from app.services.dca import calculate_enhanced_dca
from app.services.market_data import normalize_yfinance_history
from app.services.portfolio import build_holdings, summarize_portfolio
from app.services.portfolio_history import build_portfolio_history


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
        self.assertIn("AMUNDI MSCI WORLD", rows[0].error)
        self.assertIn("Code valeur", rows[0].error)

    def test_parse_zip_without_fortuneo_csv_fails_clearly(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, mode="w") as zip_file:
            zip_file.writestr("notes.txt", "not a Fortuneo export")

        with self.assertRaisesRegex(ValueError, "HistoriqueOperations CSV"):
            parse_transactions_csv(archive.getvalue())


class PortfolioTests(unittest.TestCase):
    def test_build_holdings_reduces_cost_basis_on_sell(self):
        transactions = parse_transactions_csv(
            """Date operation;Operation;Code valeur;Quantite;Prix unitaire;Frais;Devise
15/01/2026;Achat;CW8.PA;3;100,00;3,00;EUR
20/02/2026;Vente;CW8.PA;1;120,00;1,00;EUR
"""
        )

        holdings = build_holdings(transactions)

        self.assertEqual(len(holdings), 1)
        self.assertEqual(holdings[0].quantity, Decimal("2"))
        self.assertEqual(holdings[0].average_cost, Decimal("101.00"))

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


class DcaTests(unittest.TestCase):
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


class MarketDataTests(unittest.TestCase):
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
