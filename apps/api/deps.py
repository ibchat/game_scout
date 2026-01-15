from fastapi import Depends
from sqlalchemy.orm import Session
from apps.db.session import get_db


def get_db_session(db: Session = Depends(get_db)) -> Session:
    """FastAPI dependency for database session"""
    return db