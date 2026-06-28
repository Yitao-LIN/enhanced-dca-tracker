import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const DEFAULT_API_BASE_URL = localStorage.getItem("trackerApiBaseUrl") || "http://127.0.0.1:8000";
const BENCHMARKS = [
  { symbol: "^GSPC", key: "sp500", label: "S&P 500", color: "#1c8c5a" },
  { symbol: "^NDX", key: "nasdaq100", label: "Nasdaq 100", color: "#b45f06" },
];
const CHART_RANGES = [
  { key: "1d", label: "1D", days: 1, intraday: true, interval: "30m" },
  { key: "5d", label: "5D", days: 5, intraday: true, interval: "1h" },
  { key: "30d", label: "30D", days: 30 },
  { key: "1y", label: "1Y", yearStart: true },
  { key: "all", label: "Since start", days: null },
];

const sampleCsv = `Date operation;Operation;Code valeur;Quantite;Prix unitaire;Frais;Devise;Compte;Libelle
15/01/2026;Achat;CW8.PA;3;470,50;1,95;EUR;PEA;Amundi MSCI World
15/02/2026;Achat;CW8.PA;2;480,10;1,95;EUR;PEA;Amundi MSCI World
15/03/2026;Achat;EWLD.PA;8;32,60;1,95;EUR;PEA;Amundi World
20/04/2026;Vente;EWLD.PA;2;34,20;1,95;EUR;PEA;Rebalance`;

const initialPrices = {
  "CW8.PA": 510.2,
  "EWLD.PA": 35.4,
};

const emptyApiSummary = {
  total_value: 0,
  total_invested: 0,
  total_gain: 0,
  total_gain_percent: 0,
  cash_flow: 0,
  holdings: [],
};

const emptyAnalytics = {
  total_value: 0,
  total_target_percent: 0,
  unassigned_target_percent: 100,
  allocation_drift: [],
  monthly_activity: [],
  benchmark_comparison: [],
};

function money(value) {
  return new Intl.NumberFormat("fr-FR", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 2,
  }).format(Number.isFinite(Number(value)) ? Number(value) : 0);
}

function percent(value) {
  const number = Number(value);
  return `${number >= 0 ? "+" : ""}${Number.isFinite(number) ? number.toFixed(2) : "0.00"}%`;
}

function parseNumber(value) {
  if (!value) return 0;
  let normalized = String(value).trim().replace(/\s/g, "").replace(/[^0-9,.-]/g, "");
  const lastComma = normalized.lastIndexOf(",");
  const lastDot = normalized.lastIndexOf(".");
  if (lastComma >= 0 && lastDot >= 0) {
    const decimalSeparator = lastComma > lastDot ? "," : ".";
    const groupSeparator = decimalSeparator === "," ? "." : ",";
    normalized = normalized.replaceAll(groupSeparator, "").replace(decimalSeparator, ".");
  } else if (lastComma >= 0) {
    normalized = normalized.replace(",", ".");
  }
  return Number(normalized.replace(/[^0-9.-]/g, "")) || 0;
}

function toNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}

function isoDate(date) {
  return date.toISOString().slice(0, 10);
}

function queryString(params) {
  return Object.entries(params)
    .filter(([, value]) => value !== undefined && value !== null && value !== "")
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
    .join("&");
}

function chartRangeConfig(rangeKey) {
  return CHART_RANGES.find((item) => item.key === rangeKey) || CHART_RANGES[3];
}

function chartDateRange(rangeKey) {
  const end = new Date();
  const range = chartRangeConfig(rangeKey);
  const params = { end_date: isoDate(end) };
  if (range.yearStart) {
    params.start_date = isoDate(new Date(end.getFullYear(), 0, 1));
  } else if (range.days !== null) {
    const start = new Date(end);
    start.setDate(start.getDate() - range.days);
    params.start_date = isoDate(start);
  }
  return params;
}

function chartDateTimeRange(rangeKey) {
  const end = new Date();
  const range = chartRangeConfig(rangeKey);
  const start = new Date(end);
  start.setDate(start.getDate() - (range.days || 1));
  return {
    start_at: start.toISOString(),
    end_at: end.toISOString(),
    interval: range.interval || "30m",
  };
}

function isIntradayRange(rangeKey) {
  return Boolean(chartRangeConfig(rangeKey).intraday);
}

function splitCsvLine(line, delimiter) {
  const result = [];
  let cell = "";
  let quoted = false;
  for (const char of line) {
    if (char === '"') {
      quoted = !quoted;
    } else if (char === delimiter && !quoted) {
      result.push(cell);
      cell = "";
    } else {
      cell += char;
    }
  }
  result.push(cell);
  return result;
}

function parseCsv(text) {
  const lines = text.split(/\r?\n/).filter((line) => line.trim());
  if (lines.length < 2) return [];
  const delimiter = lines[0].includes(";") ? ";" : ",";
  const headers = splitCsvLine(lines[0], delimiter).map((header) => header.toLowerCase());
  const indexOf = (...names) => headers.findIndex((header) => names.some((name) => header.includes(name)));
  const indexes = {
    date: indexOf("date"),
    type: indexOf("operation", "type"),
    ticker: indexOf("code valeur", "ticker", "symbol"),
    quantity: indexOf("quantite", "quantity", "qte"),
    price: indexOf("prix", "price"),
    fees: indexOf("frais", "fees"),
    currency: indexOf("devise", "currency"),
    account: indexOf("compte", "account"),
    description: indexOf("libelle", "description"),
  };
  return lines.slice(1).map((line) => {
    const cells = splitCsvLine(line, delimiter);
    const rawType = (cells[indexes.type] || "").toLowerCase();
    const type = rawType.includes("vente") || rawType.includes("sell") ? "sell" : "buy";
    return {
      transaction_date: cells[indexes.date] || "",
      ticker: (cells[indexes.ticker] || "").trim().toUpperCase(),
      transaction_type: type,
      quantity: parseNumber(cells[indexes.quantity]),
      price: parseNumber(cells[indexes.price]),
      fees: parseNumber(cells[indexes.fees]),
      currency: (cells[indexes.currency] || "EUR").trim().toUpperCase(),
      account: cells[indexes.account] || "",
      description: cells[indexes.description] || "",
    };
  });
}

function buildDemoHoldings(transactions, prices) {
  const lots = {};
  transactions.forEach((transaction) => {
    const key = transaction.ticker;
    if (!key) return;
    lots[key] ||= { ticker: key, quantity: 0, cost: 0, name: transaction.description, currency: transaction.currency || "EUR" };
    if (transaction.transaction_type === "buy") {
      lots[key].quantity += transaction.quantity;
      lots[key].cost += transaction.quantity * transaction.price + transaction.fees;
    } else if (transaction.transaction_type === "sell" && lots[key].quantity > 0) {
      const sold = Math.min(transaction.quantity, lots[key].quantity);
      const avg = lots[key].cost / lots[key].quantity;
      lots[key].quantity -= sold;
      lots[key].cost -= avg * sold;
    }
  });
  const openLots = Object.values(lots).filter((lot) => lot.quantity > 0.0001);
  const totalValue = openLots.reduce((sum, lot) => sum + lot.quantity * (prices[lot.ticker] || lot.cost / lot.quantity), 0);
  return openLots.map((lot) => {
    const averageCost = lot.cost / lot.quantity;
    const currentPrice = prices[lot.ticker] || averageCost;
    const value = lot.quantity * currentPrice;
    const gain = value - lot.cost;
    return {
      ticker: lot.ticker,
      name: lot.name,
      quantity: lot.quantity,
      averageCost,
      currentPrice,
      value,
      gain,
      gainPercent: lot.cost ? (gain / lot.cost) * 100 : 0,
      allocation: totalValue ? (value / totalValue) * 100 : 0,
    };
  });
}

function holdingsFromApi(summary) {
  return (summary.holdings || []).map((holding) => ({
    ticker: holding.ticker,
    name: holding.name,
    quantity: toNumber(holding.quantity),
    averageCost: toNumber(holding.average_cost),
    currentPrice: toNumber(holding.current_price),
    value: toNumber(holding.market_value),
    gain: toNumber(holding.unrealized_gain),
    gainPercent: toNumber(holding.unrealized_gain_percent),
    allocation: toNumber(holding.allocation_percent),
  }));
}

function defaultManualTransactionDraft() {
  return {
    transaction_date: isoDate(new Date()),
    transaction_type: "buy",
    ticker: "",
    quantity: "",
    price: "",
    amount: "",
    fees: "0",
    currency: "EUR",
    account: "",
    description: "",
  };
}

function defaultDcaDraft(portfolioId = "default") {
  return {
    portfolio_id: portfolioId,
    name: "Monthly normal",
    model_type: "normal",
    base_amount: 1000,
    preferred_benchmark: "^GSPC",
    min_multiplier: 0.7,
    max_multiplier: 1.5,
    contribution_frequency: "monthly",
    is_default: false,
  };
}

