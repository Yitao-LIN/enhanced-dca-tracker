from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.domain import MarketSnapshot


DEFAULT_BENCHMARKS = {
    "^GSPC": "S&P 500",
    "^NDX": "Nasdaq 100",
}


@dataclass(frozen=True)
class HistoricalMarketPrice:
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


class MarketDataProvider:
    def quote(self, symbol: str) -> MarketSnapshot:
        raise NotImplementedError


class StaticMarketDataProvider(MarketDataProvider):
    def __init__(self, quotes: dict[str, Decimal] | None = None) -> None:
        self.quotes = quotes or {}

    def quote(self, symbol: str) -> MarketSnapshot:
        close = self.quotes.get(symbol.upper(), Decimal("0"))
        return MarketSnapshot(symbol=symbol.upper(), close=close, previous_close=None, as_of=datetime.now(timezone.utc))


class YFinanceMarketDataProvider(MarketDataProvider):
    def quote(self, symbol: str) -> MarketSnapshot:
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

    def historical_prices(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        currency: str = "USD",
        source: str = "yfinance",
    ) -> list[HistoricalMarketPrice]:
        try:
            import yfinance as yf
        except ImportError as exc:
            raise RuntimeError("Install yfinance to use live market data.") from exc

        history = yf.download(
            symbol,
            start=start_date.isoformat(),
            end=(end_date + timedelta(days=1)).isoformat(),
            progress=False,
            auto_adjust=False,
            threads=False,
        )
        if history.empty:
            raise ValueError(f"No historical market data returned for {symbol}")

        return normalize_yfinance_history(
            symbol=symbol,
            history=history,
            currency=currency,
            source=source,
        )


def normalize_yfinance_history(
    symbol: str,
    history: object,
    currency: str = "USD",
    source: str = "yfinance",
) -> list[HistoricalMarketPrice]:
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


def _optional_decimal(value: object) -> Decimal | None:
    if value is None or value != value:
        return None
    return Decimal(str(value))


def _optional_int(value: object) -> int | None:
    if value is None or value != value:
        return None
    return int(value)


def _single_symbol_history_frame(symbol: str, history: object) -> object:
    columns = getattr(history, "columns", None)
    if not hasattr(columns, "nlevels") or columns.nlevels <= 1:
        return history

    normalized_symbol = symbol.upper()
    for level in range(columns.nlevels):
        level_values = [str(value).upper() for value in columns.get_level_values(level)]
        if normalized_symbol in level_values:
            return history.xs(symbol, axis=1, level=level, drop_level=True)
    return history
