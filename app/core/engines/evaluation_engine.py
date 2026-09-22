from datetime import datetime, timezone, date, timedelta
from typing import List, Dict, Any, Optional
import json
import logging

from app.config import settings
from app.core.models.schema import get_db, Proposal, ProposalEvaluation, Position, SessionLocal
from app.llm.client import OpenCodeClient

logger = logging.getLogger(__name__)


class EvaluationEngine:
    """Evaluates historical proposals against realized outcomes for calibration"""

    def __init__(self):
        self.db = SessionLocal()

    def get_market_return(self, ticker: str, start_date: date, days: int) -> float:
        """Get realized return for ticker over window from vnstock"""
        from app.core.engines.market_data import get_return_pct
        ret = get_return_pct(ticker, start_date, days)
        return ret if ret is not None else 0.0

    def get_benchmark_return(self, start_date: date, days: int) -> float:
        """Get VN-INDEX return over window from vnstock"""
        from app.core.engines.market_data import get_benchmark_return
        return get_benchmark_return(start_date, days)

    def evaluate_settled_proposals(self) -> Dict[str, Any]:
        """Find proposals whose evaluation window has elapsed and evaluate them"""
        proposals = self.db.query(Proposal).filter(
            Proposal.valid_until <= datetime.now(timezone.utc),
            Proposal.status.in_(["ACTIVE", "REVISED"])
        ).all()

        evaluated = 0
        for p in proposals:
            # Check if evaluation already exists
            existing = self.db.query(ProposalEvaluation).filter(
                ProposalEvaluation.proposal_id == p.id
            ).first()

            if existing:
                continue

            # Calculate realized metrics
            start = p.valid_from.date() if p.valid_from else date.today()
            window_days = p.horizon_days

            # In production, fetch actual price data
            realized_return = self.get_market_return(p.ticker, start, window_days)
            benchmark_return = self.get_benchmark_return(start, window_days)
            alpha = realized_return - benchmark_return

            # Max drawdown
            from app.core.engines.market_data import get_max_drawdown
            max_dd = get_max_drawdown(p.ticker, start, window_days)
            max_drawdown_pct = (max_dd * 100) if max_dd is not None else 0.0

            # Determine outcome
            outcome = "SUCCESS" if realized_return > 0 else "FAILED"

            evaluation = ProposalEvaluation(
                proposal_id=p.id,
                ticker=p.ticker,
                evaluated_at=datetime.now(timezone.utc),
                evaluation_window_days=window_days,
                realized_return_pct=realized_return * 100,
                benchmark_return_pct=benchmark_return * 100,
                alpha_pct=alpha * 100,
                max_drawdown_pct=max_drawdown_pct,
                mfe_pct=0.0,
                mae_pct=0.0,
                outcome_status=outcome,
            )

            self.db.add(evaluation)
            evaluated += 1

        self.db.commit()
        return {"evaluated": evaluated}

    def get_calibration_data(self) -> Dict[str, Any]:
        """Analyze confidence calibration across all evaluated proposals"""
        from sqlalchemy import join
        evals = self.db.query(ProposalEvaluation).filter(
            ProposalEvaluation.outcome_status.in_(["SUCCESS", "FAILED"])
        ).all()

        if not evals:
            return {}

        # Bucket by confidence (join with proposal)
        buckets = {"0-20": [], "20-40": [], "40-60": [], "60-80": [], "80-100": []}

        for e in evals:
            proposal = self.db.query(Proposal).filter(Proposal.id == e.proposal_id).first()
            conf = proposal.confidence if proposal else 50
            if conf < 20:
                buckets["0-20"].append(e)
            elif conf < 40:
                buckets["20-40"].append(e)
            elif conf < 60:
                buckets["40-60"].append(e)
            elif conf < 80:
                buckets["60-80"].append(e)
            else:
                buckets["80-100"].append(e)

        result = {
            "total_evaluated": len(evals),
            "win_rate": sum(1 for e in evals if e.outcome_status == "SUCCESS") / len(evals) * 100,
            "avg_return": sum(e.realized_return_pct or 0 for e in evals) / len(evals),
            "avg_alpha": sum(e.alpha_pct or 0 for e in evals) / len(evals),
            "by_confidence": {},
        }

        for band, band_evals in buckets.items():
            if band_evals:
                wins = sum(1 for e in band_evals if e.outcome_status == "SUCCESS")
                result["by_confidence"][band] = {
                    "count": len(band_evals),
                    "win_rate": round(wins / len(band_evals) * 100, 1),
                    "avg_return": round(sum(e.realized_return_pct or 0 for e in band_evals) / len(band_evals), 2),
                }

        return result

    def close(self):
        self.db.close()


def run_evaluation_job():
    engine = EvaluationEngine()
    try:
        return engine.evaluate_settled_proposals()
    finally:
        engine.close()
