from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timezone
from uuid import uuid4
import logging

from app.config import settings
from app.core.models.schema import JobRun, SessionLocal
from app.ingestion.pipeline.main import run_ingestion_job
from app.core.engines.opportunity_engine import run_opportunity_scan_job
from app.core.engines.portfolio_engine import run_portfolio_reevaluation_job
from app.core.engines.evaluation_engine import run_evaluation_job

logger = logging.getLogger(__name__)


def _summarize_result(result) -> dict:
    """Scalar summary of a job result for JobRun.record_counts (lists become counts)."""
    if not isinstance(result, dict):
        return {"result": str(result)[:200]}
    out = {}
    for key, value in result.items():
        if isinstance(value, (int, float, bool)) or value is None:
            out[key] = value
        elif isinstance(value, list):
            out[f"{key}_count"] = len(value)
        elif isinstance(value, str):
            out[key] = value[:100]
        elif isinstance(value, dict):
            out[f"{key}_keys"] = list(value.keys())[:20]
    return out


class EngineScheduler:
    """Manages periodic background tasks for ingestion, opportunity scan, and re-evaluations"""

    def __init__(self):
        # max_instances=1 (APScheduler default, set explicitly): a job never
        # overlaps itself; a failed run cannot stop the scheduler (_safe_job).
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
            max_instances=1,
        )

        # Opportunity Scan job: runs after ingestion or on interval
        self.scheduler.add_job(
            func=self._safe_job(run_opportunity_scan_job, "Opportunity Scan"),
            trigger=IntervalTrigger(minutes=settings.INGESTION_INTERVAL_MINUTES + 15),
            id="job_opportunity_scan",
            name="Run Opportunity Scan",
            replace_existing=True,
            max_instances=1,
        )

        # Portfolio Re-evaluation: runs periodically
        self.scheduler.add_job(
            func=self._safe_job(run_portfolio_reevaluation_job, "Portfolio Re-evaluation"),
            trigger=IntervalTrigger(minutes=settings.REEVALUATION_INTERVAL_MINUTES),
            id="job_portfolio_reeval",
            name="Run Portfolio Re-evaluation",
            replace_existing=True,
            max_instances=1,
        )

        # Evaluation job: runs daily
        self.scheduler.add_job(
            func=self._safe_job(run_evaluation_job, "Evaluation"),
            trigger=IntervalTrigger(hours=24),
            id="job_evaluation",
            name="Run Evaluation Engine",
            replace_existing=True,
            max_instances=1,
        )

        self.scheduler.start()
        logger.info("Background scheduler started with 4 jobs.")

    def shutdown(self):
        """Stop all background jobs"""
        self.scheduler.shutdown()
        logger.info("Background scheduler shut down.")

    def _safe_job(self, func, name: str):
        """Wrapper: never lets an exception kill the scheduler; records a JobRun row."""
        def wrapper():
            db = SessionLocal()
            run = JobRun(
                job_id=uuid4().hex,
                job_name=name,
                started_at=datetime.now(timezone.utc),
                status="RUNNING",
            )
            db.add(run)
            db.commit()
            logger.info("Starting scheduled job: %s (%s)", name, run.job_id)
            try:
                result = func()
                run.status = "SUCCESS"
                run.record_counts = _summarize_result(result)
                logger.info("Completed scheduled job: %s (%s): %s",
                            name, run.job_id, run.record_counts)
            except Exception as e:
                run.status = "FAILED"
                run.error = f"{type(e).__name__}: {e}"[:2000]
                logger.error("Error in job %s (%s): %s", name, run.job_id, e, exc_info=True)
            finally:
                run.finished_at = datetime.now(timezone.utc)
                db.commit()
                db.close()
        return wrapper


# Global instance
scheduler = EngineScheduler()
