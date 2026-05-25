import json
import unittest
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
import app.models as models  # noqa: F401


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_json(name):
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def load_fixture_bytes(name):
    return (FIXTURES_DIR / name).read_bytes()


class ApiRouteTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, expire_on_commit=False)

        def override_get_db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_health_and_reference_routes(self):
        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json(), {"status": "ok"})

        portfolios = self.client.get("/api/portfolios")
        self.assertEqual(portfolios.status_code, 200)
        self.assertEqual(len(portfolios.json()), 1)
        self.assertEqual(portfolios.json()[0]["id"], "default")

    def test_upload_transactions_skips_duplicates_and_lists_accounts(self):
        first_upload = self._upload_golden_csv()
        self.assertEqual(first_upload.status_code, 200)
        self.assertEqual(first_upload.json()["row_count"], 8)
        self.assertEqual(first_upload.json()["imported"], 8)
        self.assertEqual(first_upload.json()["duplicates"], 0)
        self.assertEqual(first_upload.json()["total"], 8)

        second_upload = self._upload_golden_csv()
        self.assertEqual(second_upload.status_code, 200)
        self.assertEqual(second_upload.json()["imported"], 0)
        self.assertEqual(second_upload.json()["duplicates"], 8)
        self.assertEqual(second_upload.json()["total"], 8)

        transactions = self.client.get("/api/transactions?portfolio_id=default")
        self.assertEqual(transactions.status_code, 200)
        self.assertEqual(len(transactions.json()), 8)
        self.assertEqual(transactions.json()[0]["ticker"], "CW8.PA")
        self.assertEqual(transactions.json()[0]["transaction_type"], "buy")

        accounts = self.client.get("/api/accounts?portfolio_id=default")
        self.assertEqual(accounts.status_code, 200)
        self.assertEqual([account["name"] for account in accounts.json()], ["CTO", "PEA"])

    def test_portfolio_summary_matches_golden_fixture(self):
        expected = load_json("expected_portfolio_summary.json")
        market_history = load_json("market_history_basic.json")
        self._upload_golden_csv()

        price_update = self.client.put("/api/market/prices", json={"prices": market_history["latest_prices"]})
        self.assertEqual(price_update.status_code, 200)
        self.assertEqual(price_update.json(), {"updated": 3})

        response = self.client.get("/api/portfolio?portfolio_id=default")
        self.assertEqual(response.status_code, 200)
        summary = response.json()

        self.assertDecimalEqual(summary["total_value"], expected["total_value"])
        self.assertDecimalEqual(summary["total_invested"], expected["total_invested"])
        self.assertDecimalEqual(summary["total_gain"], expected["total_gain"])
        self.assertDecimalEqual(summary["total_gain_percent"], expected["total_gain_percent"])
        self.assertDecimalEqual(summary["cash_flow"], expected["cash_flow"])
        self.assertEqual(len(summary["holdings"]), len(expected["holdings"]))

        for actual, expected_holding in zip(summary["holdings"], expected["holdings"]):
            self.assertEqual(actual["ticker"], expected_holding["ticker"])
            self.assertDecimalEqual(actual["quantity"], expected_holding["quantity"])
            self.assertDecimalEqual(actual["average_cost"], expected_holding["average_cost"])
            self.assertDecimalEqual(actual["current_price"], expected_holding["current_price"])
            self.assertDecimalEqual(actual["invested_amount"], expected_holding["invested_amount"])
            self.assertDecimalEqual(actual["market_value"], expected_holding["market_value"])
            self.assertDecimalEqual(actual["unrealized_gain"], expected_holding["unrealized_gain"])
            self.assertDecimalEqual(actual["unrealized_gain_percent"], expected_holding["unrealized_gain_percent"])
            self.assertDecimalEqual(actual["allocation_percent"], expected_holding["allocation_percent"])

    def test_market_history_and_portfolio_history_match_golden_fixture(self):
        expected = load_json("expected_portfolio_summary.json")
        market_history = load_json("market_history_basic.json")
        self._upload_golden_csv()

        write_response = self.client.put("/api/market/history", json={"prices": market_history["prices"]})
        self.assertEqual(write_response.status_code, 200)
        self.assertEqual(write_response.json(), {"updated": len(market_history["prices"])})

        symbol_history = self.client.get(
            "/api/market/history/CW8.PA?start_date=2026-02-01&end_date=2026-05-16&source=manual"
        )
        self.assertEqual(symbol_history.status_code, 200)
        self.assertEqual([point["price_date"] for point in symbol_history.json()], ["2026-02-15", "2026-04-20", "2026-05-16"])

        portfolio_history = self.client.get("/api/portfolio/history?portfolio_id=default")
        self.assertEqual(portfolio_history.status_code, 200)
        self.assertEqual(portfolio_history.json(), expected["portfolio_history"])

    def test_dca_settings_and_recommendation_routes(self):
        settings_payload = {
            "portfolio_id": "default",
            "base_amount": "750",
            "preferred_benchmark": "^ndx",
            "min_multiplier": "0.8",
            "max_multiplier": "1.4",
            "contribution_frequency": "weekly",
        }
        saved_settings = self.client.put("/api/dca/settings", json=settings_payload)
        self.assertEqual(saved_settings.status_code, 200)
        self.assertEqual(saved_settings.json()["base_amount"], "750.00000000")
        self.assertEqual(saved_settings.json()["preferred_benchmark"], "^NDX")
        self.assertEqual(saved_settings.json()["contribution_frequency"], "weekly")

        loaded_settings = self.client.get("/api/dca/settings?portfolio_id=default")
        self.assertEqual(loaded_settings.status_code, 200)
        self.assertEqual(loaded_settings.json()["preferred_benchmark"], "^NDX")

        recommendation = self.client.post(
            "/api/dca/recommendation",
            json={
                "portfolio_id": "default",
                "market_change_percent": "-4",
                "volatility_index": "18",
            },
        )
        self.assertEqual(recommendation.status_code, 200)
        self.assertEqual(recommendation.json()["base_amount"], "750.00")
        self.assertEqual(recommendation.json()["adjusted_amount"], "975.00")
        self.assertEqual(recommendation.json()["multiplier"], "1.3")

    def test_invalid_csv_upload_returns_bad_request(self):
        response = self.client.post(
            "/api/transactions/upload?portfolio_id=default",
            files={"file": ("bad.csv", b"Operation;Code valeur\nAchat;CW8.PA\n", "text/csv")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("CSV is missing required columns", response.json()["detail"])

    def _upload_golden_csv(self):
        return self.client.post(
            "/api/transactions/upload?portfolio_id=default",
            files={"file": ("fortuneo_golden.csv", load_fixture_bytes("fortuneo_golden.csv"), "text/csv")},
        )

    def assertDecimalEqual(self, actual, expected):
        self.assertEqual(Decimal(str(actual)), Decimal(str(expected)))


if __name__ == "__main__":
    unittest.main()
