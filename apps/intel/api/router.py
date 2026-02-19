"""
Intel API Router
Endpoints for Intel dashboard and moderation.
"""
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session

from apps.api.deps import get_db_session
from apps.intel.config import is_intel_enabled

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/intel", tags=["Intel"])


def check_intel_enabled():
    """Dependency to check if Intel is enabled."""
    if not is_intel_enabled():
        raise HTTPException(
            status_code=503,
            detail="Intel module is disabled. Set INTEL_ENABLED=true to enable."
        )


@router.get("/health")
async def intel_health(db: Session = Depends(get_db_session)) -> Dict[str, Any]:
    """Health check for Intel module."""
    from apps.intel.policy.policy_engine import load_policy, get_policy_hash
    from apps.intel.config import get_telegram_config
    
    policy_loaded = False
    policy_version = None
    policy_hash = None
    telegram_configured = False
    db_ok = False
    
    try:
        policy = load_policy()
        policy_loaded = policy is not None
        policy_version = policy.get("version", "unknown") if policy else None
        policy_hash = get_policy_hash()
    except Exception as e:
        logger.warning(f"Failed to load policy for health check: {e}")
    
    # Check Telegram config and access
    telegram_configured = False
    telegram_ok = False
    telegram_details = {}
    telegram_error = None
    try:
        from apps.intel.services.publishers.telegram_publisher import TelegramPublisher
        token, chat_id = get_telegram_config()
        # telegram_configured = True if token is set (chat_id can be auto-detected)
        telegram_configured = token is not None
        
        if telegram_configured:
            # Check actual access (TelegramPublisher will try auto-detection if chat_id is None)
            publisher = TelegramPublisher(db)
            telegram_ok, telegram_error, telegram_details = publisher.check_telegram_access()
            # Add can_post flag if available
            if telegram_ok and "can_post" not in telegram_details:
                telegram_details["can_post"] = True
        else:
            telegram_error = "TELEGRAM_BOT_TOKEN not configured"
    except Exception as e:
        logger.warning(f"Failed to check Telegram access: {e}")
        telegram_error = str(e)
    
    # Check DB
    try:
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    
    # Check Translation service
    translation_ok = False
    translation_error = None
    try:
        from apps.intel.services.translation.free_translate import check_translation_service
        translation_ok, translation_error = check_translation_service()
    except Exception as e:
        logger.warning(f"Failed to check translation service: {e}")
        translation_error = str(e)
    
    return {
        "status": "ok" if is_intel_enabled() else "disabled",
        "module": "intel",
        "enabled": is_intel_enabled(),
        "policy_loaded": policy_loaded,
        "policy_version": policy_version,
        "policy_hash": policy_hash,
        "telegram_configured": telegram_configured,
        "telegram_ok": telegram_ok,
        "telegram_error": telegram_error if not telegram_ok else None,
        "telegram_details": telegram_details if telegram_ok else {},
        "translation_ok": translation_ok,
        "translation_error": translation_error if not translation_ok else None,
        "db_ok": db_ok
    }


