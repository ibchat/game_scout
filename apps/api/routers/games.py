from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select, func, or_
from typing import Optional
from datetime import date

from apps.api.deps import get_db_session
from apps.api.schemas.games import GameResponse, GameListResponse
from apps.db.models import Game, GameSource, GameMetricsDaily

router = APIRouter()


@router.get("", response_model=GameListResponse)
async def list_games(
    source: Optional[str] = Query(None, description="Filter by source (steam/itch)"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    from_date: Optional[date] = Query(None, description="Filter from created date"),
    to_date: Optional[date] = Query(None, description="Filter to created date"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db_session)
):
    """List games with optional filters"""
    stmt = select(Game).options(joinedload(Game.metrics))
    
    # Apply filters
    if source:
        try:
            source_enum = GameSource(source)
            stmt = stmt.where(Game.source == source_enum)
        except ValueError:
            pass
    
    if tag:
        # PostgreSQL JSONB contains
        stmt = stmt.where(Game.tags.op('@>')(f'["{tag.lower()}"]'))
    
    if from_date:
        stmt = stmt.where(func.date(Game.created_at) >= from_date)
    
    if to_date:
        stmt = stmt.where(func.date(Game.created_at) <= to_date)
    
    # Get total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.execute(count_stmt).scalar()
    
    # Apply pagination
    stmt = stmt.order_by(Game.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    
    games = db.execute(stmt).unique().scalars().all()
    
    return GameListResponse(
        games=games,
        total=total,
        page=page,
        page_size=page_size
    )