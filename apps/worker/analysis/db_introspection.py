"""
Database introspection utilities for Emerging Engine v4.
Detects actual column names in database tables.
"""
import logging
from typing import Optional, Union
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Приоритетный порядок поиска колонки app_id
APP_ID_COLUMN_PRIORITY = [
    "app_id",
    "steam_app_id",
    "appid",
    "steamid",
    "game_id",
    "steam_game_id"
]


def detect_steam_review_app_id_column(db: Union[Session, Connection, Engine]) -> str:
    """
    Returns column name for Steam app id in steam_review_daily.
    
    Prefer order: app_id, steam_app_id, appid, steamid, game_id.
    Raise RuntimeError if none found.
    
    Args:
        db: SQLAlchemy Session, Connection, or Engine object
        
    Returns:
        str: Column name (e.g., "steam_app_id")
        
    Raises:
        RuntimeError: If no suitable column found
    """
    try:
        # Поддерживаем Session, Connection, и Engine
        if isinstance(db, Session):
            # Для Session используем execute напрямую
            # Используем autocommit для information_schema запросов
            result = db.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'steam_review_daily' 
                  AND table_schema = 'public'
                ORDER BY ordinal_position
            """))
            available_columns = {row[0] for row in result}
        elif isinstance(db, Engine):
            # Для Engine создаём connection
            with db.connect() as conn:
                result = conn.execute(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'steam_review_daily' 
                      AND table_schema = 'public'
                    ORDER BY ordinal_position
                """))
                available_columns = {row[0] for row in result}
        else:
            # Connection
            result = db.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'steam_review_daily' 
                  AND table_schema = 'public'
                ORDER BY ordinal_position
            """))
            available_columns = {row[0] for row in result}
        
        # Ищем по приоритету
        for preferred_name in APP_ID_COLUMN_PRIORITY:
            if preferred_name in available_columns:
                logger.info(f"Detected app_id column in steam_review_daily: {preferred_name}")
                return preferred_name
        
        # Если ничего не нашли, выводим доступные колонки для отладки
        logger.error(f"No app_id column found in steam_review_daily. Available columns: {sorted(available_columns)}")
        raise RuntimeError(
            f"No suitable app_id column found in steam_review_daily. "
            f"Available columns: {sorted(available_columns)}. "
            f"Expected one of: {APP_ID_COLUMN_PRIORITY}"
        )
        
    except Exception as e:
        logger.error(f"Failed to detect app_id column in steam_review_daily: {e}", exc_info=True)
        raise RuntimeError(f"Failed to detect app_id column: {e}") from e


def detect_reviews_count_column(conn: Connection, table_name: str = "steam_review_daily") -> Optional[str]:
    """
    Detects column name for reviews count in given table.
    
    Priority: reviews_count, review_count, reviews, count, total_reviews
    
    Args:
        conn: SQLAlchemy connection
        table_name: Table to inspect
        
    Returns:
        Column name or None if not found
    """
    priority = ["reviews_count", "review_count", "reviews", "count", "total_reviews"]
    
    try:
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = :table_name 
              AND table_schema = 'public'
        """), {"table_name": table_name})
        
        available = {row[0] for row in result}
        
        for name in priority:
            if name in available:
                return name
                
        return None
    except Exception:
        return None


def detect_positive_ratio_column(conn: Connection, table_name: str = "steam_review_daily") -> Optional[str]:
    """
    Detects column name for positive ratio/percent in given table.
    
    Priority: positive_ratio, positive_percent, positive_pct, all_positive_percent
    
    Args:
        conn: SQLAlchemy connection
        table_name: Table to inspect
        
    Returns:
        Column name or None if not found
    """
    priority = ["positive_ratio", "positive_percent", "positive_pct", "all_positive_percent", "all_positive_ratio"]
    
    try:
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = :table_name 
              AND table_schema = 'public'
        """), {"table_name": table_name})
        
        available = {row[0] for row in result}
        
        for name in priority:
            if name in available:
                return name
                
        return None
    except Exception:
        return None