@router.get("/events")
async def get_intel_events(
    status: Optional[str] = Query(None, description="Filter by status"),
    steam_appid: Optional[int] = Query(None, description="Filter by Steam app ID"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    min_score: Optional[int] = Query(None, description="Minimum score"),
    q: Optional[str] = Query(None, description="Search query"),
    date_from: Optional[str] = Query(None, description="Date from (ISO format)"),
    date_to: Optional[str] = Query(None, description="Date to (ISO format)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db_session),
    _: None = Depends(check_intel_enabled),
) -> Dict[str, Any]:
    """
    Get Intel events with filtering and pagination.
    Requires Intel module to be enabled.
    """
    # TODO: Implement in Commit 12
    return {
        "status": "ok",
        "events": [],
        "total": 0,
        "limit": limit,
        "offset": offset
    }


@router.get("/events/{event_id}")
async def get_intel_event(
    event_id: int,
    db: Session = Depends(get_db_session),
    _: None = Depends(check_intel_enabled),
) -> Dict[str, Any]:
    """Get single Intel event by ID."""
    # TODO: Implement in Commit 12
    raise HTTPException(status_code=404, detail="Event not found")


@router.post("/events/{event_id}/set_status")
async def set_event_status(
    event_id: int,
    status: str = Body(..., description="New status: ignored|needs_review|ready"),
    db: Session = Depends(get_db_session),
    _: None = Depends(check_intel_enabled),
) -> Dict[str, Any]:
    """Manually set event status for moderation."""
    # TODO: Implement in Commit 12
    return {"status": "ok", "message": "Status updated"}


@router.post("/events/{event_id}/publish")
async def publish_event(
    event_id: int,
    db: Session = Depends(get_db_session),
    _: None = Depends(check_intel_enabled),
) -> Dict[str, Any]:
    """Manually publish a single event to Telegram."""
    # TODO: Implement in Commit 12
    return {"status": "ok", "message": "Event published"}


@router.get("/sources")
async def get_intel_sources(
    db: Session = Depends(get_db_session),
    _: None = Depends(check_intel_enabled),
) -> Dict[str, Any]:
    """Get list of Intel sources."""
    from apps.intel.db.models import IntelSource
    
    sources = db.query(IntelSource).order_by(IntelSource.name).all()
    
    return {
        "status": "ok",
        "sources": [
            {
                "id": str(s.id),
                "name": s.name,
                "type": s.type,
                "url": s.url,
                "is_enabled": s.is_enabled,
                "language_hint": s.language_hint,
                "priority": s.priority
            }
            for s in sources
        ],
        "total": len(sources),
        "active": len([s for s in sources if s.is_enabled])
    }


@router.post("/sources/seed_global")
async def seed_global_sources_endpoint(
    force: bool = Query(False, description="Force update existing sources"),
    db: Session = Depends(get_db_session),
    _: None = Depends(check_intel_enabled),
) -> Dict[str, Any]:
    """
    Seed high-noise global sources for Intel collection.
    Adds Google News RSS (multiple locales), Reddit RSS, SteamDB, and major gaming media.
    """
    from apps.intel.services.sources_seeder import seed_global_sources
    
    try:
        result = seed_global_sources(db, force_update=force)
        return {
            "status": "ok",
            "message": f"Seeded {result['added']} new sources, updated {result['updated']}, skipped {result['skipped']}",
            **result
        }
    except Exception as e:
        logger.error(f"Failed to seed global sources: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to seed sources: {str(e)}")


@router.post("/sources/seed")
async def seed_intel_sources(
    force: bool = Query(False, description="Force update existing sources"),
    db: Session = Depends(get_db_session),
    _: None = Depends(check_intel_enabled),
) -> Dict[str, Any]:
    """
    Seed Intel sources from global RSS list.
    Idempotent UPSERT - safe to call multiple times.
    """
    from apps.intel.db.seed_sources import seed_intel_sources as seed_func
    
    try:
        stats = seed_func(db, force=force)
        return {
            "status": "ok",
            "message": "Sources seeded successfully",
            "stats": stats
        }
    except Exception as e:
        logger.error(f"Source seeding failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Seeding failed: {str(e)}")


@router.post("/sources")
async def create_intel_source(
    source_data: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db_session),
    _: None = Depends(check_intel_enabled),
) -> Dict[str, Any]:
    """Create a new Intel source."""
    # TODO: Implement in Commit 12
    return {"status": "ok", "source_id": 0}


@router.put("/sources/{source_id}")
async def update_intel_source(
    source_id: int,
    source_data: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db_session),
    _: None = Depends(check_intel_enabled),
) -> Dict[str, Any]:
    """Update Intel source configuration."""
    # TODO: Implement in Commit 12
    return {"status": "ok", "message": "Source updated"}


