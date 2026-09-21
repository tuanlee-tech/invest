from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
import json

from app.config import settings
from app.core.models.schema import get_db, Proposal, ProposalEvaluation, Position, SessionLocal
from app.llm.client import OpenCodeClient


class EvaluationEngine:
    """Evaluates historical proposals against realized outcomes for calibration"""

    def __init__(self):
        self.db = SessionLocal()

    def get_market_return(self, ticker: str, start_date: date, days: int) -> float:
        """Get realized return for ticker over window (placeholder - would use vnstock)"""
        # Mock: In production, fetch OHLCV from vnstock
        # For now return a placeholder
        return 0.05  # 5% mock return

    def get_benchmark_return(self, start_date: date, days: int) -> float:
        """Get VN-INDEX return over window (placeholder)"""
        return 0.03  # 3% mock

    def evaluate_settled_proposals(self) -> Dict[str, Any]:
        """Find proposals whose evaluation window has elapsed and evaluate them"""
        proposals = self.db.query(Proposal).filter(
            Proposal.valid_until <= datetime.utcnow(),
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
            
            # Determine outcome
            outcome = "SUCCESS" if realized_return > 0 else "FAILED"
            
            evaluation = ProposalEvaluation(
                proposal_id=p.id,
                ticker=p.ticker,
                evaluated_at=datetime.utcnow(),
                evaluation_window_days=window_days,
                realized_return_pct=realized_return * 100,
                benchmark_return_pct=benchmark_return * 100,
                alpha_pct=alpha * 100,
                max_drawdown_pct=0.0,  # Would calculate from price path
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
        evals = self.db.query(ProposalEvaluation).filter(
            ProposalEvaluation.outcome_status.in_(["SUCCESS", "FAILED"])
        ).all()
        
        if not evals:
            return {}
        
        # Bucket by confidence
        buckets = {"0-20": [], "20-40": [], "40-60": [], "60-80": [], "80-100": []}
        
        for e in evals:
            # We'd need to join with proposal to get confidence
            pass
        
        # This would be expanded in production
        return {
            "total_evaluated": len(evals),
            "win_rate": sum(1 for e in evals if e.outcome_status == "SUCCESS") / len(evals) * 100,
            "avg_return": sum(e.realized_return_pct or 0 for e in evals) / len(evals),
            "avg_alpha": sum(e.alpha_pct or 0 for e in evals) / len(evals),
        }

    def close(self):
        self.db.close()


def run_evaluation_job():
    engine = EvaluationEngine()
    try:
        return engine.evaluate_settled_proposals()
    finally:
        engine.close()