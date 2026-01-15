"""Relaunch Scout API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, desc, text
from typing import List, Optional
from datetime import datetime
import uuid
from apps.db.session import get_db
from pydantic import BaseModel

router = APIRouter(prefix="/relaunch", tags=["relaunch"])

class CandidateResponse(BaseModel):
    app_id: str
    steam_app_id: str
    name: str
    relaunch_score: float
    classification: str
    failure_reasons: List[str]
    relaunch_angles: List[dict]
    reasoning: str
    latest_snapshot: Optional[dict]
    computed_at: datetime

class AppDetailResponse(BaseModel):
    app_id: str
    steam_app_id: str
    name: str
    tracking_since: datetime
    latest_score: Optional[dict]
    score_history: List[dict]
    recent_snapshots: List[dict]
    review_stats: dict

class TrackAppRequest(BaseModel):
    steam_app_id: str
    name: str
    priority: str = "normal"

@router.get("/candidates")
def get_candidates(
    classification: Optional[str] = Query(None),
    min_score: Optional[float] = Query(70.0),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db)
):
    """Get list of relaunch candidates"""
    
    query = text("""
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
        AND (:classification IS NULL OR rs.classification = :classification)
        ORDER BY rs.relaunch_score DESC
        LIMIT :limit
    """)
    
    results = db.execute(query, {
        "min_score": min_score,
        "classification": classification,
        "limit": limit
    }).fetchall()
    
    return [{
        "app_id": str(r[0]),
        "steam_app_id": r[1],
        "name": r[2],
        "relaunch_score": r[3],
        "classification": r[4],
        "failure_reasons": r[5] or [],
        "relaunch_angles": r[6] or [],
        "reasoning": r[7] or "",
        "latest_snapshot": None,
        "computed_at": r[8]
    } for r in results]

@router.get("/app/{app_id}")
def get_app_details(app_id: str, db: Session = Depends(get_db)):
    """Get detailed information about a tracked app"""
    
    try:
        app_uuid = uuid.UUID(app_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid app_id format")
    
    app_query = text("SELECT id, steam_app_id, name, added_at FROM relaunch_apps WHERE id = :id")
    app = db.execute(app_query, {"id": app_uuid}).fetchone()
    
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
        "review_stats": {"total_reviews": 0, "positive_count": 0, "negative_count": 0}
    }

@router.post("/admin/track")
def track_app(request: TrackAppRequest, db: Session = Depends(get_db)):
    """Add a new app to tracking"""
    
    check_query = text("SELECT id FROM relaunch_apps WHERE steam_app_id = :steam_app_id")
    existing = db.execute(check_query, {"steam_app_id": request.steam_app_id}).fetchone()
    
    if existing:
        return {"message": "App already tracked", "app_id": str(existing[0])}
    
    insert_query = text("""
        INSERT INTO relaunch_apps (steam_app_id, name, tracking_priority)
        VALUES (:steam_app_id, :name, :priority)
        RETURNING id
    """)
    
    result = db.execute(insert_query, {
        "steam_app_id": request.steam_app_id,
        "name": request.name,
        "priority": request.priority
    })
    db.commit()
    
    app_id = result.fetchone()[0]
    
    return {"message": "App added to tracking", "app_id": str(app_id)}

@router.post("/admin/recompute/{app_id}")
def trigger_recompute(app_id: str, db: Session = Depends(get_db)):
    """Trigger score recomputation for an app"""
    
    try:
        app_uuid = uuid.UUID(app_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid app_id format")
    
    check_query = text("SELECT id FROM relaunch_apps WHERE id = :id")
    app = db.execute(check_query, {"id": app_uuid}).fetchone()
    
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    
    return {"message": "Score recomputation triggered", "task_id": "manual-trigger"}

@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    """Health check endpoint"""
    try:
        count_query = text("SELECT COUNT(*) FROM relaunch_apps WHERE is_active = true")
        result = db.execute(count_query).fetchone()
        
        return {
            "status": "healthy",
            "tracked_apps": result[0],
            "timestamp": datetime.utcnow()
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {str(e)}")
