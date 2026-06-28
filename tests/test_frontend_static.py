"""@file
@brief Static regression tests for the standalone frontend source.
"""

import unittest
from pathlib import Path


FRONTEND_PATH = Path(__file__).parents[1] / "frontend" / "index.html"


class FrontendStaticTests(unittest.TestCase):
    def test_backend_empty_history_does_not_render_demo_monthly_chart(self):
        source = FRONTEND_PATH.read_text(encoding="utf-8")

        self.assertIn("if (apiAvailable) {\n            return [];\n          }", source)
        self.assertLess(
            source.index("if (apiAvailable) {\n            return [];\n          }"),
            source.index('const months = ["Jan", "Feb", "Mar", "Apr", "May", "Now"];'),
        )

    def test_market_price_parser_keeps_dot_decimal_prices(self):
        source = FRONTEND_PATH.read_text(encoding="utf-8")

        parse_number_body = source[source.index("function parseNumber(value)") : source.index("function toNumber(value)")]
        self.assertIn("const lastComma = normalized.lastIndexOf(\",\");", parse_number_body)
        self.assertIn("const lastDot = normalized.lastIndexOf(\".\");", parse_number_body)
        self.assertNotIn('replace(/\\./g, "")', parse_number_body)

    def test_analytics_ui_calls_backend_endpoints(self):
        source = FRONTEND_PATH.read_text(encoding="utf-8")

        self.assertIn("/api/allocation-targets?portfolio_id=", source)
        self.assertIn("/api/portfolio/analytics?", source)
        self.assertIn("function saveAllocationTargets()", source)
        self.assertIn("Portfolio Analytics", source)

    def test_backend_empty_analytics_does_not_render_demo_activity(self):
        source = FRONTEND_PATH.read_text(encoding="utf-8")

        self.assertIn("const analyticsRows = apiAvailable ? analyticsRowsFromApi(portfolioAnalytics) : demoAllocationRows(holdings);", source)
        self.assertIn("const monthlyActivity = portfolioAnalytics.monthly_activity || [];", source)
        self.assertIn("const benchmarkComparison = portfolioAnalytics.benchmark_comparison || [];", source)
        self.assertNotIn("apiAvailable ? monthlyActivity : demo", source)

    def test_dca_strategy_ui_uses_plan_endpoints(self):
        source = FRONTEND_PATH.read_text(encoding="utf-8")

        self.assertIn("/api/dca/plans?portfolio_id=", source)
        self.assertIn("/api/dca/plans/${encodeURIComponent(selectedDcaPlanId)}/recommendation", source)
        self.assertIn("DCA Strategy", source)
        self.assertIn("function saveDcaPlan()", source)
        self.assertNotIn("/api/dca/settings", source)
        self.assertNotIn("/api/dca/recommendation", source)

    def test_backend_empty_dca_plans_do_not_render_demo_plans_as_backend_data(self):
        source = FRONTEND_PATH.read_text(encoding="utf-8")

        self.assertIn("const [dcaPlans, setDcaPlans] = useState([]);", source)
        self.assertIn("Demo mode calculates locally and does not show saved backend plans.", source)
        self.assertNotIn("apiAvailable ? dcaPlans : [", source)

    def test_manual_transaction_ui_uses_backend_create_endpoint(self):
        source = FRONTEND_PATH.read_text(encoding="utf-8")

        self.assertIn("function renderManualTransactionForm()", source)
        self.assertIn("async function saveManualTransaction(event)", source)
        self.assertIn('apiRequest("/api/transactions"', source)
        self.assertIn('transaction_type: type', source)
        self.assertIn('type === "fee" || type === "cash" ? amount : parseNumber(manualDraft.fees)', source)

    def test_manual_transaction_ui_searches_security_mapping(self):
        source = FRONTEND_PATH.read_text(encoding="utf-8")
        manual_form_body = source[source.index("function renderManualTransactionForm()") : source.index("/** @brief Render current allocation bars")]

        self.assertIn("async function searchManualTransactionMapping()", source)
        self.assertIn("/api/securities/search?query=", source)
        self.assertIn("Search mapping", manual_form_body)
        self.assertIn("useManualSearchResult(result)", manual_form_body)
        self.assertIn('updateManualDraft("ticker", result.symbol)', source)

    def test_manual_transaction_entry_is_backend_only(self):
        source = FRONTEND_PATH.read_text(encoding="utf-8")
        manual_form_body = source[source.index("function renderManualTransactionForm()") : source.index("/** @brief Render current allocation bars")]

        self.assertIn('disabled={!apiAvailable || apiLoading}', manual_form_body)
        self.assertIn("Connect API to add manual transactions.", source)
        self.assertNotIn("setTransactions((current)", manual_form_body)

    def test_manual_transaction_keeps_fortuneo_import_available(self):
        source = FRONTEND_PATH.read_text(encoding="utf-8")

        self.assertIn("Fortuneo CSV/ZIP", source)
        self.assertIn("/api/transactions/preview?portfolio_id=", source)
        self.assertIn("/api/transactions/upload?portfolio_id=", source)
        self.assertIn("function importFile(event)", source)
        self.assertIn("function confirmImport()", source)


if __name__ == "__main__":
    unittest.main()