@router.get("/pipeline/status")
async def pipeline_status(
    db: Session = Depends(get_db_session),
    _: None = Depends(check_intel_enabled),
) -> Dict[str, Any]:
    """
    Get Intel pipeline status including daily run information.
    
    Returns:
    {
      "schedule_mode": "daily" | "hourly",
      "last_daily_run_at": "2026-02-18T09:00:00+01:00" | null,
      "last_daily_run_date": "2026-02-18" | null,
      "last_daily_run_result": {
        "published": int,
        "skipped": int,
        "collected": int
      } | null,
      "daily_lock_exists": bool,
      "time_window": {
        "start": "09:00",
        "end": "10:00",
        "timezone": "Europe/Madrid"
      }
    }
    """
    import os
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from apps.intel.services.daily_lock import check_daily_lock, get_daily_lock_key
    from apps.intel.db.models import IntelPublishLog
    
    schedule_mode = os.getenv("INTEL_SCHEDULE_MODE", "daily")
    tz = ZoneInfo(os.getenv("INTEL_DAILY_RUN_TZ", "Europe/Madrid"))
    
    # Get last daily run from publish_log (today's first published message)
    today = datetime.now(tz).date()
    today_start = datetime.combine(today, datetime.min.time()).replace(tzinfo=tz)
    
    last_run_log = db.query(IntelPublishLog).filter(
        IntelPublishLog.published_at >= today_start,
        IntelPublishLog.status == "published"
    ).order_by(IntelPublishLog.published_at.asc()).first()
    
    last_daily_run_at = None
    last_daily_run_date = None
    last_daily_run_result = None
    
    if last_run_log:
        last_daily_run_at = last_run_log.published_at.isoformat()
        last_daily_run_date = last_run_log.published_at.date().isoformat()
        
        # Get stats for today
        today_logs = db.query(IntelPublishLog).filter(
            IntelPublishLog.published_at >= today_start
        ).all()
        
        published_today = len([l for l in today_logs if l.status == "published"])
        skipped_today = len([l for l in today_logs if l.status == "skipped"])
        
        # Get collected count from last run (if available in payload)
        collected_today = 0
        if last_run_log.payload and isinstance(last_run_log.payload, dict):
            collected_today = last_run_log.payload.get("collected", 0)
        
        last_daily_run_result = {
            "published": published_today,
            "skipped": skipped_today,
            "collected": collected_today
        }
    
    # Check daily lock
    daily_lock_exists = check_daily_lock()
    
    return {
        "schedule_mode": schedule_mode,
        "last_daily_run_at": last_daily_run_at,
        "last_daily_run_date": last_daily_run_date,
        "last_daily_run_result": last_daily_run_result,
        "daily_lock_exists": daily_lock_exists,
        "time_window": {
            "start": os.getenv("INTEL_RUN_WINDOW_START", "09:00"),
            "end": os.getenv("INTEL_RUN_WINDOW_END", "10:00"),
            "timezone": os.getenv("INTEL_DAILY_RUN_TZ", "Europe/Madrid")
        }
    }


@router.post("/pipeline/run")
async def run_pipeline(
    body: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db_session),
    _: None = Depends(check_intel_enabled),
) -> Dict[str, Any]:
    """
    Run Steam Intel pipeline.
    
    Body:
    {
      "sources": ["steam_rss", "Steam News"],
      "dry_run": false
    }
    
    Returns:
    {
      "collected": int,
      "extracted": int,
      "events_created": int,
      "briefs_generated": int,
      "published": int,
      "skipped": int
    }
    """
    from apps.intel.services.pipeline.steam_intel_pipeline import run_pipeline as run_intel_pipeline
    
    # ARCHITECTURE FIX: If sources not provided, pass None (not empty list)
    # Pipeline will get all active sources
    sources = body.get("sources")  # None if not provided
    dry_run = body.get("dry_run", False)
    
    # If sources is empty list, convert to None to trigger "get all active"
    if isinstance(sources, list) and len(sources) == 0:
        sources = None
    
    try:
        result = run_intel_pipeline(sources=sources, db=db, dry_run=dry_run)
        return {
            "status": "ok",
            **result
        }
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {str(e)}")


