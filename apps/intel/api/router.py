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
    return {
        "status": "ok" if is_intel_enabled() else "disabled",
        "module": "intel",
        "enabled": is_intel_enabled()
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
