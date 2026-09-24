from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone, date, timedelta
from pathlib import Path

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
        valid_from=datetime.now(timezone.utc),
        valid_until=datetime.now(timezone.utc) + timedelta(days=data.horizon_days),
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
        valid_from=datetime.now(timezone.utc),
        valid_until=datetime.now(timezone.utc) + timedelta(days=data.horizon_days or original.horizon_days),
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
            pos.closed_at = datetime.now(timezone.utc)
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
# PRICES (Real-time from vnstock)
# ============================================================

@api.get("/prices/{ticker}")
def get_price(ticker: str):
    """Get latest price for a ticker from vnstock"""
    from app.core.engines.market_data import get_latest_price, MarketDataError
    try:
        price = get_latest_price(ticker)
    except MarketDataError as e:
        raise HTTPException(502, str(e))
    if price is None:
        raise HTTPException(404, f"Price not found for {ticker}")
    return {"ticker": ticker, "price": price, "source": "vnstock"}


@api.get("/prices")
def get_prices(tickers: str = ""):
    """Get latest prices for multiple tickers (comma-separated)"""
    from app.core.engines.market_data import get_latest_price, MarketDataError
    ticker_list = [t.strip() for t in tickers.split(",") if t.strip()]
    result = {}
    for t in ticker_list:
        try:
            price = get_latest_price(t)
        except MarketDataError as e:
            result[t] = {"price": None, "error": str(e)}
            continue
        result[t] = {"price": price, "source": "vnstock"} if price else {"price": None, "error": "not found"}
    return result


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
def get_track_record(
    ticker: Optional[str] = None,
    action: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Track record with optional ticker/action filter plus full slices.

    Slices cover ticker + action (model/prompt slices need `model_run_id`,
    which is not populated yet).
    """
    evals = db.query(ProposalEvaluation).filter(
        ProposalEvaluation.outcome_status.in_(["SUCCESS", "FAILED"])
    ).all()

    proposals = {
        p.id: p for p in db.query(Proposal).filter(
            Proposal.id.in_([e.proposal_id for e in evals])
        )
    } if evals else {}

    def _row(e: ProposalEvaluation):
        p = proposals.get(e.proposal_id)
        return {
            "proposal_id": e.proposal_id,
            "ticker": e.ticker,
            "confidence": p.confidence if p else None,
            "action": p.action if p else None,
            "realized_return_pct": round(e.realized_return_pct or 0, 2),
            "benchmark_return_pct": round(e.benchmark_return_pct or 0, 2),
            "alpha_pct": round(e.alpha_pct or 0, 2),
            "max_drawdown_pct": round(e.max_drawdown_pct or 0, 2),
            "entry_hit": e.entry_hit,
            "target_hit": e.target_hit,
            "stop_hit": e.stop_hit,
            "outcome_status": e.outcome_status,
            "evaluated_at": e.evaluated_at.isoformat() if e.evaluated_at else None,
        }

    def _agg(rows):
        n = len(rows)
        if not n:
            return {"total": 0, "win_rate": 0, "avg_return_pct": 0, "avg_alpha_pct": 0}
        wins = sum(1 for r in rows if r["outcome_status"] == "SUCCESS")
        return {
            "total": n,
            "win_rate": round(wins / n * 100, 1),
            "avg_return_pct": round(sum(r["realized_return_pct"] for r in rows) / n, 2),
            "avg_alpha_pct": round(sum(r["alpha_pct"] for r in rows) / n, 2),
            "target_hit_rate": round(sum(1 for r in rows if r["target_hit"]) / n * 100, 1),
            "stop_hit_rate": round(sum(1 for r in rows if r["stop_hit"]) / n * 100, 1),
        }

    all_rows = [_row(e) for e in evals]

    # Slices computed over the full set, independent of the filter
    by_ticker, by_action = {}, {}
    for r in all_rows:
        by_ticker.setdefault(r["ticker"], []).append(r)
        key = r["action"] or "UNKNOWN"
        by_action.setdefault(key, []).append(r)

    filtered = all_rows
    if ticker:
        filtered = [r for r in filtered if r["ticker"] == ticker.upper()]
    if action:
        filtered = [r for r in filtered if (r["action"] or "").upper() == action.upper()]

    summary = _agg(filtered)
    if summary["total"] == 0 and not all_rows:
        return {"total": 0, "win_rate": 0, "avg_return_pct": 0, "avg_alpha_pct": 0}

    return {
        **summary,
        "filters": {"ticker": ticker, "action": action},
        "slices": {
            "by_ticker": {k: _agg(v) for k, v in sorted(by_ticker.items())},
            "by_action": {k: _agg(v) for k, v in sorted(by_action.items())},
        },
        "details": filtered,
    }


@api.get("/jobs")
def list_job_runs(
    job_name: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """Job execution history (id, window, status, error, record counts)."""
    from app.core.models.schema import JobRun
    q = db.query(JobRun)
    if job_name:
        q = q.filter(JobRun.job_name == job_name)
    if status:
        q = q.filter(JobRun.status == status)
    return q.order_by(JobRun.started_at.desc()).limit(min(limit, 200)).all()


@api.get("/disclaimer")
def get_disclaimer():
    """Return full disclaimer text"""
    disclaimer_path = Path(__file__).resolve().parent.parent.parent / "DISCLAIMER.md"
    if disclaimer_path.exists():
        return PlainTextResponse(disclaimer_path.read_text(encoding="utf-8"))
    return PlainTextResponse("Disclaimer not found.")