from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.deps import get_db_session

router = APIRouter(prefix="/games", tags=["Games"])


@router.get("/health")
def games_health() -> Dict[str, Any]:
    return {"status": "ok"}


@router.get("/list")
def games_list(
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db_session),
) -> List[Dict[str, Any]]:
    """
    Пытаемся отдать список игр из локальной таблицы (если она есть).
    Поддерживаем варианты:
      - steam_games (steam_app_id, name, review_count)
      - games (steam_app_id, name, review_count)
    """
    queries = [
        """
        SELECT steam_app_id, name, review_count
        FROM steam_games
        ORDER BY COALESCE(review_count, 0) DESC
        LIMIT :limit
        """,
        """
        SELECT steam_app_id, name, review_count
        FROM games
        ORDER BY COALESCE(review_count, 0) DESC
        LIMIT :limit
        """,
    ]

    rows = None
    for q in queries:
        try:
            rows = db.execute(text(q), {"limit": int(limit)}).mappings().all()
            break
        except Exception:
            continue

    if not rows:
        return []

    return [
        {
            "steam_app_id": str(r.get("steam_app_id")),
            "name": r.get("name"),
            "review_count": int(r.get("review_count") or 0),
        }
        for r in rows
    ]