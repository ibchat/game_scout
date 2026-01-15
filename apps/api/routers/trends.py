from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from datetime import date, datetime

from apps.api.deps import get_db_session
from apps.api.schemas.trends import TrendResponse, TrendListResponse
from apps.db.models import TrendsDaily

router = APIRouter()


@router.get("/today", response_model=TrendListResponse)
async def get_today_trends(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db_session)
):
    """Get today's top trends sorted by velocity"""
    today = date.today()
    
    stmt = select(TrendsDaily).where(
        TrendsDaily.date == today
    ).order_by(
        TrendsDaily.velocity.desc()
    ).limit(limit)
    
    trends = db.execute(stmt).scalars().all()
    
    return TrendListResponse(
        trends=trends,
        total=len(trends)
    )


@router.get("", response_model=TrendListResponse)
async def get_trends(
    from_date: date = Query(..., description="Start date"),
    to_date: date = Query(None, description="End date (defaults to today)"),
    signal: str = Query(None, description="Filter by signal"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db_session)
):
    """Get trends for a date range"""
    if to_date is None:
        to_date = date.today()
    
    stmt = select(TrendsDaily).where(
        TrendsDaily.date >= from_date,
        TrendsDaily.date <= to_date
    )
    
    if signal:
        stmt = stmt.where(TrendsDaily.signal == signal.lower())
    
    stmt = stmt.order_by(
        TrendsDaily.date.desc(),
        TrendsDaily.velocity.desc()
    ).limit(limit)
    
    trends = db.execute(stmt).scalars().all()
    
    return TrendListResponse(
        trends=trends,
        total=len(trends)
    )