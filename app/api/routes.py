from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, date, timedelta

from app.core.models.schema import get_db, Fund, FundHoldingSnapshot, Security, Event, Proposal, Position, Transaction, Watchlist, ProposalEvaluation
from app.schemas.domain import ProposalCreate, ProposalRevision, PositionCreate, TransactionCreate, EventCreate


api = APIRouter(prefix="/api", tags=["api"])


# ============================================================
# FUNDS & HOLDINGS
# ============================================================

@api.get("/funds")
def list_funds(db: Session = Depends(get_db)):
    return db.query(Fund).all()


@api.get("/funds/{fund_id}/holdings")
def get_fund_holdings(
    fund_id: str,
    as_of: Optional[date] = None,
    db: Session = Depends(get_db)
):
    q = db.query(FundHoldingSnapshot).filter(FundHoldingSnapshot.fund_id == fund_id)
    if as_of:
        q = q.filter(FundHoldingSnapshot.as_of_date <= as_of)
    return q.order_by(FundHoldingSnapshot.as_of_date.desc()).all()


@api.get("/funds/{fund_id}/holdings/latest")
def get_latest_holdings(fund_id: str, db: Session = Depends(get_db)):
    snapshot = db.query(FundHoldingSnapshot).filter(
        FundHoldingSnapshot.fund_id == fund_id
    ).order_by(FundHoldingSnapshot.as_of_date.desc()).first()
    if not snapshot:
        raise HTTPException(404, "No holdings snapshot found")
    return snapshot


# ============================================================
# SECURITIES (Watched Universe)
# ============================================================

