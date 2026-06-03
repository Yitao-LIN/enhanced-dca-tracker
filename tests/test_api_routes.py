import io
import json
import unittest
import zipfile
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app, get_symbol_search_provider
from app.services.market_data import SymbolSearchResult
import app.models as models  # noqa: F401


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_json(name):
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def load_fixture_bytes(name):
    return (FIXTURES_DIR / name).read_bytes()


def fortuneo_bourse_without_code_bytes():
    csv_text = (
        "libell\u00e9;Op\u00e9ration;Place;Date;Qt\u00e9;Prix d'\u00e9x\u00e9;Montant brut;"
        "Courtage/Pr\u00e9l\u00e8vement;Montant net;Devise;\n"
        "AMUNDI MSCI WORLD;Achat comptant;Paris;15/01/2026;3;470,50;"
        "1411,50;1,95;-1413,45;EUR;\n"
    )
    return csv_text.encode("iso-8859-1")


def fortuneo_account_export_bytes():
    csv_text = (
        "Date op\u00e9ration;Date valeur;libell\u00e9;D\u00e9bit;Cr\u00e9dit;\n"
        "13/12/2019;13/12/2019;CARTE 12/12 EXAMPLE;-6,40;\n"
    )
    return csv_text.encode("iso-8859-1")


def fortuneo_account_export_zip_bytes():
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, mode="w") as zip_file:
        zip_file.writestr("HistoriqueOperationsBourse_2026.csv", fortuneo_account_export_bytes())
    return archive.getvalue()


