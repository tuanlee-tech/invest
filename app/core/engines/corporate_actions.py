"""Corporate actions adjustment — split, dividend, rights price normalization.

MANUAL DATA FORMAT (hand-curated; no verified live feed yet — see roadmap Phase 1):
    CORPORATE_ACTIONS_DB = {
        "HPG": [
            {"type": "split",   "date": "2022-01-15", "ratio": 2.0, "description": "2:1 stock split"},
            {"type": "dividend", "date": "2023-04-20", "amount": 2000, "description": "2,000 VND/share"},
            {"type": "rights",  "date": "2021-06-01", "ratio": 1.5, "description": "3:2 rights issue"},
            {"type": "bonus",   "date": "2020-05-01", "ratio": 1.1, "description": "10% bonus shares"},
        ]
    }
    - type: split | dividend | rights | bonus
    - date: ISO "YYYY-MM-DD" (ex-date)
    - ratio: price divisor for split/rights/bonus (2.0 = 2:1 → price / 2.0)
    - amount: cash VND per share for dividend

ADJUSTMENT WINDOW: only actions with `since < date <= as_of` are applied when a
window is given, so events before the window start do not distort a return
calculation. `since=None` (default) applies every action up to `as_of`.

Provenance: MANUAL. Rights without `ratio` and dividends without `amount` are
skipped (never fabricated).
"""
from datetime import date
from typing import Optional, List, Dict, Any
from enum import Enum


class ActionType(Enum):
    SPLIT = "split"
    DIVIDEND = "dividend"
    RIGHTS = "rights"
    BONUS = "bonus"


# Known corporate actions for VN market (manual curation)
# Format: {ticker: [{"type": "split", "date": "2023-01-15", "ratio": 2.0, "description": "2:1 stock split"}]}
CORPORATE_ACTIONS_DB: Dict[str, List[Dict[str, Any]]] = {
    "HPG": [
        {"type": "split", "date": "2022-01-15", "ratio": 2.0, "description": "2:1 stock split"},
    ],
    "VCB": [
        {"type": "split", "date": "2020-05-20", "ratio": 1.5, "description": "3:2 stock split"},
    ],
    "CTG": [
        {"type": "split", "date": "2019-11-10", "ratio": 1.5, "description": "3:2 stock split"},
    ],
    "MWG": [
        {"type": "split", "date": "2021-07-05", "ratio": 2.0, "description": "2:1 stock split"},
    ],
    "FPT": [
        {"type": "split", "date": "2020-03-15", "ratio": 1.5, "description": "3:2 stock split"},
    ],
    "MBB": [
        {"type": "split", "date": "2018-06-20", "ratio": 2.0, "description": "2:1 stock split"},
    ],
    "TCB": [
        {"type": "split", "date": "2019-04-10", "ratio": 1.5, "description": "3:2 stock split"},
    ],
    "BVH": [
        {"type": "split", "date": "2017-05-01", "ratio": 1.2, "description": "6:5 stock split"},
    ],
}

# Actions that divide price (share-count dilution events)
_RATIO_TYPES = {"split", "rights", "bonus"}


def get_actions_for_ticker(ticker: str, since: Optional[date] = None) -> List[Dict[str, Any]]:
    """Get corporate actions for a ticker; if `since` given, only actions after it."""
    actions = CORPORATE_ACTIONS_DB.get(ticker, [])
    if since:
        actions = [a for a in actions if date.fromisoformat(a["date"]) > since]
    # Sort by date ascending
    actions.sort(key=lambda a: a["date"])
    return actions


def _in_window(action_date: date, since: Optional[date], as_of: date) -> bool:
    """True when since < action_date <= as_of (or all dates <= as_of when since is None)."""
    if action_date > as_of:
        return False
    if since is not None and action_date <= since:
        return False
    return True