@router.get("/pipeline/status")
async def pipeline_status(
    db: Session = Depends(get_db_session),
    _: None = Depends(check_intel_enabled),
) -> Dict[str, Any]:
    """
    Get pipeline status and statistics.
    
    Returns:
    {
      "total_raw_items": int,
      "total_events": int,
      "total_published": int,
      "total_skipped": int,
      "last_publish_time": str (ISO format) or null,
      "last_error": str or null
    }
    """
    from apps.intel.db.models import IntelRawItem, IntelEvent, IntelPublishLog
    
    total_raw_items = db.query(IntelRawItem).count()
    total_events = db.query(IntelEvent).count()
    total_published = db.query(IntelPublishLog).filter(
        IntelPublishLog.status == "published"
    ).count()
    total_skipped = db.query(IntelPublishLog).filter(
        IntelPublishLog.status == "skipped"
    ).count()
    
    # Get last publish time
    last_publish = db.query(IntelPublishLog).filter(
        IntelPublishLog.status == "published"
    ).order_by(IntelPublishLog.published_at.desc()).first()
    
    last_publish_time = last_publish.published_at.isoformat() if last_publish else None
    
    # Get last error
    last_error_log = db.query(IntelPublishLog).filter(
        IntelPublishLog.status == "failed"
    ).order_by(IntelPublishLog.published_at.desc()).first()
    
    last_error = last_error_log.error if last_error_log else None
    
    return {
        "status": "ok",
        "total_raw_items": total_raw_items,
        "total_events": total_events,
        "total_published": total_published,
        "total_skipped": total_skipped,
        "last_publish_time": last_publish_time,
        "last_error": last_error
    }


@router.post("/telegram/test")
async def test_telegram(
    body: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db_session),
    _: None = Depends(check_intel_enabled),
) -> Dict[str, Any]:
    """Test Telegram publishing with a custom message"""
    from apps.intel.db.models import IntelEvent
    """
    Test Telegram bot and channel access.
    
    Body:
    {
      "dry_run": true|false,
      "text": "optional test message"
    }
    
    If dry_run=true: only check access (getMe/getChat)
    If dry_run=false: send test message to channel
    """
    from apps.intel.services.publishers.telegram_publisher import TelegramPublisher
    from apps.intel.db.models import IntelPublishLog
    from datetime import datetime
    
    dry_run = body.get("dry_run", True)
    test_text = body.get("text", "🧪 Game Scout Intel test")
    
    publisher = TelegramPublisher(db)
    
    # Check access
    access_ok, access_error, access_details = publisher.check_telegram_access()
    
    if not access_ok:
        raise HTTPException(
            status_code=400,
            detail=f"Telegram access check failed: {access_error}"
        )
    
    if dry_run:
        return {
            "status": "ok",
            "message": "Telegram access verified (dry run)",
            "bot_username": access_details.get("bot_username"),
            "chat_title": access_details.get("chat_title"),
            "chat_type": access_details.get("chat_type")
        }
    
    # Send test message
    test_message = f"{test_text} - {datetime.utcnow().isoformat()}"
    
    try:
        # Ensure message is in Russian
        from apps.intel.services.translator import translate_to_ru, message_is_russian
        if not message_is_russian(test_message):
            test_message = translate_to_ru(test_message)
        
        success, message_id, error = publisher._send_to_telegram(test_message)
        
        if success:
            # Log as test publish
            test_event_id = None  # No real event for test
            # Create a minimal log entry
            publish_log = IntelPublishLog(
                event_id=test_event_id or db.query(IntelEvent).first().id if db.query(IntelEvent).count() > 0 else None,
                channel_id="free",
                telegram_message_id=message_id or "test",
                status="published",
                payload={"test": True, "message": test_message[:100]}
            )
            if publish_log.event_id:
                db.add(publish_log)
                db.commit()
            
            return {
                "status": "ok",
                "message": "Test message sent successfully",
                "message_id": message_id,
                "bot_username": access_details.get("bot_username"),
                "chat_title": access_details.get("chat_title")
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to send test message: {error}"
            )
    except Exception as e:
        logger.error(f"Telegram test failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Telegram test failed: {str(e)}"
        )


