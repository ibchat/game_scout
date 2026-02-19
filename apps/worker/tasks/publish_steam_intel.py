"""
Celery task for publishing Steam Intel to Telegram
Runs periodically via beat schedule (daily at 09:00 or hourly).
"""
import os
import logging
from typing import Optional, Tuple
from datetime import datetime
from zoneinfo import ZoneInfo
from apps.worker.celery_app import celery_app
from apps.db.session import SessionLocal
from apps.intel.services.pipeline.steam_intel_pipeline import run_pipeline
from apps.intel.services.daily_lock import acquire_daily_lock, check_daily_lock

logger = logging.getLogger(__name__)

# Configuration
INTEL_SCHEDULE_MODE = os.getenv("INTEL_SCHEDULE_MODE", "daily")
INTEL_DAILY_RUN_TZ = os.getenv("INTEL_DAILY_RUN_TZ", "Europe/Madrid")
INTEL_RUN_WINDOW_START = os.getenv("INTEL_RUN_WINDOW_START", "09:00")
INTEL_RUN_WINDOW_END = os.getenv("INTEL_RUN_WINDOW_END", "10:00")
INTEL_MAX_POSTS_PER_RUN = int(os.getenv("INTEL_MAX_POSTS_PER_RUN", "20"))


def check_time_window(force: bool = False) -> Tuple[bool, Optional[str]]:
    """
    Check if current time is within allowed window (09:00-10:00 CET).
    
    Args:
        force: If True, skip time window check.
    
    Returns:
        (is_allowed: bool, reason: str or None)
    """
    if force:
        return True, None
    
    if INTEL_SCHEDULE_MODE != "daily":
        return True, None  # Hourly mode doesn't have time window
    
    try:
        tz = ZoneInfo(INTEL_DAILY_RUN_TZ)
        now = datetime.now(tz)
        current_time = now.time()
        
        # Parse window start/end
        start_hour, start_min = map(int, INTEL_RUN_WINDOW_START.split(":"))
        end_hour, end_min = map(int, INTEL_RUN_WINDOW_END.split(":"))
        
        window_start = datetime.strptime(INTEL_RUN_WINDOW_START, "%H:%M").time()
        window_end = datetime.strptime(INTEL_RUN_WINDOW_END, "%H:%M").time()
        
        if window_start <= current_time <= window_end:
            return True, None
        else:
            reason = f"Outside time window ({INTEL_RUN_WINDOW_START}-{INTEL_RUN_WINDOW_END} {INTEL_DAILY_RUN_TZ}), current time: {current_time.strftime('%H:%M')}"
            return False, reason
    except Exception as e:
        logger.warning(f"Failed to check time window: {e}, allowing run")
        return True, None  # Allow if check fails


@celery_app.task(name="publish_steam_intel")
def publish_steam_intel_task(sources: list[str] = None, dry_run: bool = False, force: bool = False):
    """
    Celery task to run Steam Intel pipeline.
    
    Args:
        sources: List of source names to collect from. If None, uses all enabled sources.
        dry_run: If True, don't actually publish.
        force: If True, skip time window check (but still respects daily lock).
    
    Returns:
        Dict with pipeline results
    """
    from apps.intel.db.models import IntelSource
    
    # Check time window (unless forced)
    time_ok, time_reason = check_time_window(force=force)
    if not time_ok:
        logger.info(f"Skipping pipeline run: {time_reason}")
        return {
            "collected": 0,
            "extracted": 0,
            "events_created": 0,
            "eligible_count": 0,
            "briefs_generated": 0,
            "published": 0,
            "skipped": 0,
            "dry_run": dry_run,
            "skipped_reason": "outside_time_window",
            "skipped_message": time_reason
        }
    
    # Check daily lock (for daily mode)
    if INTEL_SCHEDULE_MODE == "daily" and not force:
        lock_acquired, lock_key = acquire_daily_lock()
        if not lock_acquired:
            logger.info(f"Skipping pipeline run: daily lock already exists ({lock_key})")
            return {
                "collected": 0,
                "extracted": 0,
                "events_created": 0,
                "eligible_count": 0,
                "briefs_generated": 0,
                "published": 0,
                "skipped": 0,
                "dry_run": dry_run,
                "skipped_reason": "daily_lock_exists",
                "skipped_message": f"Daily run already executed today ({lock_key})"
            }
    
    db = SessionLocal()
    try:
        # If sources not specified, get all enabled RSS sources
        if sources is None:
            enabled_sources = db.query(IntelSource).filter(
                IntelSource.is_enabled == True,
                IntelSource.type.in_(["rss", "reddit_rss", "steam"])  # Include all types
            ).all()
            sources = [s.name for s in enabled_sources]
            logger.info(f"Using all enabled sources: {len(sources)} sources")
        
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
        
        logger.info(f"Starting Steam Intel pipeline task: sources={len(sources)} sources, dry_run={dry_run}, force={force}")
        
        # Run pipeline with max posts per run limit
        result = run_pipeline(
            sources=sources,
            db=db,
            dry_run=dry_run,
            max_posts_per_run=INTEL_MAX_POSTS_PER_RUN if INTEL_SCHEDULE_MODE == "daily" else None
        )
        
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
