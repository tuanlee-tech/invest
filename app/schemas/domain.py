from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, date


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