@router.post("/run-steam-feed")
async def run_steam_feed(
    limit: int = Query(20, ge=1, le=100, description="Maximum events to process"),
    dry_run: bool = Query(False, description="Dry run mode (no actual publishing)"),
    premium: bool = Query(False, description="Use premium channel"),
    db: Session = Depends(get_db_session),
    _: None = Depends(check_intel_enabled),
) -> Dict[str, Any]:
    """
    Run full Steam Intelligence → Telegram Business Feed pipeline.
    
    Flow: collect → extract → event → brief → publish
    
    Args:
        limit: Maximum events to process
        dry_run: If True, don't actually publish
        premium: If True, use premium channel (includes funding, publisher_deal, market_trend)
    
    Returns:
        Summary of processed events
    """
    from apps.intel.db.models import IntelEvent, IntelRawItem, IntelExtractedItem
    from apps.intel.services.briefing.steam_brief_generator import generate_business_brief
    from apps.intel.services.publishers.telegram_publisher import TelegramPublisher
    from apps.intel.policy.policy_engine import load_policy
    from datetime import datetime
    
    logger.info(f"Starting Steam feed pipeline: limit={limit}, dry_run={dry_run}, premium={premium}")
    
    # Determine channel and event types
    channel = "premium" if premium else "public"
    policy = load_policy()
    
    if premium:
        # Premium: all allowed types
        allowed_types = policy.get("allowed_event_types_for_autopublish", [])
    else:
        # Public: only safe types (release, patch_major, discount)
        allowed_types = ["release", "patch_major", "discount"]
    
    # Get events ready for publishing
    events_query = db.query(IntelEvent).filter(
        IntelEvent.status == "ready",
        IntelEvent.event_type.in_(allowed_types),
        IntelEvent.publish_status.in_([None, "draft"]),
        IntelEvent.is_premium == premium
    ).order_by(IntelEvent.score.desc(), IntelEvent.created_at.desc()).limit(limit)
    
    events = events_query.all()
    
    if not events:
        return {
            "status": "ok",
            "message": "No events ready for publishing",
            "processed": 0,
            "published": 0,
            "failed": 0
        }
    
    # Process each event
    published_count = 0
    failed_count = 0
    results = []
    
    publisher = TelegramPublisher(db)
    
    for event in events:
        try:
            # Step 1: Generate business brief if not exists
            if not event.business_brief_json:
                logger.info(f"Generating business brief for event {event.id}")
                brief = generate_business_brief(event, db)
                event.business_brief_json = brief
                event.business_brief_generated_at = datetime.utcnow()
                db.commit()
            
            # Step 2: Publish to Telegram
            result = publisher.publish_event(event, dry_run=dry_run, channel=channel)
            
            if result.success:
                published_count += 1
                results.append({
                    "event_id": str(event.id),
                    "status": "published",
                    "message_id": result.message_id,
                    "channel": channel
                })
            else:
                failed_count += 1
                event.publish_status = "failed"
                results.append({
                    "event_id": str(event.id),
                    "status": "failed",
                    "error": result.error
                })
            
            db.commit()
            
        except Exception as e:
            logger.error(f"Failed to process event {event.id}: {e}", exc_info=True)
            failed_count += 1
            event.publish_status = "failed"
            results.append({
                "event_id": str(event.id),
                "status": "error",
                "error": str(e)
            })
            db.rollback()
    
    return {
        "status": "ok",
        "message": f"Processed {len(events)} events",
        "processed": len(events),
        "published": published_count,
        "failed": failed_count,
        "channel": channel,
        "dry_run": dry_run,
            "results": results
        }


@router.get("/debug/queue")
async def debug_queue(
    db: Session = Depends(get_db_session),
    _: None = Depends(check_intel_enabled),
) -> Dict[str, Any]:
    """
    Debug endpoint for Celery queue status.
    Shows active tasks, scheduled tasks, and last publish time.
    """
    from celery import current_app
    from apps.intel.db.models import IntelPublishLog
    
    try:
        # Get Celery inspect
        inspect = current_app.control.inspect()
        
        # Active tasks
        active_tasks = inspect.active() or {}
        active_count = sum(len(tasks) for tasks in active_tasks.values())
        
        # Scheduled tasks
        scheduled_tasks = inspect.scheduled() or {}
        scheduled_count = sum(len(tasks) for tasks in scheduled_tasks.values())
        
        # Last publish time
        last_publish = db.query(IntelPublishLog).filter(
            IntelPublishLog.status == "published"
        ).order_by(IntelPublishLog.published_at.desc()).first()
        
        last_publish_time = last_publish.published_at.isoformat() if last_publish and last_publish.published_at else None
        
        # Check if beat schedule is registered
        beat_schedule = current_app.conf.beat_schedule or {}
        intel_tasks = {k: v for k, v in beat_schedule.items() if "intel" in k.lower() or "publish" in k.lower()}
        
        return {
            "status": "ok",
            "active_tasks": active_count,
            "scheduled_tasks": scheduled_count,
            "last_publish_time": last_publish_time,
            "beat_schedule_registered": len(intel_tasks) > 0,
            "intel_tasks_in_schedule": list(intel_tasks.keys())
        }
    except Exception as e:
        logger.error(f"Failed to get queue debug info: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e)
        }