def adjust_price_for_splits(ticker: str, raw_price: float, as_of: date,
                            since: Optional[date] = None) -> float:
    """Adjust a raw price for split/rights/bonus events in (since, as_of].

    2:1 split → price halved. Events at or before `since` are ignored so a
    return window starting after them is not distorted.
    """
    adjusted = raw_price
    for action in get_actions_for_ticker(ticker, since=None):
        if action.get("type") not in _RATIO_TYPES:
            continue
        ratio = action.get("ratio")
        if not ratio:
            continue  # never fabricate a ratio
        action_date = date.fromisoformat(action["date"])
        if _in_window(action_date, since, as_of):
            adjusted = adjusted / float(ratio)
    return adjusted


def adjust_price_for_dividends(ticker: str, raw_price: float, as_of: date,
                               since: Optional[date] = None) -> float:
    """Subtract cash dividends paid in (since, as_of] from the price basis.

    total return = (end - (start - dividends)) / start == (end + div - start) / start
    """
    dividends = 0.0
    for action in get_actions_for_ticker(ticker, since=None):
        if action.get("type") != "dividend":
            continue
        amount = action.get("amount")
        if amount is None:
            continue  # skip incomplete records rather than guess
        action_date = date.fromisoformat(action["date"])
        if _in_window(action_date, since, as_of):
            dividends += float(amount)
    return raw_price - dividends


def get_adjusted_price(ticker: str, raw_price: float, as_of: date,
                       since: Optional[date] = None) -> float:
    """Fully adjusted price (splits/rights/bonus + dividends) in window (since, as_of]."""
    adjusted = adjust_price_for_splits(ticker, raw_price, as_of, since=since)
    adjusted = adjust_price_for_dividends(ticker, adjusted, as_of, since=since)
    return adjusted


def get_adjustment_factor(ticker: str, as_of: date, since: Optional[date] = None) -> float:
    """Cumulative ratio factor for split/rights/bonus in (since, as_of].

    Factor > 1 means the past price sits on a larger pre-dilution scale.
    """
    factor = 1.0
    for action in get_actions_for_ticker(ticker, since=None):
        if action.get("type") not in _RATIO_TYPES:
            continue
        ratio = action.get("ratio")
        if not ratio:
            continue
        action_date = date.fromisoformat(action["date"])
        if _in_window(action_date, since, as_of):
            factor *= float(ratio)
    return factor


def add_corporate_action(ticker: str, action_type: ActionType, action_date: date,
                         ratio: Optional[float] = None, amount: Optional[float] = None,
                         description: str = "") -> Dict[str, Any]:
    """Add a new corporate action to the database (runtime only)."""
    action = {
        "type": action_type.value,
        "date": action_date.isoformat(),
        "description": description,
    }
    if action_type in (ActionType.SPLIT, ActionType.RIGHTS, ActionType.BONUS) and ratio:
        action["ratio"] = ratio
    elif action_type == ActionType.DIVIDEND and amount:
        action["amount"] = amount

    if ticker not in CORPORATE_ACTIONS_DB:
        CORPORATE_ACTIONS_DB[ticker] = []

    CORPORATE_ACTIONS_DB[ticker].append(action)
    # Re-sort
    CORPORATE_ACTIONS_DB[ticker].sort(key=lambda a: a["date"])
    return action


def get_all_actions() -> Dict[str, List[Dict[str, Any]]]:
    """Get all corporate actions for all tickers."""
    return CORPORATE_ACTIONS_DB.copy()


# Test
if __name__ == "__main__":
    # Test HPG split adjustment
    hp_split = get_actions_for_ticker("HPG")
    print(f"HPG actions: {hp_split}")

    # Test adjustment factor
    factor = get_adjustment_factor("HPG", date(2024, 1, 1))
    print(f"HPG adjustment factor (as of 2024-01-01): {factor}")

    # Test price adjustment
    raw_price = 50000  # Pre-split price
    adjusted = adjust_price_for_splits("HPG", raw_price, date(2024, 1, 1))
    print(f"HPG raw price: {raw_price}, adjusted: {adjusted}")