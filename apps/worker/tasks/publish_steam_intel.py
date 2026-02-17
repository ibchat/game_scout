"""
Celery task for publishing Steam Intel to Telegram
Runs periodically via beat schedule.
"""
import logging
from apps.worker.celery_app import celery_app
from apps.db.session import SessionLocal
from apps.intel.services.pipeline.steam_intel_pipeline import run_pipeline

logger = logging.getLogger(__name__)


@celery_app.task(name="publish_steam_intel")
def publish_steam_intel_task(sources: list[str] = None, dry_run: bool = False):
    """
    Celery task to run Steam Intel pipeline.
    
    Args:
        sources: List of source names to collect from. Defaults to ["steam_rss"].
        dry_run: If True, don't actually publish.
    
    Returns:
        Dict with pipeline results
    """
    if sources is None:
        sources = ["steam_rss"]
    
    logger.info(f"Starting Steam Intel pipeline task: sources={sources}, dry_run={dry_run}")
    
    db = SessionLocal()
    try:
        result = run_pipeline(sources=sources, db=db, dry_run=dry_run)
        logger.info(f"Pipeline completed: {result}")
        return result
    except Exception as e:
        logger.error(f"Pipeline task failed: {e}", exc_info=True)
        raise
    finally:
        db.close()