function dcaDraftFromPlan(plan, portfolioId = "default") {
  if (!plan) return defaultDcaDraft(portfolioId);
  return {
    portfolio_id: plan.portfolio_id || portfolioId,
    name: plan.name || "Monthly normal",
    model_type: plan.model_type || "normal",
    base_amount: toNumber(plan.base_amount) || 0,
    preferred_benchmark: plan.preferred_benchmark || "^GSPC",
    min_multiplier: toNumber(plan.min_multiplier) || 0.7,
    max_multiplier: toNumber(plan.max_multiplier) || 1.5,
    contribution_frequency: plan.contribution_frequency || "monthly",
    is_default: Boolean(plan.is_default),
  };
}

function dcaPlanPayload(draft, portfolioId) {
  return {
    portfolio_id: portfolioId,
    name: String(draft.name || "").trim(),
    model_type: draft.model_type,
    base_amount: Number(draft.base_amount) || 0,
    preferred_benchmark: String(draft.preferred_benchmark || "^GSPC").trim().toUpperCase(),
    min_multiplier: Number(draft.min_multiplier) || 0.7,
    max_multiplier: Number(draft.max_multiplier) || 1.5,
    contribution_frequency: String(draft.contribution_frequency || "monthly").trim().toLowerCase(),
    is_default: Boolean(draft.is_default),
  };
}

function calculateDca(modelType, baseAmount, marketChange, volatility) {
  if (modelType === "normal") {
    return {
      adjusted: Math.round(baseAmount),
      multiplier: 1,
      reason: "Keep contribution because this Normal DCA plan uses a fixed amount.",
      allocationSuggestions: [],
    };
  }
  let multiplier = 1;
  if (marketChange <= -5) multiplier = 1.5;
  else if (marketChange <= -3) multiplier = 1.3;
  else if (marketChange <= -1) multiplier = 1.2;
  else if (marketChange >= 5) multiplier = 0.7;
  else if (marketChange >= 3) multiplier = 0.8;
  if (volatility >= 30 && multiplier > 1) multiplier += 0.1;
  if (volatility <= 14 && multiplier > 1) multiplier -= 0.1;
  const adjusted = Math.round(baseAmount * multiplier);
  const action = multiplier > 1 ? "Increase" : multiplier < 1 ? "Decrease" : "Keep";
  return {
    adjusted,
    multiplier,
    reason: `${action} the next contribution from market movement and volatility inputs.`,
    allocationSuggestions: [],
  };
}

function metricValue(value) {
  return <strong>{money(toNumber(value))}</strong>;
}

function MiniStat({ label, children }) {
  return (
    <div className="mini-stat">
      <span>{label}</span>
      <strong>{children}</strong>
    </div>
  );
}

function Button({ children, className = "", ...props }) {
  return (
    <button className={className} {...props}>
      {children}
    </button>
  );
}

