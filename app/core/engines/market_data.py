from datetime import date, datetime, timedelta
from typing import Optional, Dict

from app.core.engines.corporate_actions import get_adjusted_price, get_adjustment_factor
from app.core.retry import vnstock_retry


@vnstock_retry
def get_latest_price(ticker: str) -> Optional[float]:
    """Get latest closing price from vnstock. Returns VND."""
    from vnstock.api.quote import Quote
    q = Quote(symbol=ticker, source='VCI')
    today = date.today()
    df = q.history(
        start=(today - timedelta(days=7)).isoformat(),
        end=today.isoformat(),
    )
    if df.empty:
        return None
    return float(df['close'].iloc[-1])


@vnstock_retry
def get_return_pct(ticker: str, start: date, days: int, adjust_corporate_actions: bool = True) -> Optional[float]:
    """Get realized return % for ticker over [start, start+days], optionally adjusted for splits."""
    from vnstock.api.quote import Quote
    q = Quote(symbol=ticker, source='VCI')
    end = start + timedelta(days=days)
    df = q.history(start=start.isoformat(), end=end.isoformat())
    if df.empty or len(df) < 2:
        return None
    start_price = float(df['close'].iloc[0])
    end_price = float(df['close'].iloc[-1])

    # Apply corporate action adjustment if requested
    if adjust_corporate_actions:
        # Adjust the start price forward to match the end price basis
        # If a 2:1 split happened between start and end, the end price is halved,
        # so we must adjust the start price down by the same ratio
        start_price = get_adjusted_price(ticker, start_price, end)

    return (end_price - start_price) / start_price


@vnstock_retry
def get_benchmark_return(start: date, days: int) -> float:
    """Get VN-INDEX return over window. Fallback to 0 on error."""
    ret = get_return_pct("VNINDEX", start, days)
    return ret if ret is not None else 0.0


@vnstock_retry
def get_max_drawdown(ticker: str, start: date, days: int) -> Optional[float]:
    """Get max drawdown % over window."""
    from vnstock.api.quote import Quote
    q = Quote(symbol=ticker, source='VCI')
    end = start + timedelta(days=days)
    df = q.history(start=start.isoformat(), end=end.isoformat())
    if df.empty:
        return None
    prices = df['close'].astype(float)
    peak = prices.cummax()
    drawdown = (prices - peak) / peak
    return float(drawdown.min())
