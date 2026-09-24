from datetime import datetime, timezone, date, timedelta
from typing import List, Dict, Any, Optional
import logging

from app.config import settings
from app.core.models.schema import get_db, Position, Proposal, Event, SessionLocal
from app.llm.client import OpenCodeClient

logger = logging.getLogger(__name__)


def evaluate_invalidation_conditions(conditions: Optional[List[Dict[str, Any]]],
                                     current_price: float) -> List[Dict[str, Any]]:
    """Deterministically check price-based invalidation conditions.

    Only conditions with data_source starting 'price' and a numeric
    threshold_value are machine-checkable (market data is live; financial
    series are not persisted — those stay with the LLM). Returns triggered rows.
    """
    triggered = []
    if not conditions or not current_price:
        return triggered
    ops = {
        "<": lambda v, t: v < t,
        "<=": lambda v, t: v <= t,
        ">": lambda v, t: v > t,
        ">=": lambda v, t: v >= t,
        "==": lambda v, t: v == t,
    }
    for cond in conditions:
        if not isinstance(cond, dict):
            continue
        src = str(cond.get("data_source") or "").lower()
        if not src.startswith("price"):
            continue
        try:
            threshold = float(cond.get("threshold_value"))
        except (TypeError, ValueError):
            continue
        op = ops.get(str(cond.get("comparison") or "<"))
        if op is None:
            continue
        if op(current_price, threshold):
            triggered.append(cond)
    return triggered