@api.get("/securities")
def list_securities(
    in_fund_universe: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    q = db.query(Security)
    if in_fund_universe is not None:
        q = q.filter(Security.in_fund_universe == in_fund_universe)
    return q.all()


@api.get("/securities/{ticker}")
def get_security(ticker: str, db: Session = Depends(get_db)):
    sec = db.query(Security).filter(Security.ticker == ticker).first()
    if not sec:
        raise HTTPException(404, "Security not found")
    return sec


# ============================================================
# EVENTS
# ============================================================

@api.get("/events")
def list_events(
    source_type: Optional[str] = None,
    ticker: Optional[str] = None,
    since: Optional[datetime] = None,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    q = db.query(Event)
    if source_type:
        q = q.filter(Event.source_type == source_type)
    if since:
        q = q.filter(Event.occurred_at >= since)
    if ticker:
        # Filter events that mention this ticker
        q = q.filter(Event.entities.contains([ticker]))
    return q.order_by(Event.occurred_at.desc()).limit(limit).all()


@api.get("/events/{event_id}")
def get_event(event_id: str, db: Session = Depends(get_db)):
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(404, "Event not found")
    return event


# ============================================================
# PROPOSALS (Investment Proposals with versioning)
# ============================================================

@api.get("/proposals")
def list_proposals(
    ticker: Optional[str] = None,
    status: Optional[str] = None,
    group_id: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    q = db.query(Proposal)
    if ticker:
        q = q.filter(Proposal.ticker == ticker)
    if status:
        q = q.filter(Proposal.status == status)
    if group_id:
        q = q.filter(Proposal.proposal_group_id == group_id)
    return q.order_by(Proposal.created_at.desc()).limit(limit).all()


@api.get("/proposals/group/{group_id}")
def get_proposal_group(group_id: str, db: Session = Depends(get_db)):
    return db.query(Proposal).filter(
        Proposal.proposal_group_id == group_id
    ).order_by(Proposal.version).all()


@api.get("/proposals/{proposal_id}")
def get_proposal(proposal_id: str, db: Session = Depends(get_db)):
    p = db.query(Proposal).filter(Proposal.id == proposal_id).first()
    if not p:
        raise HTTPException(404, "Proposal not found")
    return p


@api.post("/proposals")
def create_proposal(data: ProposalCreate, db: Session = Depends(get_db)):
    # Generate group ID if new proposal
    import uuid
    group_id = f"{data.ticker}-{datetime.now().strftime('%Y')}-{str(uuid.uuid4())[:8]}"
    proposal_id = f"{group_id}-v1"
    
    proposal = Proposal(
        id=proposal_id,
        proposal_group_id=group_id,
        ticker=data.ticker,
        version=1,
        status="ACTIVE",
        action=data.action,
        entry_min=data.entry_min,
        entry_max=data.entry_max,
        target_min=data.target_min,
        target_max=data.target_max,
        stop_reference=data.stop_reference,
        stop_method=data.stop_method,
        horizon_days=data.horizon_days,
        valid_from=datetime.utcnow(),
        valid_until=datetime.utcnow() + timedelta(days=data.horizon_days),
        confidence=data.confidence,
        position_size_suggestion=data.position_size_suggestion,
        thesis=data.thesis,
        catalysts=data.catalysts,
        risks=data.risks,
        invalidation_conditions=[c.model_dump() for c in data.invalidation_conditions],
        evidence_refs=data.evidence_refs,
        reasoning_summary=data.reasoning_summary,
        changed_from_previous=data.changed_from_previous or "Initial proposal",
    )
    db.add(proposal)
    db.commit()
    return proposal


@api.post("/proposals/{proposal_id}/revise")
def revise_proposal(proposal_id: str, data: ProposalRevision, db: Session = Depends(get_db)):
    original = db.query(Proposal).filter(Proposal.id == proposal_id).first()
    if not original:
        raise HTTPException(404, "Proposal not found")
    
    # Create new version
    new_version = original.version + 1
    new_id = f"{original.proposal_group_id}-v{new_version}"
    
    # Mark original as REVISED
    original.status = "REVISED"
    
    revision = Proposal(
        id=new_id,
        proposal_group_id=original.proposal_group_id,
        ticker=original.ticker,
        version=new_version,
        parent_version=original.version,
        status="ACTIVE",
        action=data.action,
        entry_min=data.entry_min,
        entry_max=data.entry_max,
        target_min=data.target_min,
        target_max=data.target_max,
        stop_reference=data.stop_reference,
        stop_method=data.stop_method or original.stop_method,
        horizon_days=data.horizon_days or original.horizon_days,
        valid_from=datetime.utcnow(),
        valid_until=datetime.utcnow() + timedelta(days=data.horizon_days or original.horizon_days),
        confidence=data.confidence,
        position_size_suggestion=data.position_size_suggestion or original.position_size_suggestion,
        thesis=data.thesis,
        catalysts=data.catalysts,
        risks=data.risks,
        invalidation_conditions=[c.model_dump() for c in data.invalidation_conditions],
        evidence_refs=data.evidence_refs,
        reasoning_summary=data.reasoning_summary,
        changed_from_previous=data.changed_from_previous,
    )
    db.add(revision)
    db.commit()
    # Refresh to ensure all fields are loaded
    db.refresh(revision)
    return revision


# ============================================================
# PORTFOLIO POSITIONS
# ============================================================

@api.get("/positions")
def list_positions(status: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(Position)
    if status:
        q = q.filter(Position.status == status)
    return q.order_by(Position.created_at.desc()).all()


@api.get("/positions/{position_id}")
def get_position(position_id: str, db: Session = Depends(get_db)):
    pos = db.query(Position).filter(Position.id == position_id).first()
    if not pos:
        raise HTTPException(404, "Position not found")
    return pos


@api.post("/positions")
def create_position(data: PositionCreate, db: Session = Depends(get_db)):
    import uuid
    pos_id = str(uuid.uuid4())[:8]
    
    pos = Position(
        id=pos_id,
        ticker=data.ticker,
        quantity=data.quantity,
        avg_buy_price=data.avg_buy_price,
        buy_date=data.buy_date,
        fees=data.fees,
        source_proposal_id=data.source_proposal_id,
        notes=data.notes,
    )
    db.add(pos)
    db.commit()
    return pos


@api.post("/positions/{position_id}/transact")
def add_transaction(position_id: str, data: TransactionCreate, db: Session = Depends(get_db)):
    pos = db.query(Position).filter(Position.id == position_id).first()
    if not pos:
        raise HTTPException(404, "Position not found")
    
    import uuid
    tx_id = str(uuid.uuid4())[:8]
    
    tx = Transaction(
        id=tx_id,
        position_id=position_id,
        ticker=data.ticker,
        action=data.action,
        quantity=data.quantity,
        price=data.price,
        fees=data.fees,
        transaction_date=data.transaction_date,
        notes=data.notes,
    )
    
    # Update position quantity and avg price
    if data.action in ["BUY", "ADD"]:
        total_cost = pos.quantity * pos.avg_buy_price + data.quantity * data.price + data.fees
        pos.quantity += data.quantity
        pos.avg_buy_price = total_cost / pos.quantity
    elif data.action in ["SELL", "REDUCE"]:
        pos.quantity -= data.quantity
        if pos.quantity <= 0:
            pos.status = "CLOSED"
            pos.closed_at = datetime.utcnow()
            pos.closed_price = data.price
            pos.realized_pnl = (data.price - pos.avg_buy_price) * data.quantity - data.fees
    
    db.add(tx)
    db.commit()
    return tx


@api.get("/positions/{position_id}/transactions")
def get_position_transactions(position_id: str, db: Session = Depends(get_db)):
    pos = db.query(Position).filter(Position.id == position_id).first()
    if not pos:
        raise HTTPException(404, "Position not found")
    return pos.transactions


# ============================================================
# WATCHLIST
# ============================================================

@api.get("/watchlist")
def get_watchlist(db: Session = Depends(get_db)):
    return db.query(Watchlist).order_by(Watchlist.added_at.desc()).all()


@api.post("/watchlist")
def add_to_watchlist(ticker: str, notes: Optional[str] = None, priority: str = "NORMAL", db: Session = Depends(get_db)):
    existing = db.query(Watchlist).filter(Watchlist.ticker == ticker).first()
    if existing:
        existing.notes = notes
        existing.priority = priority
        db.commit()
        return existing
    
    item = Watchlist(ticker=ticker, notes=notes, priority=priority)
    db.add(item)
    db.commit()
    return item


@api.delete("/watchlist/{ticker}")
def remove_from_watchlist(ticker: str, db: Session = Depends(get_db)):
    item = db.query(Watchlist).filter(Watchlist.ticker == ticker).first()
    if not item:
        raise HTTPException(404, "Not in watchlist")
    db.delete(item)
    db.commit()
    return {"ok": True}


# ============================================================
# EVALUATION / TRACK RECORD
# ============================================================

@api.get("/evaluations")
def list_evaluations(
    ticker: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    q = db.query(ProposalEvaluation)
    if ticker:
        q = q.filter(ProposalEvaluation.ticker == ticker)
    return q.order_by(ProposalEvaluation.evaluated_at.desc()).limit(limit).all()


@api.get("/track-record")
def get_track_record(db: Session = Depends(get_db)):
    evals = db.query(ProposalEvaluation).filter(
        ProposalEvaluation.outcome_status.in_(["SUCCESS", "FAILED"])
    ).all()
    
    total = len(evals)
    if total == 0:
        return {"total": 0, "win_rate": 0, "avg_return": 0, "avg_alpha": 0}
    
    wins = sum(1 for e in evals if e.outcome_status == "SUCCESS")
    avg_return = sum(e.realized_return_pct or 0 for e in evals) / total
    avg_alpha = sum(e.alpha_pct or 0 for e in evals) / total
    
    # By confidence band
    high_conf = [e for e in evals if e.realized_return_pct is not None and e.benchmark_return_pct is not None]
    
    return {
        "total_evaluated": total,
        "win_rate": round(wins / total * 100, 1),
        "avg_return_pct": round(avg_return, 2),
        "avg_alpha_pct": round(avg_alpha, 2),
        "by_confidence": {},
        "by_horizon": {},
        "by_signal_type": {},
    }