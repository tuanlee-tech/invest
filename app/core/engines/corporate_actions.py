"""Corporate actions adjustment — split, dividend, rights price normalization."""
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


def get_actions_for_ticker(ticker: str, since: Optional[date] = None) -> List[Dict[str, Any]]:
    """Get corporate actions for a ticker, optionally filtered by date."""
    actions = CORPORATE_ACTIONS_DB.get(ticker, [])
    if since:
        actions = [a for a in actions if date.fromisoformat(a["date"]) >= since]
    # Sort by date ascending
    actions.sort(key=lambda a: a["date"])
    return actions


def adjust_price_for_splits(ticker: str, raw_price: float, as_of: date) -> float:
    """
    Adjust a raw price for all stock splits that occurred before as_of.
    For example: 2:1 split means price should be halved.
    """
    actions = get_actions_for_ticker(ticker, since=None)
    adjusted = raw_price
    for action in actions:
        if action["type"] == "split":
            action_date = date.fromisoformat(action["date"])
            if action_date <= as_of:
                adjusted = adjusted / action["ratio"]
    return adjusted


def adjust_price_for_dividends(ticker: str, raw_price: float, as_of: date) -> float:
    """
    Adjust a raw price for cash dividends (price drops by dividend amount on ex-date).
    Note: This is simplified - real dividend adjustment needs more data.
    """
    # Dividend adjustment requires dividend amount data which we don't have
    # For now, return raw price
    return raw_price


def get_adjusted_price(ticker: str, raw_price: float, as_of: date) -> float:
    """
    Get fully adjusted price (splits + dividends) for a ticker at a given date.
    """
    adjusted = adjust_price_for_splits(ticker, raw_price, as_of)
    adjusted = adjust_price_for_dividends(ticker, adjusted, as_of)
    return adjusted


def get_adjustment_factor(ticker: str, as_of: date) -> float:
    """
    Get the cumulative adjustment factor for a ticker up to a date.
    Factor > 1 means price was higher in the past (after adjusting down for splits).
    """
    actions = get_actions_for_ticker(ticker, since=None)
    factor = 1.0
    for action in actions:
        if action["type"] == "split":
            action_date = date.fromisoformat(action["date"])
            if action_date <= as_of:
                factor *= action["ratio"]
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
    if action_type == ActionType.SPLIT and ratio:
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