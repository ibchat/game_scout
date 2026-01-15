from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from apps.api.deps import get_db_session

router = APIRouter()


@router.get("/health")
async def health_check(db: Session = Depends(get_db_session)):
    """Health check endpoint"""
    try:
        # Test database connection
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "database": db_status,
        "service": "game_scout_api"
    }