class PortfolioEngine:
    """Manages active portfolio positions and event-driven re-evaluations"""

    def __init__(self):
        self.db = SessionLocal()
        self.llm = OpenCodeClient()

    def get_active_positions(self) -> List[Position]:
        """Get all open positions"""
        return self.db.query(Position).filter(Position.status == "ACTIVE").all()

    def get_latest_proposal(self, ticker: str) -> Optional[Proposal]:
        """Get latest active proposal for ticker"""
        return self.db.query(Proposal).filter(
            Proposal.ticker == ticker,
            Proposal.status == "ACTIVE"
        ).order_by(Proposal.version.desc()).first()

    def get_recent_events_for_ticker(self, ticker: str, days: int = 14) -> List[Event]:
        """Get events affecting this ticker"""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        events = self.db.query(Event).filter(
            Event.occurred_at >= cutoff
        ).order_by(Event.occurred_at.desc()).all()

        # Filter for ticker mention
        return [e for e in events if ticker in (e.entities or [])]

    def get_current_price(self, ticker: str) -> float:
        """Get current market price from vnstock"""
        from app.core.engines.market_data import get_latest_price, MarketDataError
        try:
            price = get_latest_price(ticker)
        except MarketDataError as e:
            logger.warning("Market data unavailable for %s: %s", ticker, e)
            return 0.0
        return price if price else 0.0

    def reevaluate_all_positions(self) -> Dict[str, Any]:
        """Re-evaluate all active positions against new events and price action"""
        positions = self.get_active_positions()
        logger.info(f"Re-evaluating {len(positions)} active positions...")

        results = {
            "positions_checked": len(positions),
            "revisions_created": 0,
            "actions": {},
            "invalidation_alerts": [],
            "errors": 0,
        }

        for pos in positions:
            ticker = pos.ticker
            proposal = self.get_latest_proposal(ticker)
            events = self.get_recent_events_for_ticker(ticker)
            current_price = self.get_current_price(ticker)

            conditions = proposal.invalidation_conditions if proposal else []
            triggered = evaluate_invalidation_conditions(conditions, current_price)
            critical_hit = any(
                str(c.get("severity", "CRITICAL")).upper() == "CRITICAL" for c in triggered
            )

            # LLM evaluation is best-effort; deterministic price checks run regardless
            evaluation: Dict[str, Any] = {}
            llm_error = None
            try:
                evaluation = self.llm.reevaluate_position(
                    ticker=ticker,
                    avg_buy_price=pos.avg_buy_price,
                    current_price=current_price,
                    current_thesis=proposal.thesis if proposal else "No active proposal",
                    invalidation_conditions=conditions,
                    new_events=events,
                )
                if not isinstance(evaluation, dict):
                    raise ValueError(f"evaluation is not an object: {type(evaluation).__name__}")
            except Exception as e:
                llm_error = e
                logger.error("LLM re-evaluation failed for %s: %s", ticker, e)

            new_action = str(evaluation.get("action") or "HOLD").upper()
            if new_action not in {"ADD", "HOLD", "REDUCE", "EXIT"}:
                new_action = "HOLD"
            thesis_health = str(evaluation.get("thesis_health") or "HEALTHY").upper()
            if thesis_health not in {"HEALTHY", "AT_RISK", "INVALIDATED"}:
                thesis_health = "HEALTHY"
            invalidation_triggered = bool(evaluation.get("invalidation_triggered"))

            # Deterministic override: a CRITICAL price condition beats the LLM
            if critical_hit:
                thesis_health = "INVALIDATED"
                new_action = "EXIT"
                invalidation_triggered = True
            elif triggered:
                thesis_health = "AT_RISK"
                invalidation_triggered = True

            if llm_error and not triggered:
                # No LLM verdict and no deterministic trigger → leave state untouched
                results["errors"] += 1
                results["actions"][ticker] = pos.current_action
                continue

            for cond in triggered:
                results["invalidation_alerts"].append({
                    "ticker": ticker,
                    "condition_id": cond.get("condition_id"),
                    "reason": cond.get("description"),
                    "current_price": current_price,
                    "threshold_value": cond.get("threshold_value"),
                    "comparison": cond.get("comparison"),
                    "severity": cond.get("severity", "CRITICAL"),
                })

            # Update position state
            pos.current_action = new_action
            pos.thesis_health = thesis_health

            if invalidation_triggered and not any(
                a.get("ticker") == ticker for a in results["invalidation_alerts"]
            ):
                results["invalidation_alerts"].append({
                    "ticker": ticker,
                    "reason": evaluation.get("explanation") or "invalidation triggered",
                })

            # If proposal exists and action changed or targets revised, create revision
            if proposal and (new_action != proposal.action or evaluation.get("revised_target_min")):
                new_version = proposal.version + 1
                new_id = f"{proposal.proposal_group_id}-v{new_version}"

                # Mark old as REVISED
                proposal.status = "REVISED"

                revision = Proposal(
                    id=new_id,
                    proposal_group_id=proposal.proposal_group_id,
                    ticker=ticker,
                    version=new_version,
                    parent_version=proposal.version,
                    status="ACTIVE",
                    action=new_action,
                    entry_min=proposal.entry_min,
                    entry_max=proposal.entry_max,
                    target_min=evaluation.get("revised_target_min", proposal.target_min),
                    target_max=evaluation.get("revised_target_max", proposal.target_max),
                    stop_reference=evaluation.get("revised_stop", proposal.stop_reference),
                    stop_method=proposal.stop_method,
                    horizon_days=proposal.horizon_days,
                    valid_from=datetime.now(timezone.utc),
                    valid_until=datetime.now(timezone.utc) + timedelta(days=proposal.horizon_days),
                    confidence=evaluation.get("confidence", proposal.confidence),
                    position_size_suggestion=proposal.position_size_suggestion,
                    thesis=proposal.thesis,
                    catalysts=proposal.catalysts,
                    risks=proposal.risks,
                    invalidation_conditions=proposal.invalidation_conditions,
                    evidence_refs=[e.id for e in events],
                    reasoning_summary=evaluation.get("explanation"),
                    changed_from_previous=f"Portfolio re-evaluation: {new_action}. {evaluation.get('explanation')}",
                )
                self.db.add(revision)
                results["revisions_created"] += 1

            results["actions"][ticker] = new_action

        self.db.commit()
        return results

    def close(self):
        self.db.close()


def run_portfolio_reevaluation_job():
    engine = PortfolioEngine()
    try:
        return engine.reevaluate_all_positions()
    finally:
        engine.close()