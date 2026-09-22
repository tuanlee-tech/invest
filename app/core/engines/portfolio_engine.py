from datetime import datetime, timezone, date, timedelta
from typing import List, Dict, Any, Optional
import logging

from app.config import settings
from app.core.models.schema import get_db, Position, Proposal, Event, SessionLocal
from app.llm.client import OpenCodeClient

logger = logging.getLogger(__name__)


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
        from app.core.engines.market_data import get_latest_price
        price = get_latest_price(ticker)
        return price if price else 0.0

    def reevaluate_all_positions(self) -> Dict[str, Any]:
        """Re-evaluate all active positions against new events and price action"""
        positions = self.get_active_positions()
        logger.info(f"Re-evaluating {len(positions)} active positions...")

        results = {
            "positions_checked": len(positions),
            "revisions_created": 0,
            "actions": {},
            "invalidation_alerts": []
        }

        for pos in positions:
            ticker = pos.ticker
            proposal = self.get_latest_proposal(ticker)
            events = self.get_recent_events_for_ticker(ticker)
            current_price = self.get_current_price(ticker)

            # Re-evaluate position using LLM
            evaluation = self.llm.reevaluate_position(
                ticker=ticker,
                avg_buy_price=pos.avg_buy_price,
                current_price=current_price,
                current_thesis=proposal.thesis if proposal else "No active proposal",
                invalidation_conditions=proposal.invalidation_conditions if proposal else [],
                new_events=events,
            )

            new_action = evaluation.get("action", "HOLD")
            thesis_health = evaluation.get("thesis_health", "HEALTHY")
            invalidation_triggered = evaluation.get("invalidation_triggered", False)

            # Update position state
            pos.current_action = new_action
            pos.thesis_health = thesis_health

            if invalidation_triggered:
                results["invalidation_alerts"].append({
                    "ticker": ticker,
                    "reason": evaluation.get("explanation")
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