class StubSearchProvider:
    def __init__(self, results=None, error: Exception | None = None):
        self.results = results or []
        self.error = error
        self.queries = []

    def search_symbols(self, query: str, limit: int = 5):
        self.queries.append((query, limit))
        if self.error is not None:
            raise self.error
        return self.results[:limit]


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

    def test_empty_portfolio_summary_returns_zeroes(self):
        response = self.client.get("/api/portfolio?portfolio_id=default")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "total_value": "0.00",
                "total_invested": "0.00",
                "total_gain": "0.00",
                "total_gain_percent": "0",
                "cash_flow": "0.00",
                "holdings": [],
            },
        )

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

    def test_preview_golden_csv_matches_fixture_without_persisting(self):
        expected = load_json("expected_import_preview.json")

        preview = self._preview_golden_csv()
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json(), {key: value for key, value in expected.items() if key != "source_csv"})

        transactions = self.client.get("/api/transactions?portfolio_id=default")
        self.assertEqual(transactions.status_code, 200)
        self.assertEqual(transactions.json(), [])

    def test_preview_marks_duplicate_rows_and_existing_transactions(self):
        expected_duplicate_rows = load_json("expected_duplicate_preview.json")

        duplicate_preview = self.client.post(
            "/api/transactions/preview?portfolio_id=default",
            files={"file": ("fortuneo_duplicate_rows.csv", load_fixture_bytes("fortuneo_duplicate_rows.csv"), "text/csv")},
        )
        self.assertEqual(duplicate_preview.status_code, 200)
        self.assertEqual(
            duplicate_preview.json(),
            {key: value for key, value in expected_duplicate_rows.items() if key != "source_csv"},
        )

        self._upload_golden_csv()
        existing_preview = self._preview_golden_csv()
        self.assertEqual(existing_preview.status_code, 200)
        self.assertEqual(existing_preview.json()["duplicate_count"], 8)
        self.assertEqual({row["status"] for row in existing_preview.json()["rows"]}, {"duplicate_existing"})

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

    def test_invalid_csv_preview_returns_row_errors_without_bad_request(self):
        response = self.client.post(
            "/api/transactions/preview?portfolio_id=default",
            files={"file": ("bad.csv", b"Operation;Code valeur\nAchat;CW8.PA\n", "text/csv")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["row_count"], 1)
        self.assertEqual(response.json()["valid_count"], 0)
        self.assertEqual(response.json()["duplicate_count"], 0)
        self.assertEqual(response.json()["error_count"], 1)
        self.assertEqual(response.json()["rows"][0]["status"], "invalid")
        self.assertIn("CSV is missing required columns", response.json()["rows"][0]["error"])

    def test_fortuneo_account_export_preview_and_upload_report_wrong_export_type(self):
        preview = self.client.post(
            "/api/transactions/preview?portfolio_id=default",
            files={"file": ("HistoriqueOperationsBourse.zip", fortuneo_account_export_zip_bytes(), "application/zip")},
        )

        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json()["row_count"], 1)
        self.assertEqual(preview.json()["error_count"], 1)
        self.assertEqual(preview.json()["rows"][0]["status"], "invalid")
        self.assertIn("Fortuneo bank-account export", preview.json()["rows"][0]["error"])

        upload = self.client.post(
            "/api/transactions/upload?portfolio_id=default",
            files={"file": ("HistoriqueOperationsBourse.zip", fortuneo_account_export_zip_bytes(), "application/zip")},
        )

        self.assertEqual(upload.status_code, 400)
        self.assertIn("Fortuneo bank-account export", upload.json()["detail"])

    def test_preview_returns_mapping_suggestions_for_unresolved_fortuneo_label(self):
        provider = StubSearchProvider(
            [
                SymbolSearchResult(
                    symbol="CW8.PA",
                    name="Amundi MSCI World UCITS ETF",
                    exchange="PAR",
                    quote_type="ETF",
                    currency="EUR",
                    score=5,
                    source="yfinance",
                )
            ]
        )
        app.dependency_overrides[get_symbol_search_provider] = lambda: provider

        response = self.client.post(
            "/api/transactions/preview?portfolio_id=default",
            files={"file": ("fortuneo_bourse.csv", fortuneo_bourse_without_code_bytes(), "text/csv")},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["row_count"], 1)
        self.assertEqual(payload["valid_count"], 0)
        self.assertEqual(payload["error_count"], 0)
        self.assertEqual(payload["mapping_count"], 1)
        self.assertEqual(payload["rows"][0]["status"], "needs_mapping")
        self.assertEqual(payload["rows"][0]["security_label"], "AMUNDI MSCI WORLD")
        self.assertEqual(payload["rows"][0]["suggestions"][0]["symbol"], "CW8.PA")
        self.assertEqual(provider.queries, [("AMUNDI MSCI WORLD", 5)])

    def test_upload_persists_confirmed_mapping_and_reuses_it(self):
        mapping_payload = [
            {
                "security_label": "AMUNDI MSCI WORLD",
                "ticker": "CW8.PA",
                "provider": "yfinance",
                "provider_name": "Amundi MSCI World UCITS ETF",
                "provider_exchange": "PAR",
                "provider_quote_type": "ETF",
                "provider_currency": "EUR",
            }
        ]

        upload = self.client.post(
            "/api/transactions/upload?portfolio_id=default",
            files={"file": ("fortuneo_bourse.csv", fortuneo_bourse_without_code_bytes(), "text/csv")},
            data={"mappings": json.dumps(mapping_payload)},
        )
        self.assertEqual(upload.status_code, 200)
        self.assertEqual(upload.json()["imported"], 1)

        transactions = self.client.get("/api/transactions?portfolio_id=default")
        self.assertEqual(transactions.status_code, 200)
        self.assertEqual(transactions.json()[0]["ticker"], "CW8.PA")
        self.assertEqual(transactions.json()[0]["description"], "AMUNDI MSCI WORLD")

        app.dependency_overrides[get_symbol_search_provider] = lambda: StubSearchProvider(error=RuntimeError("offline"))
        preview = self.client.post(
            "/api/transactions/preview?portfolio_id=default",
            files={"file": ("fortuneo_bourse.csv", fortuneo_bourse_without_code_bytes(), "text/csv")},
        )
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json()["rows"][0]["status"], "duplicate_existing")
        self.assertNotIn("mapping_count", preview.json())

    def test_preview_keeps_mapping_row_editable_when_search_fails(self):
        app.dependency_overrides[get_symbol_search_provider] = lambda: StubSearchProvider(error=RuntimeError("search offline"))

        response = self.client.post(
            "/api/transactions/preview?portfolio_id=default",
            files={"file": ("fortuneo_bourse.csv", fortuneo_bourse_without_code_bytes(), "text/csv")},
        )

        self.assertEqual(response.status_code, 200)
        row = response.json()["rows"][0]
        self.assertEqual(row["status"], "needs_mapping")
        self.assertEqual(row["suggestions"], [])
        self.assertIn("search offline", row["search_error"])

    def test_security_search_route_uses_provider(self):
        app.dependency_overrides[get_symbol_search_provider] = lambda: StubSearchProvider(
            [SymbolSearchResult(symbol="CW8.PA", name="Amundi MSCI World UCITS ETF", source="yfinance")]
        )

        response = self.client.get("/api/securities/search?query=AMUNDI%20MSCI%20WORLD")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["symbol"], "CW8.PA")

    def _upload_golden_csv(self):
        return self.client.post(
            "/api/transactions/upload?portfolio_id=default",
            files={"file": ("fortuneo_golden.csv", load_fixture_bytes("fortuneo_golden.csv"), "text/csv")},
        )

    def _preview_golden_csv(self):
        return self.client.post(
            "/api/transactions/preview?portfolio_id=default",
            files={"file": ("fortuneo_golden.csv", load_fixture_bytes("fortuneo_golden.csv"), "text/csv")},
        )

    def assertDecimalEqual(self, actual, expected):
        self.assertEqual(Decimal(str(actual)), Decimal(str(expected)))


if __name__ == "__main__":
    unittest.main()
