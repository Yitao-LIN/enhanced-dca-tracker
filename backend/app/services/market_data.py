from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from app.domain import MarketSnapshot


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
