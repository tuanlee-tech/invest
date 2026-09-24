from datetime import datetime, timezone, date
from typing import Optional, List
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date,
    ForeignKey, Text, JSON, Index, create_engine
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from app.config import settings

Base = declarative_base()


class Fund(Base):
    __tablename__ = "funds"

    id = Column(String(50), primary_key=True)  # VEIL, VESAF, VCBF-BCF, PYN
    name = Column(String(255), nullable=False)
    manager = Column(String(255), nullable=False)
    fund_type = Column(String(50), default="open_end")
    strategy = Column(Text, nullable=True)
    base_url = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=datetime.now(timezone.utc))

    holdings_snapshots = relationship("FundHoldingSnapshot", back_populates="fund", cascade="all, delete-orphan")


class FundHoldingSnapshot(Base):
    __tablename__ = "fund_holding_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fund_id = Column(String(50), ForeignKey("funds.id"), nullable=False)
    as_of_date = Column(Date, nullable=False)
    retrieved_at = Column(DateTime, default=datetime.now(timezone.utc))
    source_url = Column(String(512), nullable=True)
    source_hash = Column(String(64), nullable=True)  # sha256
    reporting_period = Column(String(32), nullable=True)  # e.g. "2026-07"
    effective_date = Column(Date, nullable=True)  # date the holdings are effective (may differ from as_of_date)
    raw_text = Column(Text, nullable=True)
    holdings_json = Column(JSON, nullable=False)  # list of {ticker, weight_pct, sector, ...}

    fund = relationship("Fund", back_populates="holdings_snapshots")

    __table_args__ = (
        Index("idx_fund_as_of", "fund_id", "as_of_date", unique=True),
    )


class Security(Base):
    """Normalized master table for tracked securities"""
    __tablename__ = "securities"

    ticker = Column(String(20), primary_key=True)
    name = Column(String(255), nullable=False)
    exchange = Column(String(20), nullable=True)  # HOSE, HNX, UPCoM
    sector = Column(String(100), nullable=True)
    industry = Column(String(100), nullable=True)
    in_fund_universe = Column(Boolean, default=False)
    last_updated = Column(DateTime, default=datetime.now(timezone.utc))


class Event(Base):
    """News, macro, disclosure, corporate actions with provenance"""
    __tablename__ = "events"

    id = Column(String(64), primary_key=True)  # SHA256 or uuid
    occurred_at = Column(DateTime, nullable=False)
    source_type = Column(String(50), nullable=False)  # news, macro, disclosure, corporate_action
    source_url = Column(String(512), nullable=False)
    source_name = Column(String(100), nullable=False)
    headline = Column(String(512), nullable=False)
    summary = Column(Text, nullable=True)
    raw_text = Column(Text, nullable=True)

    # Classification: FACT / COMPUTED / INFERENCE / FORECAST
    classification = Column(String(20), default="FACT")

    # Entities extracted: JSON list of tickers, sectors, commodities
    entities = Column(JSON, nullable=True)

    # Causal chain analysis: JSON list of {target_ticker, direction, confidence, thesis, mechanism}
    causal_links = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_event_time", "occurred_at"),
        Index("idx_event_source", "source_type"),
    )


