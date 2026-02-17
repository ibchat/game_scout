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
async def intel_health() -> Dict[str, Any]:
    """Health check for Intel module."""
    from apps.intel.policy.policy_engine import load_policy, get_policy_hash
    
    policy_loaded = False
    policy_version = None
    policy_hash = None
    
    try:
        policy = load_policy()
        policy_loaded = policy is not None
        policy_version = policy.get("version", "unknown") if policy else None
        policy_hash = get_policy_hash()
    except Exception as e:
        logger.warning(f"Failed to load policy for health check: {e}")
    
    return {
        "status": "ok" if is_intel_enabled() else "disabled",
        "module": "intel",
        "enabled": is_intel_enabled(),
        "policy_loaded": policy_loaded,
        "policy_version": policy_version,
        "policy_hash": policy_hash
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
    # TODO: Implement in Commit 12
    return {"status": "ok", "sources": []}


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


@router.post("/actions/run_pipeline")
async def run_pipeline_manually(
    db: Session = Depends(get_db_session),
    _: None = Depends(check_intel_enabled),
) -> Dict[str, Any]:
    """Manually trigger Intel pipeline task (for testing)."""
    # TODO: Implement in Commit 11
    return {"status": "ok", "message": "Pipeline task queued"}


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
