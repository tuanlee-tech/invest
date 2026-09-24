import logging
import time
from datetime import date, timedelta
from typing import Any, Dict, Optional, Tuple

from app.core.engines.corporate_actions import get_adjusted_price
from app.core.retry import vnstock_retry

logger = logging.getLogger(__name__)

PRICE_TTL = 60.0      # seconds — latest-price cache window
HISTORY_TTL = 300.0   # seconds — OHLCV history cache window
_MAX_CACHE_ENTRIES = 512

# key -> (expires_at_epoch, value)
_CACHE: Dict[Tuple[Any, ...], Tuple[float, Any]] = {}


class MarketDataError(Exception):
    """Explicit provider/data failure (invalid symbol, malformed response, exhausted retries)."""

    def __init__(self, ticker: str, message: str, provider: str = "vnstock/VCI"):
        self.ticker = ticker
        self.provider = provider
        super().__init__(f"{provider} {ticker}: {message}")


def _cache_get(key: Tuple[Any, ...]) -> Optional[Any]:
    hit = _CACHE.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    return None


def _cache_put(key: Tuple[Any, ...], value: Any, ttl: float) -> None:
    if len(_CACHE) >= _MAX_CACHE_ENTRIES:
        _CACHE.clear()  # ponytail: naive full clear; LRU if this ever matters
    _CACHE[key] = (time.time() + ttl, value)


def _fetch_history(ticker: str, start: str, end: str):
    """Fetch OHLCV with short-lived cache. Raises provider errors (retried if transient)."""
    key = ("hist", ticker, start, end)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    from vnstock.api.quote import Quote
    df = Quote(symbol=ticker, source="VCI").history(start=start, end=end)
    if df is not None and not df.empty and "close" not in df.columns:
        raise MarketDataError(ticker, f"malformed response: columns={list(df.columns)}")
    _cache_put(key, df, HISTORY_TTL)
    return df


def _history(ticker: str, start: date, end: date):
    """Cached history with retry + explicit error wrapping."""
    try:
        return _fetch_history_wrapped(ticker, start.isoformat(), end.isoformat())
    except MarketDataError:
        raise
    except Exception as e:
        # Non-transient failures already bypassed retry; transient ones exhausted it.
        raise MarketDataError(ticker, f"{type(e).__name__}: {e}") from e


# vnstock_retry applied to the raw fetch so classification sees original exceptions
_fetch_history_wrapped = vnstock_retry(_fetch_history)


def get_latest_price(ticker: str) -> Optional[float]:
    """Latest close price in VND (cached PRICE_TTL). None when no data."""
    key = ("price", ticker, date.today())
    cached = _cache_get(key)
    if cached is not None:
        return cached

    df = _history(ticker, date.today() - timedelta(days=7), date.today())
    if df is None or df.empty:
        return None
    price = float(df["close"].iloc[-1])
    _cache_put(key, price, PRICE_TTL)
    return price


def get_return_pct(ticker: str, start: date, days: int, adjust_corporate_actions: bool = True) -> Optional[float]:
    """Realized return % over [start, start+days], optionally adjusted for actions in that window."""
    end = start + timedelta(days=days)
    df = _history(ticker, start, end)
    if df is None or df.empty or len(df) < 2:
        return None
    start_price = float(df["close"].iloc[0])
    end_price = float(df["close"].iloc[-1])

    # Adjust only for actions inside (start, end] — events before the window
    # affect both prices equally and must not distort the return.
    if adjust_corporate_actions:
        start_price = get_adjusted_price(ticker, start_price, end, since=start)

    return (end_price - start_price) / start_price


def get_benchmark_return(start: date, days: int) -> float:
    """VN-INDEX return over window. Fallback to 0 on error."""
    try:
        ret = get_return_pct("VNINDEX", start, days)
    except MarketDataError as e:
        logger.warning("Benchmark return unavailable: %s", e)
        return 0.0
    return ret if ret is not None else 0.0


def get_max_drawdown(ticker: str, start: date, days: int) -> Optional[float]:
    """Max drawdown % over window."""
    end = start + timedelta(days=days)
    df = _history(ticker, start, end)
    if df is None or df.empty:
        return None
    prices = df["close"].astype(float)
    peak = prices.cummax()
    drawdown = (prices - peak) / peak
    return float(drawdown.min())
