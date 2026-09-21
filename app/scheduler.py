from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
import logging

from app.config import settings
from app.ingestion.pipeline.main import run_ingestion_job
from app.core.engines.opportunity_engine import run_opportunity_scan_job
from app.core.engines.portfolio_engine import run_portfolio_reevaluation_job
from app.core.engines.evaluation_engine import run_evaluation_job

logger = logging.getLogger(__name__)


class EngineScheduler:
    """Manages periodic background tasks for ingestion, opportunity scan, and re-evaluations"""

    def __init__(self):
        self.scheduler = BackgroundScheduler()

    def start(self):
        """Configure and start scheduler jobs"""
        # Ingestion job: runs every N minutes
        self.scheduler.add_job(
            func=self._safe_job(run_ingestion_job, "Ingestion"),
            trigger=IntervalTrigger(minutes=settings.INGESTION_INTERVAL_MINUTES),
            id="job_ingestion",
            name="Run Ingestion Pipeline",
            replace_existing=True,
        )

        # Opportunity Scan job: runs after ingestion or on interval
        self.scheduler.add_job(
            func=self._safe_job(run_opportunity_scan_job, "Opportunity Scan"),
            trigger=IntervalTrigger(minutes=settings.INGESTION_INTERVAL_MINUTES + 15),
            id="job_opportunity_scan",
            name="Run Opportunity Scan",
            replace_existing=True,
        )

        # Portfolio Re-evaluation: runs periodically
        self.scheduler.add_job(
            func=self._safe_job(run_portfolio_reevaluation_job, "Portfolio Re-evaluation"),
            trigger=IntervalTrigger(minutes=settings.REEVALUATION_INTERVAL_MINUTES),
            id="job_portfolio_reeval",
            name="Run Portfolio Re-evaluation",
            replace_existing=True,
        )

        # Evaluation job: runs daily
        self.scheduler.add_job(
            func=self._safe_job(run_evaluation_job, "Evaluation"),
            trigger=IntervalTrigger(hours=24),
            id="job_evaluation",
            name="Run Evaluation Engine",
            replace_existing=True,
        )

        self.scheduler.start()
        print(f"[{datetime.utcnow()}] Background scheduler started with 4 jobs.")

    def shutdown(self):
        """Stop all background jobs"""
        self.scheduler.shutdown()
        print(f"[{datetime.utcnow()}] Background scheduler shut down.")

    def _safe_job(self, func, name: str):
        """Wrapper to prevent unhandled exceptions from stopping scheduler"""
        def wrapper():
            print(f"[{datetime.utcnow()}] Starting scheduled job: {name}")
            try:
                result = func()
                print(f"[{datetime.utcnow()}] Completed scheduled job: {name}, Result: {result}")
            except Exception as e:
                logger.error(f"Error in job {name}: {e}", exc_info=True)
                print(f"[{datetime.utcnow()}] ERROR in job {name}: {e}")
        return wrapper


# Global instance
scheduler = EngineScheduler()