function App() {
  const [apiBaseUrl, setApiBaseUrl] = useState(DEFAULT_API_BASE_URL);
  const [apiBaseDraft, setApiBaseDraft] = useState(DEFAULT_API_BASE_URL);
  const [apiAvailable, setApiAvailable] = useState(false);
  const [apiLoading, setApiLoading] = useState(false);
  const [status, setStatus] = useState("Demo mode loaded. Start FastAPI to sync with the backend.");
  const [activeView, setActiveView] = useState("portfolio");
  const [transactions, setTransactions] = useState(() => parseCsv(sampleCsv));
  const [prices, setPrices] = useState(initialPrices);
  const [apiSummary, setApiSummary] = useState(emptyApiSummary);
  const [portfolios, setPortfolios] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [selectedPortfolioId, setSelectedPortfolioId] = useState("default");
  const [portfolioHistory, setPortfolioHistory] = useState([]);
  const [portfolioAnalytics, setPortfolioAnalytics] = useState(emptyAnalytics);
  const [allocationTargets, setAllocationTargets] = useState([]);
  const [targetDrafts, setTargetDrafts] = useState({});
  const [newTarget, setNewTarget] = useState({ ticker: "", target_percent: "" });
  const [chartRange, setChartRange] = useState("1y");
  const [visibleBenchmarks, setVisibleBenchmarks] = useState({ sp500: true, nasdaq100: true });
  const [hiddenSecurities, setHiddenSecurities] = useState([]);
  const [securityMappings, setSecurityMappings] = useState([]);
  const [newMapping, setNewMapping] = useState({ security_label: "", ticker: "" });
  const [dcaPlans, setDcaPlans] = useState([]);
  const [selectedDcaPlanId, setSelectedDcaPlanId] = useState("");
  const [dcaDraft, setDcaDraft] = useState(() => defaultDcaDraft("default"));
  const [apiDca, setApiDca] = useState(null);
  const [marketChange, setMarketChange] = useState(-2.3);
  const [volatility, setVolatility] = useState(18.5);
  const [manualDraft, setManualDraft] = useState(() => defaultManualTransactionDraft());
  const [manualSearchQuery, setManualSearchQuery] = useState("");
  const [manualSearchResults, setManualSearchResults] = useState([]);
  const [manualSearchStatus, setManualSearchStatus] = useState("");
  const [importPreview, setImportPreview] = useState(null);
  const [pendingImportFile, setPendingImportFile] = useState(null);
  const [mappingSelections, setMappingSelections] = useState({});
  const [mappingSearchDrafts, setMappingSearchDrafts] = useState({});
  const [mappingSearchStatus, setMappingSearchStatus] = useState({});
  const [mappingSuggestionOverrides, setMappingSuggestionOverrides] = useState({});

  async function apiRequest(path, options = {}) {
    let response;
    try {
      response = await fetch(`${apiBaseUrl}${path}`, options);
    } catch (error) {
      throw new Error(`Backend request failed before a response from ${apiBaseUrl}${path}. ${error.message}`);
    }
    if (!response.ok) {
      const message = await response.text();
      throw new Error(message || `${response.status} ${response.statusText}`);
    }
    return response.status === 204 ? null : response.json();
  }

  function historyPath(portfolioId = selectedPortfolioId) {
    if (isIntradayRange(chartRange)) {
      return `/api/portfolio/history/intraday?${queryString({
        portfolio_id: portfolioId,
        ...chartDateTimeRange(chartRange),
      })}`;
    }
    return `/api/portfolio/history?${queryString({
      portfolio_id: portfolioId,
      ...chartDateRange(chartRange),
    })}`;
  }

  function analyticsPath(portfolioId = selectedPortfolioId) {
    return `/api/portfolio/analytics?${queryString({
      portfolio_id: portfolioId,
      ...chartDateRange(chartRange),
    })}`;
  }

  async function connectBackend() {
    setApiLoading(true);
    try {
      await apiRequest("/api/health");
      setApiAvailable(true);
      localStorage.setItem("trackerApiBaseUrl", apiBaseUrl);
      await refreshBackendData(selectedPortfolioId, { autoBackfill: true });
      setStatus(`Connected to backend at ${apiBaseUrl}.`);
    } catch (error) {
      setApiAvailable(false);
      setStatus(`Backend unavailable. Demo mode is active. ${error.message}`);
    } finally {
      setApiLoading(false);
    }
  }

  async function refreshBackendData(portfolioId = selectedPortfolioId, options = {}) {
    const { autoBackfill = false, quiet = false } = options;
    setApiLoading(true);
    try {
      const [portfolioRows, accountRows, summary, historyRows, planRows, mappingRows, hiddenRows, targetRows, analytics] = await Promise.all([
        apiRequest("/api/portfolios"),
        apiRequest(`/api/accounts?portfolio_id=${encodeURIComponent(portfolioId)}`),
        apiRequest(`/api/portfolio?portfolio_id=${encodeURIComponent(portfolioId)}`),
        apiRequest(historyPath(portfolioId)),
        apiRequest(`/api/dca/plans?portfolio_id=${encodeURIComponent(portfolioId)}`),
        apiRequest(`/api/security-mappings?portfolio_id=${encodeURIComponent(portfolioId)}`),
        apiRequest(`/api/hidden-securities?portfolio_id=${encodeURIComponent(portfolioId)}`),
        apiRequest(`/api/allocation-targets?portfolio_id=${encodeURIComponent(portfolioId)}`),
        apiRequest(analyticsPath(portfolioId)),
      ]);
      setPortfolios(portfolioRows);
      setAccounts(accountRows);
      setApiSummary(summary);
      setPortfolioHistory(historyRows);
      setDcaPlans(planRows);
      setSecurityMappings(mappingRows);
      setHiddenSecurities(hiddenRows);
      setAllocationTargets(targetRows);
      setPortfolioAnalytics(analytics);
      setTargetDrafts(targetDraftsFromRows(targetRows, analytics.allocation_drift || []));
      const activePlan = planRows.find((plan) => String(plan.id) === String(selectedDcaPlanId)) || planRows.find((plan) => plan.is_default) || planRows[0];
      setSelectedDcaPlanId(activePlan ? String(activePlan.id) : "");
      setDcaDraft(dcaDraftFromPlan(activePlan, portfolioId));
      setApiDca(null);
      setPrices((current) => ({
        ...current,
        ...(summary.holdings || []).reduce((nextPrices, holding) => {
          nextPrices[holding.ticker] = toNumber(holding.current_price);
          return nextPrices;
        }, {}),
      }));
      setApiAvailable(true);
      if (autoBackfill) {
        const result = await backfillMarketHistory(portfolioId, summary.holdings || [], historyRows);
        if (result) {
          const [refreshedSummary, refreshedHistory, refreshedHidden, refreshedAnalytics] = await Promise.all([
            apiRequest(`/api/portfolio?portfolio_id=${encodeURIComponent(portfolioId)}`),
            apiRequest(historyPath(portfolioId)),
            apiRequest(`/api/hidden-securities?portfolio_id=${encodeURIComponent(portfolioId)}`),
            apiRequest(analyticsPath(portfolioId)),
          ]);
          setApiSummary(refreshedSummary);
          setPortfolioHistory(refreshedHistory);
          setHiddenSecurities(refreshedHidden);
          setPortfolioAnalytics(refreshedAnalytics);
          setTargetDrafts(targetDraftsFromRows(targetRows, refreshedAnalytics.allocation_drift || []));
          if (!quiet) {
            const skipped = result.failures || [];
            const skippedText = skipped.length ? ` Skipped ${skipped.map((failure) => failure.symbol).join(", ")}.` : "";
            setStatus(`Backfilled ${result.updated} market history row(s).${skippedText}`);
          }
        }
      }
    } catch (error) {
      setApiAvailable(false);
      setStatus(`Backend sync failed: ${error.message}`);
    } finally {
      setApiLoading(false);
    }
  }

  async function backfillMarketHistory(portfolioId, visibleHoldings, historyRows = []) {
    const symbols = Array.from(new Set([...(visibleHoldings || []).map((holding) => holding.ticker), ...BENCHMARKS.map((item) => item.symbol)]));
    if (!symbols.length) return null;
    if (isIntradayRange(chartRange)) {
      const range = chartDateTimeRange(chartRange);
      const response = await apiRequest("/api/market/intraday/backfill", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbols, ...range, currency: "EUR", source: "yfinance" }),
      });
      if (response.updated > 0 || response.failures?.length) return response;
    }
    const range = chartDateRange(chartRange);
    const latestHistoryDate = historyRows.map((row) => row.date || row.timestamp).filter(Boolean).sort().at(-1);
    if (latestHistoryDate && range.start_date && latestHistoryDate >= range.start_date && latestHistoryDate >= range.end_date) {
      return null;
    }
    return apiRequest("/api/market/history/backfill", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbols, ...range, currency: "EUR", source: "yfinance" }),
    });
  }

  useEffect(() => {
    connectBackend();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (apiAvailable) refreshBackendData(selectedPortfolioId, { autoBackfill: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedPortfolioId]);

  useEffect(() => {
    if (apiAvailable) refreshBackendData(selectedPortfolioId, { autoBackfill: true, quiet: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chartRange]);

  const demoHoldings = useMemo(() => buildDemoHoldings(transactions, prices), [transactions, prices]);
  const apiHoldings = useMemo(() => holdingsFromApi(apiSummary), [apiSummary]);
  const holdings = apiAvailable ? apiHoldings : demoHoldings;
  const totalValue = apiAvailable ? toNumber(apiSummary.total_value) : holdings.reduce((sum, holding) => sum + holding.value, 0);
  const totalInvested = apiAvailable ? toNumber(apiSummary.total_invested) : holdings.reduce((sum, holding) => sum + holding.averageCost * holding.quantity, 0);
  const totalGain = apiAvailable ? toNumber(apiSummary.total_gain) : totalValue - totalInvested;
  const totalGainPercent = apiAvailable ? toNumber(apiSummary.total_gain_percent) : totalInvested ? (totalGain / totalInvested) * 100 : 0;
  const history = useMemo(() => chartRows(apiAvailable, portfolioHistory, totalInvested, totalGain), [apiAvailable, portfolioHistory, totalInvested, totalGain]);
  const dcaBaseAmount = toNumber(dcaDraft.base_amount);
  const dca = apiDca || calculateDca(dcaDraft.model_type, dcaBaseAmount, marketChange, volatility);

  function resetDemo() {
    setApiAvailable(false);
    setTransactions(parseCsv(sampleCsv));
    setApiSummary(emptyApiSummary);
    setPortfolioHistory([]);
    setPortfolioAnalytics(emptyAnalytics);
    setHiddenSecurities([]);
    setSecurityMappings([]);
    setAllocationTargets([]);
    setTargetDrafts({});
    setDcaPlans([]);
    setSelectedDcaPlanId("");
    setDcaDraft(defaultDcaDraft(selectedPortfolioId));
    setApiDca(null);
    setStatus("Demo data restored.");
  }

  const viewProps = {
    apiAvailable,
    apiLoading,
    status,
    setStatus,
    apiRequest,
    refreshBackendData,
    portfolios,
    accounts,
    selectedPortfolioId,
    setSelectedPortfolioId,
    holdings,
    prices,
    setPrices,
    apiSummary,
    totalValue,
    totalInvested,
    totalGain,
    totalGainPercent,
    chartRange,
    setChartRange,
    visibleBenchmarks,
    setVisibleBenchmarks,
    history,
    hiddenSecurities,
    setHiddenSecurities,
    portfolioAnalytics,
    allocationTargets,
    targetDrafts,
    setTargetDrafts,
    newTarget,
    setNewTarget,
    securityMappings,
    setSecurityMappings,
    newMapping,
    setNewMapping,
    manualDraft,
    setManualDraft,
    manualSearchQuery,
    setManualSearchQuery,
    manualSearchResults,
    setManualSearchResults,
    manualSearchStatus,
    setManualSearchStatus,
    importPreview,
    setImportPreview,
    pendingImportFile,
    setPendingImportFile,
    mappingSelections,
    setMappingSelections,
    mappingSearchDrafts,
    setMappingSearchDrafts,
    mappingSearchStatus,
    setMappingSearchStatus,
    mappingSuggestionOverrides,
    setMappingSuggestionOverrides,
    dcaPlans,
    setDcaPlans,
    selectedDcaPlanId,
    setSelectedDcaPlanId,
    dcaDraft,
    setDcaDraft,
    dca,
    apiDca,
    setApiDca,
    marketChange,
    setMarketChange,
    volatility,
    setVolatility,
  };

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">DCA</span>
          <div>
            <h1>Enhanced Tracker</h1>
            <p>Local portfolio workflow</p>
          </div>
        </div>
        <nav>
          {[
            ["portfolio", "Portfolio"],
            ["transactions", "Transactions"],
            ["analytics", "Analytics"],
            ["dca", "DCA Strategy"],
            ["settings", "Settings"],
          ].map(([key, label]) => (
            <button key={key} className={activeView === key ? "active" : ""} onClick={() => setActiveView(key)}>
              {label}
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <span className={`status-pill ${apiAvailable ? "connected" : ""}`}>{apiAvailable ? "Backend connected" : "Demo mode"}</span>
          <Button disabled={apiLoading} onClick={connectBackend}>{apiAvailable ? "Sync API" : "Connect API"}</Button>
          <Button onClick={resetDemo}>Demo data</Button>
        </div>
      </aside>
      <section className="main-panel">
        <header className="page-header">
          <div>
            <h2>{viewTitle(activeView)}</h2>
            <p>{viewSubtitle(activeView)}</p>
          </div>
          <div className="actions">
            <span className="muted">{status}</span>
          </div>
        </header>
        {activeView === "portfolio" && <PortfolioView {...viewProps} />}
        {activeView === "transactions" && <TransactionsView {...viewProps} />}
        {activeView === "analytics" && <AnalyticsView {...viewProps} />}
        {activeView === "dca" && <DcaView {...viewProps} />}
        {activeView === "settings" && (
          <SettingsView
            apiBaseUrl={apiBaseUrl}
            apiBaseDraft={apiBaseDraft}
            setApiBaseDraft={setApiBaseDraft}
            setApiBaseUrl={setApiBaseUrl}
            connectBackend={connectBackend}
            apiLoading={apiLoading}
          />
        )}
      </section>
    </main>
  );
}

function viewTitle(view) {
  return {
    portfolio: "Portfolio",
    transactions: "Transactions",
    analytics: "Analytics",
    dca: "DCA Strategy",
    settings: "Settings",
  }[view];
}

function viewSubtitle(view) {
  return {
    portfolio: "Holdings, valuation, history, and market context.",
    transactions: "Manual entry, security search, Fortuneo imports, and mappings.",
    analytics: "Targets, allocation drift, activity, and benchmarks.",
    dca: "Saved contribution plans and next-investment recommendations.",
    settings: "Local app configuration, startup checks, and data backup notes.",
  }[view];
}

function chartRows(apiAvailable, portfolioHistory, totalInvested, totalGain) {
  if (apiAvailable) {
    return (portfolioHistory || []).map((point) => ({
      date: String(point.timestamp || point.date),
      invested: toNumber(point.invested_amount),
      value: toNumber(point.market_value),
      sp500: point.benchmarks && point.benchmarks["^GSPC"] !== undefined ? toNumber(point.benchmarks["^GSPC"]) : undefined,
      nasdaq100: point.benchmarks && point.benchmarks["^NDX"] !== undefined ? toNumber(point.benchmarks["^NDX"]) : undefined,
    }));
  }
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Now"];
  return months.map((month, index) => {
    const ratio = (index + 1) / months.length;
    return {
      date: month,
      invested: totalInvested * ratio,
      value: totalInvested * ratio + totalGain * Math.pow(ratio, 1.3),
    };
  });
}

function targetDraftsFromRows(targetRows, analyticsRows = []) {
  const drafts = {};
  targetRows.forEach((row) => {
    drafts[row.ticker] = String(toNumber(row.target_percent));
  });
  analyticsRows.forEach((row) => {
    if (row.target_percent !== null && drafts[row.ticker] === undefined) {
      drafts[row.ticker] = String(toNumber(row.target_percent));
    }
  });
  return drafts;
}

function PortfolioView(props) {
  const {
    apiAvailable,
    apiLoading,
    apiRequest,
    refreshBackendData,
    selectedPortfolioId,
    holdings,
    prices,
    setPrices,
    totalValue,
    totalInvested,
    totalGain,
    totalGainPercent,
    chartRange,
    setChartRange,
    visibleBenchmarks,
    setVisibleBenchmarks,
    history,
    hiddenSecurities,
    setStatus,
  } = props;

  async function saveMarketPrice(ticker, value) {
    const parsed = parseNumber(value);
    setPrices((current) => ({ ...current, [ticker]: parsed }));
    if (!apiAvailable) return;
    await apiRequest("/api/market/prices", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prices: { [ticker]: parsed } }),
    });
    await refreshBackendData(selectedPortfolioId);
    setStatus(`Saved market price for ${ticker}.`);
  }

  async function hideSecurity(ticker) {
    await apiRequest(`/api/hidden-securities?portfolio_id=${encodeURIComponent(selectedPortfolioId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ticker }),
    });
    await refreshBackendData(selectedPortfolioId);
  }

  async function restoreSecurity(ticker) {
    await apiRequest(`/api/hidden-securities?portfolio_id=${encodeURIComponent(selectedPortfolioId)}&ticker=${encodeURIComponent(ticker)}`, {
      method: "DELETE",
    });
    await refreshBackendData(selectedPortfolioId);
  }

  async function deleteSecurity(ticker) {
    if (!window.confirm(`Delete all imported transactions for ${ticker}? You can import them again later.`)) return;
    const result = await apiRequest(`/api/transactions/${encodeURIComponent(ticker)}?portfolio_id=${encodeURIComponent(selectedPortfolioId)}`, { method: "DELETE" });
    await refreshBackendData(selectedPortfolioId);
    setStatus(`Deleted ${result.deleted} transaction row(s) for ${ticker}.`);
  }

  return (
    <div className="view-stack">
      <section className="metrics-grid">
        <Metric label="Total value" value={money(totalValue)} />
        <Metric label="Invested amount" value={money(totalInvested)} />
        <Metric label="Unrealized gain" value={money(totalGain)} tone={totalGain >= 0 ? "positive" : "negative"} />
        <Metric label="Return" value={percent(totalGainPercent)} tone={totalGain >= 0 ? "positive" : "negative"} />
      </section>
      <section className="panel">
        <div className="panel-header">
          <div>
            <h3>Portfolio Performance</h3>
            <p>Daily/intraday value, invested amount, and normalized benchmarks.</p>
          </div>
          <div className="segmented">
            {CHART_RANGES.map((range) => (
              <button key={range.key} className={chartRange === range.key ? "active" : ""} onClick={() => setChartRange(range.key)}>
                {range.label}
              </button>
            ))}
          </div>
        </div>
        <LineChart data={history} visibleBenchmarks={visibleBenchmarks} />
        <div className="legend">
          <span><i style={{ background: "#8090a5" }} />Invested</span>
          <span><i style={{ background: "#185fa5" }} />Value</span>
          {BENCHMARKS.map((benchmark) => (
            <label key={benchmark.key}>
              <input
                type="checkbox"
                checked={visibleBenchmarks[benchmark.key]}
                onChange={(event) => setVisibleBenchmarks((current) => ({ ...current, [benchmark.key]: event.target.checked }))}
              />
              <i style={{ background: benchmark.color }} />
              {benchmark.label}
            </label>
          ))}
        </div>
      </section>
      <section className="panel">
        <div className="panel-header">
          <div>
            <h3>Holdings</h3>
            <p>{holdings.length} open position(s)</p>
          </div>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Ticker</th>
                <th className="num">Qty</th>
                <th className="num">Avg cost</th>
                <th className="num">Market price</th>
                <th className="num">Value</th>
                <th className="num">Gain</th>
                <th className="num">Allocation</th>
                {apiAvailable && <th>Actions</th>}
              </tr>
            </thead>
            <tbody>
              {holdings.map((holding) => (
                <tr key={holding.ticker}>
                  <td><strong>{holding.ticker}</strong>{holding.name && <small>{holding.name}</small>}</td>
                  <td className="num">{holding.quantity.toFixed(4)}</td>
                  <td className="num">{money(holding.averageCost)}</td>
                  <td className="num">
                    <input
                      className="compact-input"
                      value={prices[holding.ticker] ?? holding.currentPrice ?? ""}
                      onChange={(event) => setPrices((current) => ({ ...current, [holding.ticker]: event.target.value }))}
                      onBlur={(event) => saveMarketPrice(holding.ticker, event.target.value)}
                    />
                  </td>
                  <td className="num">{money(holding.value)}</td>
                  <td className={`num ${holding.gain >= 0 ? "positive" : "negative"}`}>{money(holding.gain)} ({percent(holding.gainPercent)})</td>
                  <td className="num">{holding.allocation.toFixed(1)}%</td>
                  {apiAvailable && (
                    <td className="actions-inline">
                      <Button disabled={apiLoading} onClick={() => hideSecurity(holding.ticker)}>Hide</Button>
                      <Button disabled={apiLoading} onClick={() => deleteSecurity(holding.ticker)}>Delete</Button>
                    </td>
                  )}
                </tr>
              ))}
              {!holdings.length && <tr><td colSpan={apiAvailable ? 8 : 7}>No visible holdings.</td></tr>}
            </tbody>
          </table>
        </div>
        {apiAvailable && hiddenSecurities.length > 0 && (
          <div className="chip-list">
            {hiddenSecurities.map((security) => (
              <span className="chip" key={security.ticker}>
                {security.ticker}
                <button onClick={() => restoreSecurity(security.ticker)}>Restore</button>
              </span>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function Metric({ label, value, tone = "" }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong className={tone}>{value}</strong>
    </div>
  );
}

function LineChart({ data, visibleBenchmarks }) {
  const width = 900;
  const height = 290;
  const pad = 44;
  const series = [
    { key: "value", label: "Value", color: "#185fa5", width: 3 },
    { key: "invested", label: "Invested", color: "#8090a5", width: 2.5, dash: "6 5" },
    ...(visibleBenchmarks.sp500 ? [{ key: "sp500", label: "S&P 500", color: "#1c8c5a", width: 2.5, dash: "7 5" }] : []),
    ...(visibleBenchmarks.nasdaq100 ? [{ key: "nasdaq100", label: "Nasdaq 100", color: "#b45f06", width: 2.5, dash: "4 5" }] : []),
  ];
  const values = data.flatMap((item) => series.map((serie) => item[serie.key]).filter((value) => Number.isFinite(value)));
  if (!data.length || !values.length) {
    return (
      <div className="chart-empty">
        No visible history for this range.
      </div>
    );
  }
  const rawMax = Math.max(...values);
  const rawMin = Math.min(...values);
  const padding = rawMax === rawMin ? Math.max(Math.abs(rawMax) * 0.01, 1) : (rawMax - rawMin) * 0.08;
  const max = rawMax + padding;
  const min = rawMin - padding;
  const x = (index) => pad + (index / Math.max(data.length - 1, 1)) * (width - pad * 2);
  const y = (value) => height - pad - ((value - min) / (max - min || 1)) * (height - pad * 2);
  const path = (key) => data.map((item, index) => Number.isFinite(item[key]) ? `${index === 0 ? "M" : "L"}${x(index)},${y(item[key])}` : "").filter(Boolean).join(" ");

  return (
    <div className="chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Portfolio performance chart">
        {[0, 1, 2, 3].map((line) => {
          const yy = pad + line * ((height - pad * 2) / 3);
          return <line key={line} x1={pad} y1={yy} x2={width - pad} y2={yy} stroke="#d8dde5" />;
        })}
        {series.map((serie) => {
          const d = path(serie.key);
          return d ? <path key={serie.key} d={d} fill="none" stroke={serie.color} strokeWidth={serie.width} strokeDasharray={serie.dash} /> : null;
        })}
        {series.map((serie) => data.map((item, index) => Number.isFinite(item[serie.key]) ? (
          <circle key={`${serie.key}-${index}`} cx={x(index)} cy={y(item[serie.key])} r="4.5" fill={serie.color} stroke="#fff" strokeWidth="2" />
        ) : null))}
        {data.length === 1 && (
          <text x={width / 2} y={height - 14} textAnchor="middle" fontSize="12" fill="#627083">
            Single available point. Add more market-history dates to compare performance.
          </text>
        )}
      </svg>
    </div>
  );
}

function TransactionsView(props) {
  const {
    apiAvailable,
    apiLoading,
    apiRequest,
    refreshBackendData,
    portfolios,
    accounts,
    selectedPortfolioId,
    setSelectedPortfolioId,
    manualDraft,
    setManualDraft,
    manualSearchQuery,
    setManualSearchQuery,
    manualSearchResults,
    setManualSearchResults,
    manualSearchStatus,
    setManualSearchStatus,
    importPreview,
    setImportPreview,
    pendingImportFile,
    setPendingImportFile,
    mappingSelections,
    setMappingSelections,
    mappingSearchDrafts,
    setMappingSearchDrafts,
    mappingSearchStatus,
    setMappingSearchStatus,
    mappingSuggestionOverrides,
    setMappingSuggestionOverrides,
    securityMappings,
    setSecurityMappings,
    newMapping,
    setNewMapping,
    setStatus,
  } = props;

  function updateManualDraft(field, value) {
    setManualDraft((current) => ({
      ...current,
      [field]: field === "ticker" || field === "currency" ? String(value || "").toUpperCase() : value,
      ...(field === "transaction_type" ? { quantity: "", price: "", amount: "", fees: "0" } : {}),
    }));
  }

  async function searchManualTransactionMapping() {
    const query = String(manualSearchQuery || manualDraft.description || manualDraft.ticker || "").trim();
    if (!query) {
      setManualSearchStatus("Enter a security name, ISIN, or ticker to search.");
      return;
    }
    setManualSearchStatus("Searching...");
    const results = await apiRequest(`/api/securities/search?query=${encodeURIComponent(query)}&limit=10`);
    setManualSearchResults(results);
    if (results[0] && !String(manualDraft.ticker || "").trim()) {
      updateManualDraft("ticker", results[0].symbol);
    }
    setManualSearchStatus(results.length ? `Found ${results.length} result(s) for ${query}.` : `No results for ${query}.`);
  }

  function useManualSearchResult(result) {
    updateManualDraft("ticker", result.symbol);
    if (!String(manualDraft.description || "").trim() && result.name) {
      updateManualDraft("description", result.name);
    }
    setManualSearchStatus(`Selected ${result.symbol}.`);
  }

  function manualTransactionDisabledReason() {
    if (!apiAvailable) return "Connect API to add manual transactions.";
    if (!manualDraft.transaction_date) return "Choose a transaction date.";
    if (!String(manualDraft.ticker || "").trim()) return "Enter a ticker.";
    const fees = parseNumber(manualDraft.fees);
    if (fees < 0) return "Fees must be zero or greater.";
    if (["buy", "sell"].includes(manualDraft.transaction_type)) {
      if (parseNumber(manualDraft.quantity) <= 0) return "Enter a quantity greater than zero.";
      if (parseNumber(manualDraft.price) <= 0) return "Enter a price greater than zero.";
      return "";
    }
    if (parseNumber(manualDraft.amount) <= 0) return "Enter an amount greater than zero.";
    return "";
  }

  function manualTransactionPayload() {
    const type = manualDraft.transaction_type;
    const amount = parseNumber(manualDraft.amount);
    const trade = type === "buy" || type === "sell";
    return {
      portfolio_id: selectedPortfolioId,
      transaction_date: manualDraft.transaction_date,
      ticker: String(manualDraft.ticker || "").trim().toUpperCase(),
      transaction_type: type,
      quantity: trade ? parseNumber(manualDraft.quantity) : type === "dividend" ? 1 : 0,
      price: trade ? parseNumber(manualDraft.price) : type === "dividend" ? amount : 0,
      fees: type === "fee" || type === "cash" ? amount : parseNumber(manualDraft.fees),
      currency: String(manualDraft.currency || "EUR").trim().toUpperCase(),
      account: String(manualDraft.account || "").trim() || null,
      description: String(manualDraft.description || "").trim() || null,
    };
  }

  async function saveManualTransaction(event) {
    event.preventDefault();
    const disabledReason = manualTransactionDisabledReason();
    if (disabledReason) {
      setStatus(disabledReason);
      return;
    }
    const payload = manualTransactionPayload();
    const result = await apiRequest("/api/transactions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    await refreshBackendData(selectedPortfolioId, { autoBackfill: true });
    setManualDraft((current) => ({ ...defaultManualTransactionDraft(), currency: current.currency || "EUR", account: current.account || "" }));
    setManualSearchQuery("");
    setManualSearchResults([]);
    setManualSearchStatus("");
    setStatus(result.created ? `Added ${payload.transaction_type} transaction for ${payload.ticker}.` : `Skipped duplicate transaction for ${payload.ticker}.`);
  }

  async function importFile(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!apiAvailable) {
      const text = await file.text();
      setStatus(`Parsed ${parseCsv(text).length} row(s) in demo mode. Connect API to persist imports.`);
      return;
    }
    const formData = new FormData();
    formData.append("file", file);
    const preview = await apiRequest(`/api/transactions/preview?portfolio_id=${encodeURIComponent(selectedPortfolioId)}`, {
      method: "POST",
      body: formData,
    });
    setPendingImportFile(file);
    setImportPreview(preview);
    setMappingSelections(initialMappingSelections(preview));
    setMappingSearchDrafts({});
    setMappingSearchStatus({});
    setMappingSuggestionOverrides({});
    setStatus(`Reviewed ${preview.row_count} row(s) from ${file.name}.`);
    event.target.value = "";
  }

  async function confirmImport() {
    if (!pendingImportFile || !importPreview) return;
    const formData = new FormData();
    formData.append("file", pendingImportFile);
    const mappings = confirmedMappingsPayload(importPreview, mappingSelections, mappingSuggestionOverrides);
    if (mappings.length) formData.append("mappings", JSON.stringify(mappings));
    const summary = await apiRequest(`/api/transactions/upload?portfolio_id=${encodeURIComponent(selectedPortfolioId)}`, {
      method: "POST",
      body: formData,
    });
    setImportPreview(null);
    setPendingImportFile(null);
    await refreshBackendData(selectedPortfolioId, { autoBackfill: true });
    setStatus(`Imported ${summary.imported} row(s), skipped ${summary.duplicates} duplicate(s) from ${pendingImportFile.name}.`);
  }

  async function saveNewMapping() {
    const label = String(newMapping.security_label || "").trim();
    const ticker = String(newMapping.ticker || "").trim().toUpperCase();
    if (!label || !ticker) return;
    const saved = await apiRequest(`/api/security-mappings?portfolio_id=${encodeURIComponent(selectedPortfolioId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ security_label: label, ticker, provider: "manual" }),
    });
    setSecurityMappings((current) => [...current.filter((item) => item.normalized_label !== saved.normalized_label), saved]);
    setNewMapping({ security_label: "", ticker: "" });
  }

  return (
    <div className="two-column-view">
      <section className="panel">
        <div className="panel-header">
          <div>
            <h3>Manual transaction</h3>
            <p>Search a security, select a ticker, then save one backend transaction.</p>
          </div>
          <Button className="primary" onClick={saveManualTransaction} disabled={Boolean(manualTransactionDisabledReason()) || apiLoading}>Add transaction</Button>
        </div>
        <PortfolioSelector portfolios={portfolios} selectedPortfolioId={selectedPortfolioId} setSelectedPortfolioId={setSelectedPortfolioId} disabled={!apiAvailable || apiLoading} />
        <ManualTransactionForm
          draft={manualDraft}
          updateDraft={updateManualDraft}
          accounts={accounts}
          disabled={!apiAvailable || apiLoading}
          searchQuery={manualSearchQuery}
          setSearchQuery={setManualSearchQuery}
          searchResults={manualSearchResults}
          searchStatus={manualSearchStatus}
          search={searchManualTransactionMapping}
          useResult={useManualSearchResult}
        />
        <p className="form-note">{manualTransactionDisabledReason()}</p>
      </section>
      <section className="panel">
        <div className="panel-header">
          <div>
            <h3>Fortuneo CSV/ZIP import</h3>
            <p>Preview, resolve mappings, and import duplicate-safe transaction rows.</p>
          </div>
        </div>
        <div className="dropzone">
          <label>CSV or ZIP file</label>
          <input type="file" accept=".csv,.zip,text/csv,application/zip" disabled={apiLoading} onChange={importFile} />
        </div>
        {importPreview && (
          <ImportPreview
            preview={importPreview}
            mappingSelections={mappingSelections}
            setMappingSelections={setMappingSelections}
            mappingSearchDrafts={mappingSearchDrafts}
            setMappingSearchDrafts={setMappingSearchDrafts}
            mappingSearchStatus={mappingSearchStatus}
            setMappingSearchStatus={setMappingSearchStatus}
            mappingSuggestionOverrides={mappingSuggestionOverrides}
            setMappingSuggestionOverrides={setMappingSuggestionOverrides}
            apiRequest={apiRequest}
            confirmImport={confirmImport}
            clear={() => {
              setImportPreview(null);
              setPendingImportFile(null);
            }}
          />
        )}
        <MappingsEditor securityMappings={securityMappings} newMapping={newMapping} setNewMapping={setNewMapping} saveNewMapping={saveNewMapping} />
      </section>
    </div>
  );
}

function PortfolioSelector({ portfolios, selectedPortfolioId, setSelectedPortfolioId, disabled }) {
  return (
    <div className="field">
      <label>Portfolio</label>
      <select value={selectedPortfolioId} disabled={disabled} onChange={(event) => setSelectedPortfolioId(event.target.value)}>
        {(portfolios.length ? portfolios : [{ id: "default", name: "Default Portfolio" }]).map((portfolio) => (
          <option key={portfolio.id} value={portfolio.id}>{portfolio.name}</option>
        ))}
      </select>
    </div>
  );
}

function ManualTransactionForm({ draft, updateDraft, accounts, disabled, searchQuery, setSearchQuery, searchResults, searchStatus, search, useResult }) {
  const trade = draft.transaction_type === "buy" || draft.transaction_type === "sell";
  const amountLabel = draft.transaction_type === "dividend" ? "Dividend amount" : draft.transaction_type === "fee" ? "Fee amount" : "Cash outflow";
  return (
    <form className="form-grid" onSubmit={(event) => event.preventDefault()}>
      <div className="field"><label>Date</label><input type="date" value={draft.transaction_date} disabled={disabled} onChange={(event) => updateDraft("transaction_date", event.target.value)} /></div>
      <div className="field"><label>Type</label><select value={draft.transaction_type} disabled={disabled} onChange={(event) => updateDraft("transaction_type", event.target.value)}><option value="buy">Buy</option><option value="sell">Sell</option><option value="dividend">Dividend</option><option value="fee">Fee</option><option value="cash">Cash outflow</option></select></div>
      <div className="field"><label>Ticker</label><input value={draft.ticker} disabled={disabled} onChange={(event) => updateDraft("ticker", event.target.value)} /></div>
      <div className="field">
        <label>Search mapping</label>
        <div className="inline-field">
          <input value={searchQuery} placeholder="Security name, ISIN, or ticker" disabled={disabled} onChange={(event) => setSearchQuery(event.target.value)} />
          <Button type="button" disabled={disabled || !String(searchQuery || draft.description || draft.ticker || "").trim()} onClick={search}>Search</Button>
        </div>
      </div>
      {(searchStatus || searchResults.length > 0) && (
        <div className="full">
          {searchStatus && <p className="form-note">{searchStatus}</p>}
          <div className="suggestion-list">
            {searchResults.map((result) => (
              <div className="suggestion" key={result.symbol}>
                <strong>{result.symbol}</strong>
                <span>{result.name || result.source}</span>
                <small>{[result.exchange, result.currency, result.quote_type].filter(Boolean).join(" / ") || "-"}</small>
                <Button type="button" onClick={() => useResult(result)}>Use</Button>
              </div>
            ))}
          </div>
        </div>
      )}
      <div className="field"><label>Currency</label><input value={draft.currency} disabled={disabled} onChange={(event) => updateDraft("currency", event.target.value)} /></div>
      {trade ? (
        <>
          <div className="field"><label>Quantity</label><input value={draft.quantity} disabled={disabled} onChange={(event) => updateDraft("quantity", event.target.value)} /></div>
          <div className="field"><label>Price</label><input value={draft.price} disabled={disabled} onChange={(event) => updateDraft("price", event.target.value)} /></div>
          <div className="field"><label>Fees</label><input value={draft.fees} disabled={disabled} onChange={(event) => updateDraft("fees", event.target.value)} /></div>
        </>
      ) : (
        <>
          <div className="field"><label>{amountLabel}</label><input value={draft.amount} disabled={disabled} onChange={(event) => updateDraft("amount", event.target.value)} /></div>
          {draft.transaction_type === "dividend" && <div className="field"><label>Fees</label><input value={draft.fees} disabled={disabled} onChange={(event) => updateDraft("fees", event.target.value)} /></div>}
        </>
      )}
      <div className="field"><label>Account</label><input list="account-options" value={draft.account} disabled={disabled} onChange={(event) => updateDraft("account", event.target.value)} /><datalist id="account-options">{accounts.map((account) => <option key={account.id} value={account.name} />)}</datalist></div>
      <div className="field full"><label>Description</label><textarea value={draft.description} disabled={disabled} onChange={(event) => updateDraft("description", event.target.value)} /></div>
    </form>
  );
}

function ImportPreview({ preview, mappingSelections, setMappingSelections, mappingSearchDrafts, setMappingSearchDrafts, mappingSearchStatus, setMappingSearchStatus, mappingSuggestionOverrides, setMappingSuggestionOverrides, apiRequest, confirmImport, clear }) {
  const rows = preview.rows || [];
  const mappingRows = rows.filter((row) => row.status === "needs_mapping");
  const invalidRows = rows.filter((row) => row.status === "invalid");
  const newRows = rows.filter((row) => row.status === "new");
  const mappingGroups = buildMappingGroups(mappingRows, mappingSelections, mappingSuggestionOverrides);
  const confirmedCount = mappingGroups.filter((group) => mappingSelections[group.key]?.confirmed).length;
  const disabledReason = invalidRows.length
    ? `Fix ${invalidRows.length} invalid row(s) before importing.`
    : confirmedCount < mappingGroups.length
      ? `Confirm ${mappingGroups.length - confirmedCount} mapping task(s).`
      : newRows.length === 0 && mappingRows.length === 0
        ? "There are no new rows to import."
        : "";

  async function searchGroup(group) {
    const query = String(mappingSearchDrafts[group.key] || group.security_label || "").trim();
    if (!query) return;
    setMappingSearchStatus((current) => ({ ...current, [group.key]: "Searching..." }));
    const results = await apiRequest(`/api/securities/search?query=${encodeURIComponent(query)}&limit=10`);
    setMappingSuggestionOverrides((current) => ({ ...current, [group.key]: mergeSuggestions([...(current[group.key] || []), ...results]) }));
    setMappingSearchStatus((current) => ({ ...current, [group.key]: results.length ? `Found ${results.length} result(s).` : "No results." }));
  }

  return (
    <div className="preview-block">
      <div className="summary-row">
        <MiniStat label="Rows">{preview.row_count}</MiniStat>
        <MiniStat label="New">{newRows.length}</MiniStat>
        <MiniStat label="Mappings">{confirmedCount}/{mappingGroups.length}</MiniStat>
        <MiniStat label="Duplicates">{preview.duplicate_count}</MiniStat>
        <MiniStat label="Errors">{preview.error_count}</MiniStat>
      </div>
      {mappingGroups.map((group) => (
        <div className="mapping-card" key={group.key}>
          <strong>{group.security_label}</strong>
          <span>Rows {group.rowNumbers.join(", ")}</span>
          <div className="inline-field">
            <input value={mappingSelections[group.key]?.ticker || ""} onChange={(event) => setMappingSelections((current) => ({ ...current, [group.key]: { ticker: event.target.value.toUpperCase(), confirmed: false } }))} />
            <Button onClick={() => setMappingSelections((current) => ({ ...current, [group.key]: { ticker: current[group.key]?.ticker, confirmed: true } }))}>Confirm</Button>
          </div>
          <div className="inline-field">
            <input value={mappingSearchDrafts[group.key] ?? group.security_label ?? ""} onChange={(event) => setMappingSearchDrafts((current) => ({ ...current, [group.key]: event.target.value }))} />
            <Button onClick={() => searchGroup(group)}>Search</Button>
          </div>
          {mappingSearchStatus[group.key] && <p className="form-note">{mappingSearchStatus[group.key]}</p>}
          <div className="suggestion-list">
            {group.suggestions.map((suggestion) => (
              <div className="suggestion" key={`${group.key}-${suggestion.symbol}`}>
                <strong>{suggestion.symbol}</strong>
                <span>{suggestion.name || suggestion.source}</span>
                <Button onClick={() => setMappingSelections((current) => ({ ...current, [group.key]: { ticker: suggestion.symbol, confirmed: false } }))}>Use</Button>
              </div>
            ))}
          </div>
        </div>
      ))}
      <div className="table-wrap compact-table">
        <table>
          <thead><tr><th>Row</th><th>Status</th><th>Date</th><th>Ticker</th><th>Type</th><th className="num">Qty</th><th className="num">Price</th></tr></thead>
          <tbody>{rows.map((row) => <tr key={row.row_number}><td>{row.row_number}</td><td>{row.status}</td><td>{row.transaction_date || "-"}</td><td>{row.ticker || "-"}</td><td>{row.transaction_type || "-"}</td><td className="num">{row.quantity ?? "-"}</td><td className="num">{row.price ?? "-"}</td></tr>)}</tbody>
        </table>
      </div>
      <div className="actions">
        <Button className="primary" disabled={Boolean(disabledReason)} onClick={confirmImport}>Confirm import</Button>
        <Button onClick={clear}>Clear</Button>
      </div>
      {disabledReason && <p className="form-note">{disabledReason}</p>}
    </div>
  );
}

function buildMappingGroups(rows, selections, overrides) {
  const groups = {};
  rows.forEach((row) => {
    const key = row.security_label || `row-${row.row_number}`;
    const suggestions = mergeSuggestions([...(row.suggestions || []), ...(overrides[key] || [])]);
    groups[key] ||= { key, security_label: row.security_label, rowNumbers: [], suggestions };
    groups[key].rowNumbers.push(row.row_number);
    const firstSuggestion = suggestions[0];
    if (!selections[key] && firstSuggestion) {
      selections[key] = { ticker: firstSuggestion.symbol, confirmed: false };
    }
  });
  return Object.values(groups);
}

function initialMappingSelections(preview) {
  const selections = {};
  (preview.rows || []).filter((row) => row.status === "needs_mapping").forEach((row) => {
    const key = row.security_label || `row-${row.row_number}`;
    const suggestion = (row.suggestions || [])[0];
    if (suggestion) selections[key] = { ticker: suggestion.symbol, confirmed: false };
  });
  return selections;
}

function mergeSuggestions(items) {
  const seen = new Set();
  return (items || []).filter((item) => {
    const symbol = String(item?.symbol || "").toUpperCase();
    if (!symbol || seen.has(symbol)) return false;
    seen.add(symbol);
    return true;
  });
}

function confirmedMappingsPayload(preview, selections, overrides) {
  return buildMappingGroups((preview.rows || []).filter((row) => row.status === "needs_mapping"), selections, overrides)
    .filter((group) => selections[group.key]?.confirmed)
    .map((group) => {
      const ticker = String(selections[group.key]?.ticker || "").trim().toUpperCase();
      const suggestion = group.suggestions.find((item) => String(item.symbol || "").toUpperCase() === ticker);
      return {
        security_label: group.security_label,
        ticker,
        provider: suggestion?.source || "manual",
        provider_name: suggestion?.name || null,
        provider_exchange: suggestion?.exchange || null,
        provider_quote_type: suggestion?.quote_type || null,
        provider_currency: suggestion?.currency || null,
      };
    });
}

function MappingsEditor({ securityMappings, newMapping, setNewMapping, saveNewMapping }) {
  return (
    <div className="subsection">
      <h4>Saved mappings</h4>
      <div className="table-wrap compact-table">
        <table>
          <thead><tr><th>Label</th><th>Ticker</th><th>Provider</th></tr></thead>
          <tbody>
            {securityMappings.map((mapping) => <tr key={mapping.id}><td>{mapping.security_label}</td><td>{mapping.ticker}</td><td>{mapping.provider}</td></tr>)}
            {!securityMappings.length && <tr><td colSpan="3">No saved mappings yet.</td></tr>}
          </tbody>
        </table>
      </div>
      <div className="inline-field">
        <input placeholder="Security label" value={newMapping.security_label} onChange={(event) => setNewMapping((current) => ({ ...current, security_label: event.target.value }))} />
        <input placeholder="Ticker" value={newMapping.ticker} onChange={(event) => setNewMapping((current) => ({ ...current, ticker: event.target.value.toUpperCase() }))} />
        <Button onClick={saveNewMapping}>Add mapping</Button>
      </div>
    </div>
  );
}

function AnalyticsView(props) {
  const { apiAvailable, apiRequest, refreshBackendData, selectedPortfolioId, portfolioAnalytics, targetDrafts, setTargetDrafts, newTarget, setNewTarget, setStatus } = props;
  const rows = portfolioAnalytics.allocation_drift || [];
  const activity = portfolioAnalytics.monthly_activity || [];
  const benchmarks = portfolioAnalytics.benchmark_comparison || [];

  function targetPayload() {
    const targets = new Map();
    Object.entries(targetDrafts).forEach(([ticker, rawPercent]) => {
      const symbol = String(ticker || "").trim().toUpperCase();
      const value = Number(rawPercent);
      if (symbol && Number.isFinite(value) && value > 0) targets.set(symbol, { ticker: symbol, target_percent: value });
    });
    const symbol = String(newTarget.ticker || "").trim().toUpperCase();
    const value = Number(newTarget.target_percent);
    if (symbol && Number.isFinite(value) && value > 0) targets.set(symbol, { ticker: symbol, target_percent: value });
    return Array.from(targets.values()).sort((a, b) => a.ticker.localeCompare(b.ticker));
  }

  async function saveTargets() {
    const records = await apiRequest(`/api/allocation-targets?portfolio_id=${encodeURIComponent(selectedPortfolioId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(targetPayload()),
    });
    setNewTarget({ ticker: "", target_percent: "" });
    setTargetDrafts(targetDraftsFromRows(records, rows));
    await refreshBackendData(selectedPortfolioId);
    setStatus("Saved allocation targets.");
  }

  return (
    <div className="view-stack">
      <section className="metrics-grid">
        <MiniStat label="Targeted">{toNumber(portfolioAnalytics.total_target_percent).toFixed(2)}%</MiniStat>
        <MiniStat label="Unassigned">{toNumber(portfolioAnalytics.unassigned_target_percent).toFixed(2)}%</MiniStat>
        <MiniStat label="Tracked value">{money(toNumber(portfolioAnalytics.total_value))}</MiniStat>
        <MiniStat label="Activity months">{activity.length}</MiniStat>
      </section>
      <section className="panel">
        <div className="panel-header"><h3>Allocation drift</h3>{apiAvailable && <Button className="primary" onClick={saveTargets}>Save targets</Button>}</div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Ticker</th><th className="num">Current</th><th className="num">Target %</th><th className="num">Buy</th><th className="num">Trim</th></tr></thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.ticker}>
                  <td><strong>{row.ticker}</strong>{row.name && <small>{row.name}</small>}</td>
                  <td className="num">{money(toNumber(row.current_value))} ({toNumber(row.current_percent).toFixed(1)}%)</td>
                  <td className="num"><input className="compact-input" value={targetDrafts[row.ticker] ?? ""} onChange={(event) => setTargetDrafts((current) => ({ ...current, [row.ticker]: event.target.value }))} /></td>
                  <td className="num">{money(toNumber(row.buy_value))}</td>
                  <td className="num">{money(toNumber(row.trim_value))}</td>
                </tr>
              ))}
              {!rows.length && <tr><td colSpan="5">No visible holdings or allocation targets.</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="inline-field">
          <input placeholder="Target ticker" value={newTarget.ticker} onChange={(event) => setNewTarget((current) => ({ ...current, ticker: event.target.value.toUpperCase() }))} />
          <input placeholder="Target %" value={newTarget.target_percent} onChange={(event) => setNewTarget((current) => ({ ...current, target_percent: event.target.value }))} />
          <Button onClick={saveTargets}>Add target</Button>
        </div>
      </section>
      <section className="two-column-view">
        <div className="panel"><h3>Monthly activity</h3>{activity.map((row) => <ActivityCard key={row.month} row={row} />)}{!activity.length && <p>No activity for this range.</p>}</div>
        <div className="panel"><h3>Benchmark comparison</h3>{benchmarks.map((row) => <BenchmarkCard key={row.symbol} row={row} />)}{!benchmarks.length && <p>No benchmark comparison yet. More comparable market-history dates are needed.</p>}</div>
      </section>
    </div>
  );
}

function ActivityCard({ row }) {
  return (
    <div className="list-card">
      <strong>{row.month}</strong>
      <span>Buy {money(toNumber(row.buy_contributions))}</span>
      <span>Sell {money(toNumber(row.sell_proceeds))}</span>
      <span>Dividends {money(toNumber(row.dividends))}</span>
      <span>Fees {money(toNumber(row.fees))}</span>
    </div>
  );
}

function BenchmarkCard({ row }) {
  return (
    <div className="list-card">
      <strong>{row.name || row.symbol}</strong>
      <span>Portfolio {percent(toNumber(row.portfolio_return_percent))}</span>
      <span>{row.symbol} {percent(toNumber(row.benchmark_return_percent))}</span>
      <span>Relative {percent(toNumber(row.relative_return_percent))}</span>
    </div>
  );
}

function DcaView(props) {
  const { apiAvailable, apiRequest, selectedPortfolioId, dcaPlans, setDcaPlans, selectedDcaPlanId, setSelectedDcaPlanId, dcaDraft, setDcaDraft, dca, setApiDca, marketChange, setMarketChange, volatility, setVolatility, setStatus } = props;

  function updateDcaDraft(field, value) {
    setApiDca(null);
    setDcaDraft((current) => ({ ...current, [field]: value }));
  }

  function selectPlan(planId) {
    const selected = dcaPlans.find((plan) => String(plan.id) === String(planId));
    setSelectedDcaPlanId(planId);
    setDcaDraft(dcaDraftFromPlan(selected, selectedPortfolioId));
    setApiDca(null);
  }

  async function savePlan() {
    const payload = dcaPlanPayload(dcaDraft, selectedPortfolioId);
    const updating = selectedDcaPlanId && dcaPlans.some((plan) => String(plan.id) === String(selectedDcaPlanId));
    const saved = await apiRequest(updating ? `/api/dca/plans/${encodeURIComponent(selectedDcaPlanId)}` : "/api/dca/plans", {
      method: updating ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const planRows = await apiRequest(`/api/dca/plans?portfolio_id=${encodeURIComponent(selectedPortfolioId)}`);
    setDcaPlans(planRows);
    setSelectedDcaPlanId(String(saved.id));
    setStatus(`Saved DCA plan ${saved.name}.`);
  }

  async function computeRecommendation() {
    if (!selectedDcaPlanId) {
      setStatus("Save a DCA plan before computing a backend recommendation.");
      return;
    }
    const recommendation = await apiRequest(`/api/dca/plans/${encodeURIComponent(selectedDcaPlanId)}/recommendation`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ market_change_percent: marketChange, volatility_index: volatility, ...chartDateRange("1y") }),
    });
    setApiDca({
      adjusted: toNumber(recommendation.adjusted_amount),
      multiplier: toNumber(recommendation.multiplier),
      reason: recommendation.reason,
      allocationSuggestions: recommendation.allocation_suggestions || [],
    });
    setMarketChange(toNumber(recommendation.market_change_percent));
  }

  return (
    <div className="two-column-view">
      <section className="panel">
        <div className="panel-header"><h3>Saved plan</h3>{apiAvailable && <Button onClick={() => { setSelectedDcaPlanId(""); setDcaDraft(defaultDcaDraft(selectedPortfolioId)); }}>New plan</Button>}</div>
        <div className="form-grid">
          <div className="field full"><label>Plan</label><select value={selectedDcaPlanId} onChange={(event) => selectPlan(event.target.value)}><option value="">New unsaved plan</option>{dcaPlans.map((plan) => <option key={plan.id} value={plan.id}>{plan.name}{plan.is_default ? " (default)" : ""}</option>)}</select></div>
          <div className="field"><label>Name</label><input value={dcaDraft.name} onChange={(event) => updateDcaDraft("name", event.target.value)} /></div>
          <div className="field"><label>Model</label><select value={dcaDraft.model_type} onChange={(event) => updateDcaDraft("model_type", event.target.value)}><option value="normal">Normal DCA</option><option value="enhanced">Enhanced DCA</option></select></div>
          <div className="field"><label>Base amount</label><input value={dcaDraft.base_amount} onChange={(event) => updateDcaDraft("base_amount", Number(event.target.value))} /></div>
          <div className="field"><label>Frequency</label><select value={dcaDraft.contribution_frequency} onChange={(event) => updateDcaDraft("contribution_frequency", event.target.value)}><option value="weekly">Weekly</option><option value="monthly">Monthly</option><option value="quarterly">Quarterly</option></select></div>
          <div className="field"><label>Benchmark</label><select value={dcaDraft.preferred_benchmark} disabled={dcaDraft.model_type !== "enhanced"} onChange={(event) => updateDcaDraft("preferred_benchmark", event.target.value)}><option value="^GSPC">S&P 500</option><option value="^NDX">Nasdaq 100</option></select></div>
          <div className="field"><label>Market change %</label><input value={marketChange} onChange={(event) => { setApiDca(null); setMarketChange(Number(event.target.value)); }} disabled={dcaDraft.model_type !== "enhanced"} /></div>
          <div className="field"><label>Min multiplier</label><input value={dcaDraft.min_multiplier} onChange={(event) => updateDcaDraft("min_multiplier", Number(event.target.value))} disabled={dcaDraft.model_type !== "enhanced"} /></div>
          <div className="field"><label>Max multiplier</label><input value={dcaDraft.max_multiplier} onChange={(event) => updateDcaDraft("max_multiplier", Number(event.target.value))} disabled={dcaDraft.model_type !== "enhanced"} /></div>
          <div className="field"><label>VIX</label><input value={volatility} onChange={(event) => { setApiDca(null); setVolatility(Number(event.target.value)); }} disabled={dcaDraft.model_type !== "enhanced"} /></div>
        </div>
        <div className="actions"><Button onClick={savePlan}>Save plan</Button><Button className="primary" onClick={computeRecommendation}>Compute recommendation</Button></div>
      </section>
      <section className="panel recommendation-card">
        <span>Next investment amount</span>
        <strong>{money(dca.adjusted)}</strong>
        <p>{dca.reason} Multiplier: {Number(dca.multiplier).toFixed(2)}x.</p>
        {dca.allocationSuggestions?.length > 0 && (
          <div className="table-wrap compact-table">
            <table><thead><tr><th>Ticker</th><th className="num">Suggested</th><th className="num">Target</th><th className="num">Current</th></tr></thead><tbody>{dca.allocationSuggestions.map((suggestion) => <tr key={suggestion.ticker}><td>{suggestion.ticker}</td><td className="num">{money(toNumber(suggestion.suggested_amount))}</td><td className="num">{toNumber(suggestion.target_percent).toFixed(1)}%</td><td className="num">{toNumber(suggestion.current_percent).toFixed(1)}%</td></tr>)}</tbody></table>
          </div>
        )}
      </section>
    </div>
  );
}

function SettingsView({ apiBaseUrl, apiBaseDraft, setApiBaseDraft, setApiBaseUrl, connectBackend, apiLoading }) {
  function saveApiBase() {
    const next = apiBaseDraft.trim() || DEFAULT_API_BASE_URL;
    localStorage.setItem("trackerApiBaseUrl", next);
    setApiBaseUrl(next);
  }

  return (
    <div className="two-column-view">
      <section className="panel">
        <h3>Backend connection</h3>
        <div className="inline-field">
          <input value={apiBaseDraft} onChange={(event) => setApiBaseDraft(event.target.value)} />
          <Button onClick={saveApiBase}>Save URL</Button>
          <Button className="primary" disabled={apiLoading} onClick={connectBackend}>Reconnect</Button>
        </div>
        <p className="form-note">Default local backend: http://127.0.0.1:8000</p>
      </section>
      <section className="panel">
        <h3>Local data and backup</h3>
        <p>The launcher stores local release data in <code>.local/tracker-dev.sqlite3</code> unless <code>INVESTMENT_TRACKER_DATABASE_URL</code> is set. Copy that SQLite file before risky imports, schema work, or release upgrades.</p>
        <pre>{`# Windows PowerShell
Copy-Item .local\\tracker-dev.sqlite3 .local\\tracker-dev.backup.sqlite3

# Linux/WSL
cp .local/tracker-dev.sqlite3 .local/tracker-dev.backup.sqlite3`}</pre>
      </section>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
