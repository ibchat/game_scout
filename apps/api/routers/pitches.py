from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from typing import Optional
from uuid import UUID
from datetime import date

from apps.api.deps import get_db_session
from apps.api.schemas.pitches import PitchCreate, PitchResponse, PitchListResponse
from apps.api.services.pitch_service import create_pitch_and_score
from apps.db.models import Pitch, PitchScore, PitchStatus, Verdict

router = APIRouter()


@router.post("", response_model=PitchResponse, status_code=201)
async def create_pitch(
    pitch_data: PitchCreate,
    db: Session = Depends(get_db_session)
):
    """Create a new pitch and enqueue scoring"""
    try:
        pitch = create_pitch_and_score(db, pitch_data)
        return pitch
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{pitch_id}", response_model=PitchResponse)
async def get_pitch(
    pitch_id: UUID,
    db: Session = Depends(get_db_session)
):
    """Get a specific pitch by ID"""
    stmt = select(Pitch).where(Pitch.id == pitch_id)
    pitch = db.execute(stmt).scalar_one_or_none()
    
    if not pitch:
        raise HTTPException(status_code=404, detail="Pitch not found")
    
    return pitch


@router.get("", response_model=PitchListResponse)
async def list_pitches(
    status: Optional[str] = Query(None, description="Filter by status"),
    verdict: Optional[str] = Query(None, description="Filter by verdict"),
    from_date: Optional[date] = Query(None, description="Filter from date"),
    to_date: Optional[date] = Query(None, description="Filter to date"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db_session)
):
    """List pitches with optional filters"""
    stmt = select(Pitch)
    
    # Apply filters
    if status:
        try:
            status_enum = PitchStatus(status)
            stmt = stmt.where(Pitch.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    
    if verdict:
        # Join with pitch_scores to filter by verdict
        try:
            verdict_enum = Verdict(verdict)
            stmt = stmt.join(PitchScore).where(PitchScore.verdict == verdict_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid verdict: {verdict}")
    
    if from_date:
        stmt = stmt.where(Pitch.created_at >= from_date)
    
    if to_date:
        stmt = stmt.where(Pitch.created_at <= to_date)
    
    # Get total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.execute(count_stmt).scalar()
    
    # Apply pagination
    stmt = stmt.order_by(Pitch.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    
    pitches = db.execute(stmt).scalars().all()
    
    return PitchListResponse(
        pitches=pitches,
        total=total,
        page=page,
        page_size=page_size
    )