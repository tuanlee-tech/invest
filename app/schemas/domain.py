from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, date

PROPOSAL_ACTIONS = {"BUY", "WATCH", "AVOID", "HOLD", "ADD", "REDUCE", "EXIT"}
POSITION_SIZE_MAX_PCT = 10.0
HORIZON_MIN_DAYS = 1
HORIZON_MAX_DAYS = 3650


def validate_llm_proposal(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate raw LLM proposal output before any DB write.

    Raises ValueError with the reason — callers must drop the payload, never
    insert a partially-valid proposal. Returns the same dict for convenience.
    """
    if not isinstance(data, dict):
        raise ValueError(f"payload is not an object: {type(data).__name__}")

    action = str(data.get("action") or "").upper()
    if action not in PROPOSAL_ACTIONS:
        raise ValueError(f"invalid action {data.get('action')!r} (allowed: {sorted(PROPOSAL_ACTIONS)})")
    data["action"] = action

    try:
        confidence = float(data.get("confidence"))
    except (TypeError, ValueError):
        raise ValueError(f"confidence must be a number, got {data.get('confidence')!r}")
    if not 0 <= confidence <= 100:
        raise ValueError(f"confidence {confidence} out of range 0-100")
    data["confidence"] = confidence

    for field in ("entry_min", "entry_max", "target_min", "target_max", "stop_reference"):
        val = data.get(field)
        if val is None:
            continue
        try:
            val = float(val)
        except (TypeError, ValueError):
            raise ValueError(f"{field} must be a number, got {data.get(field)!r}")
        if val < 0:
            raise ValueError(f"{field} must be >= 0, got {val}")
        data[field] = val

    if data.get("entry_min") is not None and data.get("entry_max") is not None:
        if data["entry_min"] > data["entry_max"]:
            raise ValueError(f"entry_min {data['entry_min']} > entry_max {data['entry_max']}")
    if data.get("target_min") is not None and data.get("target_max") is not None:
        if data["target_min"] > data["target_max"]:
            raise ValueError(f"target_min {data['target_min']} > target_max {data['target_max']}")

    size = data.get("position_size_suggestion")
    if size is not None:
        try:
            size = float(size)
        except (TypeError, ValueError):
            raise ValueError(f"position_size_suggestion must be a number, got {data.get('position_size_suggestion')!r}")
        if not 0 <= size <= POSITION_SIZE_MAX_PCT:
            raise ValueError(f"position_size_suggestion {size} outside 0-{POSITION_SIZE_MAX_PCT}%")
        data["position_size_suggestion"] = size

    try:
        horizon = int(data.get("horizon_days") or 0)
    except (TypeError, ValueError):
        raise ValueError(f"horizon_days must be an integer, got {data.get('horizon_days')!r}")
    if not HORIZON_MIN_DAYS <= horizon <= HORIZON_MAX_DAYS:
        raise ValueError(f"horizon_days {horizon} outside {HORIZON_MIN_DAYS}-{HORIZON_MAX_DAYS}")
    data["horizon_days"] = horizon

    thesis = str(data.get("thesis") or "").strip()
    if not thesis:
        raise ValueError("thesis is empty")
    data["thesis"] = thesis

    conditions = data.get("invalidation_conditions")
    if not isinstance(conditions, list) or not conditions:
        raise ValueError("invalidation_conditions missing (need at least 1)")
    for c in conditions:
        if not isinstance(c, dict) or not str(c.get("description") or "").strip():
            raise ValueError(f"invalidation condition missing description: {c!r}")

    for list_field in ("catalysts", "risks"):
        val = data.get(list_field)
        if val is None:
            data[list_field] = []
        elif not isinstance(val, list):
            raise ValueError(f"{list_field} must be a list, got {type(val).__name__}")

    return data


class InvalidationCondition(BaseModel):
    condition_id: str
    description: str
    data_source: str
    check_method: str
    threshold_value: Optional[float] = None
    comparison: str
    lookback_days: int = 30
    severity: str = "CRITICAL"  # CRITICAL | WARNING
    status: str = "ACTIVE"  # ACTIVE | TRIGGERED | EXPIRED
    last_value: Optional[float] = None
    last_checked: Optional[datetime] = None


class ProposalCreate(BaseModel):
    ticker: str
    action: str  # BUY, WATCH, AVOID, HOLD, ADD, REDUCE, EXIT
    entry_min: Optional[float] = None
    entry_max: Optional[float] = None
    target_min: Optional[float] = None
    target_max: Optional[float] = None
    stop_reference: Optional[float] = None
    stop_method: str = "fixed_pct"
    horizon_days: int = 365
    confidence: float
    position_size_suggestion: Optional[float] = 5.0
    thesis: str
    catalysts: List[str] = []
    risks: List[str] = []
    invalidation_conditions: List[InvalidationCondition] = []
    evidence_refs: List[str] = []
    reasoning_summary: Optional[str] = None
    changed_from_previous: Optional[str] = None


class ProposalRevision(BaseModel):
    action: str
    entry_min: Optional[float] = None
    entry_max: Optional[float] = None
    target_min: Optional[float] = None
    target_max: Optional[float] = None
    stop_reference: Optional[float] = None
    stop_method: Optional[str] = "fixed_pct"
    horizon_days: Optional[int] = 365
    confidence: float
    position_size_suggestion: Optional[float] = None
    thesis: str
    catalysts: List[str] = []
    risks: List[str] = []
    invalidation_conditions: List[InvalidationCondition] = []
    evidence_refs: List[str] = []
    reasoning_summary: Optional[str] = None
    changed_from_previous: str  # Required explanation of changes


class PositionCreate(BaseModel):
    ticker: str
    quantity: float
    avg_buy_price: float
    buy_date: date
    fees: float = 0.0
    source_proposal_id: Optional[str] = None
    notes: Optional[str] = None


class TransactionCreate(BaseModel):
    ticker: str
    action: str  # BUY, SELL, ADD, REDUCE
    quantity: float
    price: float
    fees: float = 0.0
    transaction_date: date
    notes: Optional[str] = None


class EventCreate(BaseModel):
    occurred_at: datetime
    source_type: str
    source_url: str
    source_name: str
    headline: str
    summary: Optional[str] = None
    raw_text: Optional[str] = None
    classification: str = "FACT"
    entities: Optional[List[str]] = []
    causal_links: Optional[List[Dict[str, Any]]] = []
