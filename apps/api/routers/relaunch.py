from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.deps import get_db_session

router = APIRouter(prefix="/relaunch", tags=["relaunch"])


class TrackAppRequest(BaseModel):
    steam_app_id: int = Field(..., ge=1)
    name: str = Field(..., min_length=1, max_length=200)
    tracking_priority: int = Field(50, ge=0, le=100)


@router.get("/health")
def relaunch_health(db: Session = Depends(get_db_session)) -> Dict[str, Any]:
    count_query = text("SELECT COUNT(*) FROM relaunch_apps WHERE is_active = true")
    tracked = db.execute(count_query).scalar() or 0
    return {
        "status": "healthy",
        "tracked_apps": int(tracked),
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/candidates")
def get_candidates(
    classification: Optional[str] = Query(None),
    min_score: float = Query(70.0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db_session),
) -> List[Dict[str, Any]]:
    # Fix Postgres AmbiguousParameter: avoid `:classification IS NULL` checks
    sql = """
        SELECT
            ra.id as app_id,
            ra.steam_app_id,
            ra.name,
            rs.relaunch_score,
            rs.classification,
            rs.failure_reasons,
            rs.relaunch_angles,
            rs.reasoning_text,
            rs.computed_at
        FROM relaunch_scores rs
        JOIN relaunch_apps ra ON rs.app_id = ra.id
        WHERE rs.relaunch_score >= :min_score
    """

    params: Dict[str, Any] = {"min_score": float(min_score), "limit": int(limit)}

    if classification:
        sql += " AND rs.classification = :classification"
        params["classification"] = classification

    sql += " ORDER BY rs.relaunch_score DESC LIMIT :limit"

    rows = db.execute(text(sql), params).fetchall()

    return [
        {
            "app_id": str(r[0]),
            "steam_app_id": r[1],
            "name": r[2],
            "relaunch_score": float(r[3]) if r[3] is not None else 0.0,
            "classification": r[4],
            "failure_reasons": r[5] or [],
            "relaunch_angles": r[6] or [],
            "reasoning": r[7] or "",
            "latest_snapshot": None,
            "computed_at": r[8],
        }
        for r in rows
    ]


@router.get("/app/{app_id}")
def get_app_details(app_id: str, db: Session = Depends(get_db_session)) -> Dict[str, Any]:
    try:
        app_uuid = uuid.UUID(app_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid app_id format")

    app = db.execute(
        text("SELECT id, steam_app_id, name, added_at FROM relaunch_apps WHERE id = :id"),
        {"id": app_uuid},
    ).fetchone()

    if not app:
        raise HTTPException(status_code=404, detail="App not found")

    return {
        "app_id": str(app[0]),
        "steam_app_id": app[1],
        "name": app[2],
        "tracking_since": app[3],
        "latest_score": None,
        "score_history": [],
        "recent_snapshots": [],
        "review_stats": {"total_reviews": 0, "positive_count": 0, "negative_count": 0},
    }


@router.post("/admin/track")
def track_app(request: TrackAppRequest, db: Session = Depends(get_db_session)) -> Dict[str, Any]:
    existing = db.execute(
        text("SELECT id FROM relaunch_apps WHERE steam_app_id = :steam_app_id"),
        {"steam_app_id": request.steam_app_id},
    ).fetchone()

    if existing:
        return {"status": "exists", "app_id": str(existing[0])}

    new_id = db.execute(
        text(
            """
            INSERT INTO relaunch_apps (steam_app_id, name, tracking_priority)
            VALUES (:sid, :name, :priority)
            RETURNING id
            """
        ),
        {"sid": request.steam_app_id, "name": request.name, "priority": request.tracking_priority},
    ).scalar()

    db.commit()
    return {"status": "ok", "app_id": str(new_id)}