class Proposal(Base):
    """Investment Proposal contract with strict versioning and provenance"""
    __tablename__ = "proposals"

    id = Column(String(64), primary_key=True)  # e.g., FPT-2026-001-v1
    proposal_group_id = Column(String(50), nullable=False)  # e.g., FPT-2026-001
    ticker = Column(String(20), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    parent_version = Column(Integer, nullable=True)

    # DRAFT | REVIEWED | ACTIVE | REVISED | EXECUTED | EXPIRED | INVALIDATED | CLOSED
    status = Column(String(30), default="ACTIVE")

    # BUY | WATCH | AVOID | HOLD | ADD | REDUCE | EXIT
    action = Column(String(20), nullable=False)

    # Levels (deterministic or rule-bounded)
    entry_min = Column(Float, nullable=True)
    entry_max = Column(Float, nullable=True)
    target_min = Column(Float, nullable=True)
    target_max = Column(Float, nullable=True)
    stop_reference = Column(Float, nullable=True)
    stop_method = Column(String(50), default="fixed_pct")  # fixed_pct, trailing_atr, structure

    horizon_days = Column(Integer, default=365)  # Default > 1 year
    valid_from = Column(DateTime, nullable=False)
    valid_until = Column(DateTime, nullable=False)

    confidence = Column(Float, nullable=False)  # 0 to 100
    position_size_suggestion = Column(Float, nullable=True)  # suggested % of portfolio

    thesis = Column(Text, nullable=False)
    catalysts = Column(JSON, nullable=True)  # list of strings
    risks = Column(JSON, nullable=True)      # list of strings
    invalidation_conditions = Column(JSON, nullable=True)  # list of condition objects

    evidence_refs = Column(JSON, nullable=True)  # list of event_ids
    data_snapshot_id = Column(String(64), nullable=True)
    model_run_id = Column(String(64), nullable=True)
    reasoning_summary = Column(Text, nullable=True)

    # Audit & change tracking
    created_at = Column(DateTime, default=datetime.now(timezone.utc))
    changed_from_previous = Column(Text, nullable=True)

    __table_args__ = (
        Index("idx_proposal_ticker", "ticker"),
        Index("idx_proposal_group", "proposal_group_id", "version", unique=True),
    )


class Position(Base):
    """User active or historical portfolio holdings"""
    __tablename__ = "positions"

    id = Column(String(50), primary_key=True)  # uuid
    ticker = Column(String(20), nullable=False)
    quantity = Column(Float, nullable=False)
    avg_buy_price = Column(Float, nullable=False)
    buy_date = Column(Date, nullable=False)
    fees = Column(Float, default=0.0)

    # ACTIVE | PARTIALLY_CLOSED | CLOSED
    status = Column(String(30), default="ACTIVE")

    source_proposal_id = Column(String(64), nullable=True)
    current_action = Column(String(20), default="HOLD")  # ADD, HOLD, REDUCE, EXIT
    thesis_health = Column(String(30), default="HEALTHY")  # HEALTHY, AT_RISK, INVALIDATED
    notes = Column(Text, nullable=True)

    closed_at = Column(DateTime, nullable=True)
    closed_price = Column(Float, nullable=True)
    realized_pnl = Column(Float, nullable=True)

    updated_at = Column(DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))
    created_at = Column(DateTime, default=datetime.now(timezone.utc))

    transactions = relationship("Transaction", back_populates="position", cascade="all, delete-orphan")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String(50), primary_key=True)
    position_id = Column(String(50), ForeignKey("positions.id"), nullable=False)
    ticker = Column(String(20), nullable=False)
    action = Column(String(20), nullable=False)  # BUY, SELL, ADD, REDUCE
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    fees = Column(Float, default=0.0)
    transaction_date = Column(Date, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now(timezone.utc))

    position = relationship("Position", back_populates="transactions")


class Watchlist(Base):
    __tablename__ = "watchlist"

    ticker = Column(String(20), primary_key=True)
    added_at = Column(DateTime, default=datetime.now(timezone.utc))
    notes = Column(Text, nullable=True)
    priority = Column(String(20), default="NORMAL")  # HIGH, NORMAL, LOW


class ProposalEvaluation(Base):
    """Evaluation Engine record: strictly point-in-time, outcome metrics"""
    __tablename__ = "proposal_evaluations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    proposal_id = Column(String(64), nullable=False)
    ticker = Column(String(20), nullable=False)
    evaluated_at = Column(DateTime, default=datetime.now(timezone.utc))

    # Realized price metrics
    evaluation_window_days = Column(Integer, nullable=False)
    entry_hit = Column(Boolean, default=False)
    target_hit = Column(Boolean, default=False)
    stop_hit = Column(Boolean, default=False)

    realized_return_pct = Column(Float, nullable=True)
    benchmark_return_pct = Column(Float, nullable=True)  # VN-INDEX return over same period
    alpha_pct = Column(Float, nullable=True)
    max_drawdown_pct = Column(Float, nullable=True)
    mfe_pct = Column(Float, nullable=True)  # Maximum Favorable Excursion
    mae_pct = Column(Float, nullable=True)  # Maximum Adverse Excursion

    outcome_status = Column(String(30), nullable=False)  # SUCCESS, FAILED, EXPIRED, IN_PROGRESS
    notes = Column(Text, nullable=True)

    __table_args__ = (
        Index("idx_eval_proposal", "proposal_id"),
        Index("idx_eval_ticker", "ticker"),
    )


class PositionDecision(Base):
    """Append-only journal of every portfolio re-evaluation decision (incl. unchanged HOLDs)."""
    __tablename__ = "position_decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    position_id = Column(String(50), nullable=False)
    ticker = Column(String(20), nullable=False)
    action = Column(String(20), nullable=False)          # ADD | HOLD | REDUCE | EXIT
    thesis_health = Column(String(30), nullable=False)   # HEALTHY | AT_RISK | INVALIDATED
    invalidation_triggered = Column(Boolean, default=False)
    current_price = Column(Float, nullable=True)
    triggered_conditions = Column(JSON, nullable=True)   # list of condition dicts
    reason = Column(Text, nullable=True)
    source = Column(String(20), default="reeval")        # reeval | manual
    decided_at = Column(DateTime, default=datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_decision_position", "position_id", "decided_at"),
        Index("idx_decision_ticker", "ticker"),
    )


class JobRun(Base):
    """Scheduler/job execution history: id, window, status, error, record counts."""
    __tablename__ = "job_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(64), nullable=False)          # unique per run (uuid)
    job_name = Column(String(100), nullable=False)
    started_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(20), default="RUNNING")       # RUNNING | SUCCESS | FAILED
    error = Column(Text, nullable=True)
    record_counts = Column(JSON, nullable=True)          # scalar summary of job result

    __table_args__ = (
        Index("idx_jobrun_name_time", "job_name", "started_at"),
    )


# Database setup
engine = create_engine(settings.DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
