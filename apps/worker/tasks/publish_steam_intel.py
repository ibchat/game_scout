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
        sources: List of source names to collect from. If None, uses all enabled sources.
        dry_run: If True, don't actually publish.
    
    Returns:
        Dict with pipeline results
    """
    from apps.intel.db.models import IntelSource
    
    db = SessionLocal()
    try:
        # If sources not specified, get all enabled RSS sources
        if sources is None:
            enabled_sources = db.query(IntelSource).filter(
                IntelSource.is_enabled == True,
                IntelSource.type == "rss"
            ).all()
            sources = [s.name for s in enabled_sources]
            logger.info(f"Using all enabled RSS sources: {sources}")
        
        if not sources:
            logger.warning("No sources specified and no enabled sources found")
            return {
                "collected": 0,
                "extracted": 0,
                "events_created": 0,
                "eligible_count": 0,
                "briefs_generated": 0,
                "published": 0,
                "skipped": 0,
                "dry_run": dry_run
            }
        
        logger.info(f"Starting Steam Intel pipeline task: sources={sources}, dry_run={dry_run}")
        
        result = run_pipeline(sources=sources, db=db, dry_run=dry_run)
        logger.info(f"Pipeline completed: collected={result.get('collected', 0)}, "
                   f"eligible={result.get('eligible_count', 0)}, "
                   f"published={result.get('published', 0)}, "
                   f"skipped={result.get('skipped', 0)}")
        return result
    except Exception as e:
        logger.error(f"Pipeline task failed: {e}", exc_info=True)
        raise
    finally:
        db.close()
