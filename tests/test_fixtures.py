import json
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.repositories import transaction_fingerprint
from app.services.csv_import import parse_transactions_csv
from app.services.portfolio import summarize_portfolio
from app.services.portfolio_history import build_portfolio_history


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_json(name):
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def load_csv(name):
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


class FixtureTests(unittest.TestCase):
    def test_golden_fixture_matches_expected_summary(self):
        transactions = parse_transactions_csv(load_csv("fortuneo_golden.csv"))
        market_history = load_json("market_history_basic.json")
        expected = load_json("expected_portfolio_summary.json")

        summary = summarize_portfolio(
            transactions,
            {symbol: Decimal(value) for symbol, value in market_history["latest_prices"].items()},
        )

        self.assertEqual(len(transactions), expected["transaction_count"])
        self.assertEqual(sorted({transaction.account for transaction in transactions}), expected["account_names"])
        self.assertEqual(summary.total_value, Decimal(expected["total_value"]))
        self.assertEqual(summary.total_invested, Decimal(expected["total_invested"]))
        self.assertEqual(summary.total_gain, Decimal(expected["total_gain"]))
        self.assertEqual(summary.total_gain_percent, Decimal(expected["total_gain_percent"]))
        self.assertEqual(summary.cash_flow, Decimal(expected["cash_flow"]))

        for actual, expected_holding in zip(summary.holdings, expected["holdings"]):
            self.assertEqual(actual.ticker, expected_holding["ticker"])
            self.assertEqual(actual.quantity, Decimal(expected_holding["quantity"]))
            self.assertEqual(actual.average_cost, Decimal(expected_holding["average_cost"]))
            self.assertEqual(actual.current_price, Decimal(expected_holding["current_price"]))
            self.assertEqual(actual.invested_amount, Decimal(expected_holding["invested_amount"]))
            self.assertEqual(actual.market_value, Decimal(expected_holding["market_value"]))
            self.assertEqual(actual.unrealized_gain, Decimal(expected_holding["unrealized_gain"]))
            self.assertEqual(actual.unrealized_gain_percent, Decimal(expected_holding["unrealized_gain_percent"]))
            self.assertEqual(actual.allocation_percent, Decimal(expected_holding["allocation_percent"]))

    def test_golden_fixture_matches_expected_portfolio_history(self):
        transactions = parse_transactions_csv(load_csv("fortuneo_golden.csv"))
        market_history = load_json("market_history_basic.json")
        expected = load_json("expected_portfolio_summary.json")
        prices_by_symbol = {}
        benchmarks_by_symbol = {}

        for point in market_history["prices"]:
            target = benchmarks_by_symbol if point["symbol"].startswith("^") else prices_by_symbol
            target.setdefault(point["symbol"], {})[date.fromisoformat(point["price_date"])] = Decimal(point["close"])

        actual_history = build_portfolio_history(
            transactions,
            prices_by_symbol=prices_by_symbol,
            benchmarks_by_symbol=benchmarks_by_symbol,
        )

        self.assertEqual(len(actual_history), len(expected["portfolio_history"]))
        for actual, expected_point in zip(actual_history, expected["portfolio_history"]):
            self.assertEqual(actual.price_date.isoformat(), expected_point["date"])
            self.assertEqual(actual.invested_amount, Decimal(expected_point["invested_amount"]))
            self.assertEqual(actual.market_value, Decimal(expected_point["market_value"]))
            self.assertEqual(actual.gain, Decimal(expected_point["gain"]))
            self.assertEqual(actual.gain_percent, Decimal(expected_point["gain_percent"]))
            self.assertEqual(
                actual.benchmarks,
                {symbol: Decimal(value) for symbol, value in expected_point["benchmarks"].items()},
            )

    def test_duplicate_preview_fixture_marks_duplicate_rows(self):
        transactions = parse_transactions_csv(load_csv("fortuneo_duplicate_rows.csv"))
        expected = load_json("expected_duplicate_preview.json")
        seen = set()
        statuses = []

        for transaction in transactions:
            fingerprint = transaction_fingerprint(transaction)
            statuses.append("duplicate_in_file" if fingerprint in seen else "new")
            seen.add(fingerprint)

        self.assertEqual(statuses, [row["status"] for row in expected["rows"]])
        self.assertEqual(statuses.count("duplicate_in_file"), expected["duplicate_count"])


if __name__ == "__main__":
    unittest.main()
