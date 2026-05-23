import unittest
from decimal import Decimal

from app.services.csv_import import parse_transactions_csv
from app.services.dca import calculate_enhanced_dca
from app.services.portfolio import build_holdings, summarize_portfolio


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


class DcaTests(unittest.TestCase):
    def test_enhanced_dca_increases_on_market_drawdown(self):
        recommendation = calculate_enhanced_dca(
            base_amount=Decimal("1000"),
            market_change_percent=Decimal("-4"),
            volatility_index=Decimal("18"),
        )

        self.assertEqual(recommendation.adjusted_amount, Decimal("1300.00"))
        self.assertEqual(recommendation.multiplier, Decimal("1.3"))


if __name__ == "__main__":
    unittest.main()
