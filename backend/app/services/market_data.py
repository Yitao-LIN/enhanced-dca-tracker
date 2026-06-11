"""@file
@brief Market-data provider abstractions and yfinance normalization helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import logging

from app.domain import MarketSnapshot


DEFAULT_BENCHMARKS = {
    "^GSPC": "S&P 500",
    "^NDX": "Nasdaq 100",
}


@dataclass(frozen=True)
class HistoricalMarketPrice:
    """@brief Normalized daily market-price point from a provider."""

    symbol: str
    price_date: date
    close: Decimal
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    adjusted_close: Decimal | None = None
    volume: int | None = None
    currency: str = "USD"
    source: str = "yfinance"


@dataclass(frozen=True)
class IntradayMarketPrice:
    """@brief Normalized intraday market-price point from a provider."""

    symbol: str
    price_at: datetime
    interval: str
    close: Decimal
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    adjusted_close: Decimal | None = None
    volume: int | None = None
    currency: str = "USD"
    source: str = "yfinance"


@dataclass(frozen=True)
class SymbolSearchResult:
    """@brief Normalized ticker-search candidate."""

    symbol: str
    name: str | None = None
    exchange: str | None = None
    quote_type: str | None = None
    currency: str | None = None
    score: float | None = None
    source: str = "yfinance"


class MarketDataProvider:
    """@brief Interface for market quote providers."""

    def quote(self, symbol: str) -> MarketSnapshot:
        """@brief Fetch the latest quote for a symbol."""
        raise NotImplementedError


class StaticMarketDataProvider(MarketDataProvider):
    """@brief Deterministic in-memory market-data provider used by tests."""

    def __init__(self, quotes: dict[str, Decimal] | None = None) -> None:
        self.quotes = quotes or {}

    def quote(self, symbol: str) -> MarketSnapshot:
        close = self.quotes.get(symbol.upper(), Decimal("0"))
        return MarketSnapshot(symbol=symbol.upper(), close=close, previous_close=None, as_of=datetime.now(timezone.utc))


class YFinanceMarketDataProvider(MarketDataProvider):
    """@brief yfinance-backed provider for quotes, history, intraday data, and search."""

    def quote(self, symbol: str) -> MarketSnapshot:
        """@brief Fetch a recent quote from yfinance and derive percentage-change inputs."""
        try:
            import yfinance as yf
        except ImportError as exc:
            raise RuntimeError("Install yfinance to use live market data.") from exc

        ticker = yf.Ticker(symbol)
        history = ticker.history(period="5d")
        if history.empty:
            raise ValueError(f"No market data returned for {symbol}")

        closes = list(history["Close"].dropna())
        close = Decimal(str(closes[-1]))
        previous_close = Decimal(str(closes[-2])) if len(closes) > 1 else None
        currency = ticker.fast_info.get("currency") or "EUR"
        return MarketSnapshot(
            symbol=symbol.upper(),
            close=close,
            previous_close=previous_close,
            as_of=datetime.now(timezone.utc),
            currency=currency,
        )

    def search_symbols(self, query: str, limit: int = 5) -> list[SymbolSearchResult]:
        """@brief Search Yahoo Finance for ticker candidates matching a free-text label."""
        try:
            import yfinance as yf
        except ImportError as exc:
            raise RuntimeError("Install yfinance to use symbol search.") from exc
        if not hasattr(yf, "Search"):
            raise RuntimeError("Upgrade yfinance to a version with Search support.")

        search = yf.Search(
            query,
            max_results=limit,
            news_count=0,
            lists_count=0,
            include_cb=False,
            include_nav_links=False,
            include_research=False,
            include_cultural_assets=False,
            timeout=10,
            raise_errors=True,
        )
        return normalize_yfinance_search_quotes(search.quotes, limit=limit)

    def historical_prices(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        currency: str = "USD",
        source: str = "yfinance",
    ) -> list[HistoricalMarketPrice]:
        """@brief Fetch and normalize daily historical prices from yfinance."""
        try:
            import yfinance as yf
        except ImportError as exc:
            raise RuntimeError("Install yfinance to use live market data.") from exc

        yfinance_logger = logging.getLogger("yfinance")
        previous_level = yfinance_logger.level
        yfinance_logger.setLevel(logging.CRITICAL)
        try:
            history = yf.download(
                symbol,
                start=start_date.isoformat(),
                end=(end_date + timedelta(days=1)).isoformat(),
                progress=False,
                auto_adjust=False,
                threads=False,
            )
        finally:
            yfinance_logger.setLevel(previous_level)
        if history.empty:
            raise ValueError(f"No historical market data returned for {symbol}")

        return normalize_yfinance_history(
            symbol=symbol,
            history=history,
            currency=currency,
            source=source,
        )

    def intraday_prices(
        self,
        symbol: str,
        start_at: datetime,
        end_at: datetime,
        interval: str = "30m",
        currency: str = "USD",
        source: str = "yfinance",
    ) -> list[IntradayMarketPrice]:
        """@brief Fetch and normalize intraday historical prices from yfinance."""
        try:
            import yfinance as yf
        except ImportError as exc:
            raise RuntimeError("Install yfinance to use live market data.") from exc

        yfinance_logger = logging.getLogger("yfinance")
        previous_level = yfinance_logger.level
        yfinance_logger.setLevel(logging.CRITICAL)
        try:
            history = yf.download(
                symbol,
                start=start_at.isoformat(),
                end=end_at.isoformat(),
                interval=interval,
                progress=False,
                auto_adjust=False,
                threads=False,
            )
        finally:
            yfinance_logger.setLevel(previous_level)
        if history.empty:
            raise ValueError(f"No intraday market data returned for {symbol}")

        return normalize_yfinance_intraday_history(
            symbol=symbol,
            history=history,
            interval=interval,
            currency=currency,
            source=source,
        )


def normalize_yfinance_search_quotes(quotes: list[dict[str, object]], limit: int = 5) -> list[SymbolSearchResult]:
    """@brief Convert raw yfinance search quotes into unique normalized candidates."""
    results: list[SymbolSearchResult] = []
    seen_symbols: set[str] = set()
    for index, quote in enumerate(quotes):
        raw_symbol = quote.get("symbol")
        if raw_symbol is None:
            continue
        symbol = str(raw_symbol).strip().upper()
        if not symbol or symbol in seen_symbols:
            continue
        seen_symbols.add(symbol)
        results.append(
            SymbolSearchResult(
                symbol=symbol,
                name=_optional_text(
                    quote.get("longname")
                    or quote.get("shortname")
                    or quote.get("displayName")
                    or quote.get("name")
                ),
                exchange=_optional_text(quote.get("exchange")),
                quote_type=_optional_text(quote.get("quoteType")),
                currency=_optional_text(quote.get("currency"), upper=True),
                score=_optional_float(quote.get("score"), default=float(max(limit - index, 0))),
                source="yfinance",
            )
        )
        if len(results) >= limit:
            break
    return results


def normalize_yfinance_history(
    symbol: str,
    history: object,
    currency: str = "USD",
    source: str = "yfinance",
) -> list[HistoricalMarketPrice]:
    """@brief Convert a yfinance daily history frame into provider-neutral points."""
    history = _single_symbol_history_frame(symbol, history)
    points: list[HistoricalMarketPrice] = []
    for index, row in history.iterrows():
        close = _optional_decimal(row.get("Close"))
        if close is None:
            continue
        points.append(
            HistoricalMarketPrice(
                symbol=symbol.upper(),
                price_date=index.date(),
                open=_optional_decimal(row.get("Open")),
                high=_optional_decimal(row.get("High")),
                low=_optional_decimal(row.get("Low")),
                close=close,
                adjusted_close=_optional_decimal(row.get("Adj Close")),
                volume=_optional_int(row.get("Volume")),
                currency=currency.upper(),
                source=source.lower(),
            )
        )
    return points


def normalize_yfinance_intraday_history(
    symbol: str,
    history: object,
    interval: str,
    currency: str = "USD",
    source: str = "yfinance",
) -> list[IntradayMarketPrice]:
    """@brief Convert a yfinance intraday history frame into provider-neutral points."""
    history = _single_symbol_history_frame(symbol, history)
    points: list[IntradayMarketPrice] = []
    for index, row in history.iterrows():
        close = _optional_decimal(row.get("Close"))
        if close is None:
            continue
        price_at = _index_to_utc_datetime(index)
        points.append(
            IntradayMarketPrice(
                symbol=symbol.upper(),
                price_at=price_at,
                interval=interval.lower(),
                open=_optional_decimal(row.get("Open")),
                high=_optional_decimal(row.get("High")),
                low=_optional_decimal(row.get("Low")),
                close=close,
                adjusted_close=_optional_decimal(row.get("Adj Close")),
                volume=_optional_int(row.get("Volume")),
                currency=currency.upper(),
                source=source.lower(),
            )
        )
    return points


def _index_to_utc_datetime(value: object) -> datetime:
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if not isinstance(value, datetime):
        value = datetime.fromisoformat(str(value))
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _optional_decimal(value: object) -> Decimal | None:
    if value is None or value != value:
        return None
    return Decimal(str(value))


def _optional_float(value: object, default: float | None = None) -> float | None:
    if value is None or value != value:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _optional_int(value: object) -> int | None:
    if value is None or value != value:
        return None
    return int(value)


def _optional_text(value: object, upper: bool = False) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text.upper() if upper else text


def _single_symbol_history_frame(symbol: str, history: object) -> object:
    """@brief Select one symbol from yfinance's sometimes-multi-index history frame."""
    columns = getattr(history, "columns", None)
    if not hasattr(columns, "nlevels") or columns.nlevels <= 1:
        return history

    normalized_symbol = symbol.upper()
    for level in range(columns.nlevels):
        level_values = [str(value).upper() for value in columns.get_level_values(level)]
        if normalized_symbol in level_values:
            return history.xs(symbol, axis=1, level=level, drop_level=True)
    return history
