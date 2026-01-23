"""
Worker database utilities.
Provides get_engine() for worker tasks that need direct engine access.
"""
from sqlalchemy import create_engine
import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@postgres:5432/game_scout"
)

_engine = None


def get_engine():
    """Get SQLAlchemy engine for worker tasks"""
    global _engine
    if _engine is None:
        _engine = create_engine(DATABASE_URL, pool_pre_ping=True, echo=False)
    return _engine
