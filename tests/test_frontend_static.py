"""@file
@brief Static regression tests for the frontend source.
"""

import json
import unittest
from pathlib import Path


FRONTEND_DIR = Path(__file__).parents[1] / "frontend"
FRONTEND_INDEX = FRONTEND_DIR / "index.html"
FRONTEND_PACKAGE = FRONTEND_DIR / "package.json"
FRONTEND_SOURCE = FRONTEND_DIR / "src" / "main.jsx"
FRONTEND_STYLES = FRONTEND_DIR / "src" / "styles.css"


class FrontendStaticTests(unittest.TestCase):
    def source(self):
        return FRONTEND_SOURCE.read_text(encoding="utf-8")

    def test_vite_frontend_mounts_react_app(self):
        index_source = FRONTEND_INDEX.read_text(encoding="utf-8")
        package = json.loads(FRONTEND_PACKAGE.read_text(encoding="utf-8"))

        self.assertIn('<div id="root"></div>', index_source)
        self.assertIn('src="/src/main.jsx"', index_source)
        self.assertEqual(package["type"], "module")
        self.assertIn("vite --host 127.0.0.1", package["scripts"]["dev"])
        self.assertIn("vite build", package["scripts"]["build"])
        self.assertIn("react", package["dependencies"])

    def test_vite_frontend_has_release_layout_styles(self):
        styles = FRONTEND_STYLES.read_text(encoding="utf-8")

        self.assertIn(".app-shell", styles)
        self.assertIn(".sidebar", styles)
        self.assertIn(".two-column-view", styles)
        self.assertIn("@media (max-width: 760px)", styles)

    def test_backend_empty_history_does_not_render_demo_monthly_chart(self):
        source = self.source()
        chart_body = source[source.index("function chartRows(apiAvailable") : source.index("function PortfolioView")]

        self.assertIn("if (apiAvailable) {", chart_body)
        self.assertIn("return (portfolioHistory || []).map", chart_body)
        self.assertLess(
            chart_body.index("return (portfolioHistory || []).map"),
            chart_body.index('const months = ["Jan", "Feb", "Mar", "Apr", "May", "Now"];'),
        )

    def test_market_price_parser_keeps_dot_decimal_prices(self):
        source = self.source()

        parse_number_body = source[source.index("function parseNumber(value)") : source.index("function toNumber(value)")]
        self.assertIn("const lastComma = normalized.lastIndexOf(\",\");", parse_number_body)
        self.assertIn("const lastDot = normalized.lastIndexOf(\".\");", parse_number_body)
        self.assertNotIn('replace(/\\./g, "")', parse_number_body)

    def test_analytics_ui_calls_backend_endpoints(self):
        source = self.source()

        self.assertIn("/api/allocation-targets?portfolio_id=", source)
        self.assertIn("/api/portfolio/analytics?", source)
        self.assertIn("async function saveTargets()", source)
        self.assertIn("Targets, allocation drift, activity, and benchmarks.", source)

    def test_backend_empty_analytics_does_not_render_demo_activity(self):
        source = self.source()
        analytics_body = source[source.index("function AnalyticsView") : source.index("function ActivityCard")]

        self.assertIn("const rows = portfolioAnalytics.allocation_drift || [];", analytics_body)
        self.assertIn("const activity = portfolioAnalytics.monthly_activity || [];", analytics_body)
        self.assertIn("const benchmarks = portfolioAnalytics.benchmark_comparison || [];", analytics_body)
        self.assertNotIn("demoAllocationRows", source)
        self.assertNotIn("apiAvailable ? activity", analytics_body)

    def test_dca_strategy_ui_uses_plan_endpoints(self):
        source = self.source()

        self.assertIn("/api/dca/plans?portfolio_id=", source)
        self.assertIn("/api/dca/plans/${encodeURIComponent(selectedDcaPlanId)}/recommendation", source)
        self.assertIn("DCA Strategy", source)
        self.assertIn("async function savePlan()", source)
        self.assertNotIn("/api/dca/settings", source)
        self.assertNotIn("/api/dca/recommendation", source)

    def test_backend_empty_dca_plans_do_not_render_demo_plans_as_backend_data(self):
        source = self.source()

        self.assertIn("const [dcaPlans, setDcaPlans] = useState([]);", source)
        self.assertIn('dcaPlans.map((plan) => <option key={plan.id} value={plan.id}>', source)
        self.assertNotIn("apiAvailable ? dcaPlans : [", source)

    def test_manual_transaction_ui_uses_backend_create_endpoint(self):
        source = self.source()

        self.assertIn("function ManualTransactionForm(", source)
        self.assertIn("async function saveManualTransaction(event)", source)
        self.assertIn('apiRequest("/api/transactions"', source)
        self.assertIn('transaction_type: type', source)
        self.assertIn('type === "fee" || type === "cash" ? amount : parseNumber(manualDraft.fees)', source)

    def test_manual_transaction_ui_searches_security_mapping(self):
        source = self.source()
        manual_form_body = source[source.index("function ManualTransactionForm(") : source.index("function ImportPreview")]

        self.assertIn("async function searchManualTransactionMapping()", source)
        self.assertIn("/api/securities/search?query=", source)
        self.assertIn("Search mapping", manual_form_body)
        self.assertIn("useResult(result)", manual_form_body)
        self.assertIn("useResult={useManualSearchResult}", source)
        self.assertIn('updateManualDraft("ticker", result.symbol)', source)

    def test_manual_transaction_entry_is_backend_only(self):
        source = self.source()
        transactions_body = source[source.index("function TransactionsView") : source.index("function ImportPreview")]

        self.assertIn('disabled={!apiAvailable || apiLoading}', transactions_body)
        self.assertIn("Connect API to add manual transactions.", source)
        self.assertNotIn("setTransactions((current)", transactions_body)

    def test_manual_transaction_keeps_fortuneo_import_available(self):
        source = self.source()

        self.assertIn("Fortuneo CSV/ZIP import", source)
        self.assertIn("/api/transactions/preview?portfolio_id=", source)
        self.assertIn("/api/transactions/upload?portfolio_id=", source)
        self.assertIn("function importFile(event)", source)
        self.assertIn("function confirmImport()", source)


if __name__ == "__main__":
    unittest.main()