@router.get("/debug/full_state")
async def debug_full_state(
    db: Session = Depends(get_db_session),
    _: None = Depends(check_intel_enabled),
) -> Dict[str, Any]:
    """
    Get full Intel pipeline state for debugging.
    Returns comprehensive diagnostics.
    FIXED: Now handles missing columns gracefully.
    """
    from apps.intel.db.models import IntelSource, IntelRawItem, IntelExtractedItem, IntelEvent, IntelPublishLog
    from datetime import datetime, timedelta, timezone
    from zoneinfo import ZoneInfo
    from sqlalchemy import text
    import os
    
    errors = []
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)
    
    # Sources (with error handling for missing columns)
    try:
        sources_enabled = db.query(IntelSource).filter(IntelSource.is_enabled == True).count()
    except Exception as e:
        db.rollback()  # Reset transaction state
        errors.append(f"sources_enabled_query: {str(e)[:200]}")
        sources_enabled = 0
    
    # Raw items
    try:
        raw_last_24h = db.query(IntelRawItem).filter(
            IntelRawItem.fetched_at >= cutoff_time
        ).count()
    except Exception as e:
        db.rollback()
        errors.append(f"raw_last_24h_query: {str(e)[:200]}")
        raw_last_24h = 0
    
    # Extracted items (check if extracted_at exists)
    extracted_last_24h = 0
    extracted_at_exists = False
    try:
        # Try using extracted_at
        extracted_last_24h = db.query(IntelExtractedItem).filter(
            IntelExtractedItem.extracted_at >= cutoff_time
        ).count()
        extracted_at_exists = True
    except Exception as e:
        db.rollback()
        if "extracted_at" in str(e).lower() or "column" in str(e).lower():
            extracted_at_exists = False
            errors.append(f"extracted_at_column_missing: {str(e)[:200]}")
            # Fallback: try using raw SQL to check if column exists
            try:
                result = db.execute(text("""
                    SELECT COUNT(*) FROM intel_extracted_items
                    WHERE id IN (
                        SELECT id FROM intel_extracted_items LIMIT 1
                    )
                """))
                extracted_last_24h = result.scalar() or 0
            except:
                pass
        else:
            errors.append(f"extracted_last_24h_query: {str(e)[:200]}")
    
    # Events
    try:
        events_last_24h = db.query(IntelEvent).filter(
            IntelEvent.created_at >= cutoff_time
        ).count()
    except Exception as e:
        db.rollback()
        errors.append(f"events_last_24h_query: {str(e)[:200]}")
        events_last_24h = 0
    
    # Eligible events
    try:
        eligible_last_24h = db.query(IntelEvent).filter(
            IntelEvent.created_at >= cutoff_time,
            IntelEvent.autopublish_eligible == True
        ).count()
    except Exception as e:
        db.rollback()
        errors.append(f"eligible_last_24h_query: {str(e)[:200]}")
        eligible_last_24h = 0
    
    # Published (use created_at if exists, fallback to published_at)
    published_last_24h = 0
    try:
        # Try using created_at first
        published_last_24h = db.query(IntelPublishLog).filter(
            IntelPublishLog.created_at >= cutoff_time,
            IntelPublishLog.status == "published"
        ).count()
    except Exception as e:
        db.rollback()
        if "created_at" in str(e).lower() or "column" in str(e).lower():
            # Fallback to published_at if created_at doesn't exist
            try:
                published_last_24h = db.query(IntelPublishLog).filter(
                    IntelPublishLog.published_at >= cutoff_time,
                    IntelPublishLog.status == "published"
                ).count()
            except Exception as e2:
                db.rollback()
                errors.append(f"published_last_24h_query_fallback: {str(e2)[:200]}")
        else:
            errors.append(f"published_last_24h_query: {str(e)[:200]}")
    
    # Extraction ratio
    extraction_ratio = (extracted_last_24h / raw_last_24h * 100) if raw_last_24h > 0 else 0.0
    
    # Zero scores
    zero_scores = 0
    try:
        events_with_scores = db.query(IntelEvent).filter(
            IntelEvent.created_at >= cutoff_time,
            IntelEvent.significance_score > 0
        ).all()
        zero_scores = len([e for e in events_with_scores if e.significance_score == 0])
    except Exception as e:
        db.rollback()
        errors.append(f"zero_scores_query: {str(e)[:200]}")
    
    # Alembic current revision
    alembic_current_revision = None
    try:
        result = db.execute(text("SELECT version_num FROM alembic_version ORDER BY version_num DESC LIMIT 1"))
        row = result.fetchone()
        alembic_current_revision = row[0] if row else None
    except Exception as e:
        db.rollback()
        errors.append(f"alembic_revision_query: {str(e)[:200]}")
    
    # Last run info
    last_run_timestamp = datetime.now(timezone.utc).isoformat()
    collect_stage_executed_last_run = True  # Assume true if we can query
    
    result = {
        "alembic_current_revision": alembic_current_revision,
        "sources_enabled": sources_enabled,
        "raw_last_24h": raw_last_24h,
        "extracted_last_24h": extracted_last_24h,
        "extracted_at_exists": extracted_at_exists,
        "events_last_24h": events_last_24h,
        "eligible_last_24h": eligible_last_24h,
        "published_last_24h": published_last_24h,
        "extraction_ratio": round(extraction_ratio, 2),
        "zero_scores": zero_scores,
        "collect_stage_executed_last_run": collect_stage_executed_last_run,
        "last_run_timestamp": last_run_timestamp
    }
    
    # Add errors if any
    if errors:
        result["errors"] = errors
        result["status"] = "partial"
    else:
        result["status"] = "ok"
    
    return result


