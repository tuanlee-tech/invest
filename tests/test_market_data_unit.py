"""Unit tests: price cache, transient-only retry, explicit provider errors, corporate actions.

No network — vnstock Quote is stubbed.
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from app.core.retry import retry, is_transient_error  # noqa: E402
from app.core.engines import market_data  # noqa: E402
from app.core.engines.market_data import (  # noqa: E402
    MarketDataError, get_latest_price, _CACHE,
)
from app.core.engines.corporate_actions import (  # noqa: E402
    CORPORATE_ACTIONS_DB, adjust_price_for_splits, adjust_price_for_dividends,
    get_adjusted_price, get_adjustment_factor, ActionType, add_corporate_action,
)


class _FakeQuote:
    calls = 0

    def __init__(self, symbol, source=None):
        self.symbol = symbol

    def history(self, start, end):
        _FakeQuote.calls += 1
        return pd.DataFrame({"close": [100.0, 105.0, 110.0]})


def _stub_quote(monkey_module=market_data):
    monkey_module._CACHE.clear()
    _FakeQuote.calls = 0

    # _fetch_history imports Quote from vnstock.api.quote at call time
    import vnstock.api.quote as quote_mod
    quote_mod.Quote = _FakeQuote
    return quote_mod


def test_price_cache_serves_second_call():
    _stub_quote()
    p1 = get_latest_price("HPG")
    p2 = get_latest_price("HPG")
    assert p1 == p2 == 110.0
    assert _FakeQuote.calls == 1, f"expected 1 provider call, got {_FakeQuote.calls}"


def test_cache_expires():
    _stub_quote()
    get_latest_price("HPG")
    # Force expiry
    for k in list(_CACHE):
        expires, val = _CACHE[k]
        _CACHE[k] = (0, val)
    get_latest_price("HPG")
    assert _FakeQuote.calls == 2, "expired entry must re-fetch"


def test_transient_retry_and_permanent_failfast():
    calls = {"n": 0}

    @retry(max_attempts=3, base_delay=0.001, jitter=False,
           exceptions=(Exception,), retry_if=is_transient_error)
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError("read timed out")
        return "ok"

    assert flaky() == "ok"
    assert calls["n"] == 3

    calls["n"] = 0

    @retry(max_attempts=3, base_delay=0.001, jitter=False,
           exceptions=(Exception,), retry_if=is_transient_error)
    def permanent():
        calls["n"] += 1
        raise ValueError("invalid symbol XYZ")

    try:
        permanent()
        assert False, "permanent error must raise"
    except ValueError:
        pass
    assert calls["n"] == 1, f"permanent error must not retry, got {calls['n']} calls"


def test_is_transient_classification():
    assert is_transient_error(TimeoutError("x"))
    assert is_transient_error(ConnectionError("refused"))
    assert is_transient_error(Exception("gateway timeout"))
    assert is_transient_error(Exception("HTTP 503 service unavailable"))
    assert not is_transient_error(ValueError("bad input"))
    assert not is_transient_error(KeyError("close"))
    assert not is_transient_error(MarketDataError("HPG", "malformed"))


def test_malformed_response_raises_explicit_error():
    class _MalformedQuote(_FakeQuote):
        def history(self, start, end):
            return pd.DataFrame({"open": [1.0]})  # no 'close'

    import vnstock.api.quote as quote_mod
    quote_mod.Quote = _MalformedQuote
    market_data._CACHE.clear()
    try:
        get_latest_price("HPG")
        assert False, "malformed response must raise MarketDataError"
    except MarketDataError as e:
        assert "malformed" in str(e)
        assert "HPG" in str(e)


def test_provider_exception_wrapped_as_market_data_error():
    class _BoomQuote(_FakeQuote):
        def history(self, start, end):
            raise RuntimeError("symbol does not exist: ZZTOP")

    import vnstock.api.quote as quote_mod
    quote_mod.Quote = _BoomQuote
    market_data._CACHE.clear()
    try:
        get_latest_price("ZZTOP")
        assert False, "must raise MarketDataError"
    except MarketDataError as e:
        assert "ZZTOP" in str(e) and "symbol does not exist" in str(e)


def test_corporate_actions_split_window():
    # HPG 2:1 split on 2022-01-15
    assert adjust_price_for_splits("HPG", 50000, date(2024, 1, 1)) == 25000
    # Window starting after the split → not applied
    assert adjust_price_for_splits("HPG", 50000, date(2024, 1, 1),
                                   since=date(2023, 1, 1)) == 50000
    # Window containing the split
    assert adjust_price_for_splits("HPG", 50000, date(2024, 1, 1),
                                   since=date(2021, 1, 1)) == 25000
    # Action after as_of → not applied
    assert adjust_price_for_splits("HPG", 50000, date(2021, 6, 1)) == 50000


def test_corporate_actions_dividend():
    add_corporate_action("TESTDIV", ActionType.DIVIDEND, date(2023, 4, 20),
                         amount=2000, description="2000 VND")
    assert adjust_price_for_dividends("TESTDIV", 50000, date(2024, 1, 1)) == 48000
    # Before ex-date → untouched
    assert adjust_price_for_dividends("TESTDIV", 50000, date(2023, 1, 1)) == 50000
    # Window starting after ex-date → dividend excluded from start basis
    assert adjust_price_for_dividends("TESTDIV", 50000, date(2024, 1, 1),
                                      since=date(2023, 5, 1)) == 50000


def test_corporate_actions_rights_and_factor():
    add_corporate_action("TESTRIGHT", ActionType.RIGHTS, date(2022, 6, 1),
                         ratio=1.5, description="3:2 rights")
    assert adjust_price_for_splits("TESTRIGHT", 45000, date(2023, 1, 1)) == 30000
    assert get_adjustment_factor("TESTRIGHT", date(2023, 1, 1)) == 1.5
    assert get_adjustment_factor("TESTRIGHT", date(2021, 1, 1)) == 1.0
    # rights without ratio is skipped, never fabricated
    CORPORATE_ACTIONS_DB["NORATIO"] = [{"type": "rights", "date": "2022-01-01",
                                         "description": "missing ratio"}]
    assert adjust_price_for_splits("NORATIO", 1000, date(2023, 1, 1)) == 1000


def test_get_adjusted_price_combined():
    add_corporate_action("TESTBOTH", ActionType.SPLIT, date(2022, 1, 15),
                         ratio=2.0, description="2:1")
    add_corporate_action("TESTBOTH", ActionType.DIVIDEND, date(2023, 4, 20),
                         amount=1000, description="1000 VND")
    # split then dividend: 50000 / 2 - 1000 = 24000
    got = get_adjusted_price("TESTBOTH", 50000, date(2024, 1, 1))
    assert got == 24000.0, got


if __name__ == "__main__":
    tests = [
        test_price_cache_serves_second_call,
        test_cache_expires,
        test_transient_retry_and_permanent_failfast,
        test_is_transient_classification,
        test_malformed_response_raises_explicit_error,
        test_provider_exception_wrapped_as_market_data_error,
        test_corporate_actions_split_window,
        test_corporate_actions_dividend,
        test_corporate_actions_rights_and_factor,
        test_get_adjusted_price_combined,
    ]
    passed = failed = 0
    for t in tests:
        try:
            print(f"Running {t.__name__}...", end=" ")
            t()
            print("PASS")
            passed += 1
        except Exception as e:
            print(f"FAIL: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