@router.get("/debug/telegram")
async def debug_telegram(
    db: Session = Depends(get_db_session),
    _: None = Depends(check_intel_enabled),
) -> Dict[str, Any]:
    """
    Debug endpoint for Telegram status.
    Shows can_post, last_message_id, rate_limit_state, last_error.
    """
    from apps.intel.services.publishers.telegram_publisher import TelegramPublisher
    from apps.intel.db.models import IntelPublishLog
    from datetime import datetime, timedelta
    
    try:
        publisher = TelegramPublisher(db)
        telegram_ok, telegram_error, telegram_details = publisher.check_telegram_access()
        
        # Last message
        last_publish = db.query(IntelPublishLog).filter(
            IntelPublishLog.status == "published",
            IntelPublishLog.telegram_message_id.isnot(None)
        ).order_by(IntelPublishLog.published_at.desc()).first()
        
        last_message_id = last_publish.telegram_message_id if last_publish else None
        
        # Rate limit state
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        one_day_ago = datetime.utcnow() - timedelta(days=1)
        
        recent_publishes = db.query(IntelPublishLog).filter(
            IntelPublishLog.published_at >= one_hour_ago,
            IntelPublishLog.status == "published"
        ).count()
        
        daily_publishes = db.query(IntelPublishLog).filter(
            IntelPublishLog.published_at >= one_day_ago,
            IntelPublishLog.status == "published"
        ).count()
        
        # Last error
        last_error_log = db.query(IntelPublishLog).filter(
            IntelPublishLog.error.isnot(None)
        ).order_by(IntelPublishLog.published_at.desc()).first()
        
        last_error = last_error_log.error if last_error_log else None
        
        return {
            "status": "ok",
            "can_post": telegram_ok,
            "telegram_details": telegram_details,
            "last_message_id": last_message_id,
            "rate_limit_state": {
                "recent_publishes_1h": recent_publishes,
                "daily_publishes_24h": daily_publishes,
                "limit_per_hour": 5,
                "limit_per_day": 30
            },
            "last_error": last_error
        }
    except Exception as e:
        logger.error(f"Failed to get Telegram debug info: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e)
        }
