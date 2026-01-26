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
    filter: str = Query("all", description="Filter: all, with_reviews, with_signals, in_trends"),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Get list of games from steam_app_cache with optional filters.
    Returns: {total: int, items: List[Dict]}
    """
    from datetime import date
    
    today = date.today()
    
    # Base query - always use steam_app_cache
    base_query = """
        SELECT 
            c.steam_app_id,
            c.name,
            c.steam_url,
            c.reviews_total,
            c.positive_ratio
        FROM steam_app_cache c
    """
    
    # Apply filters
    where_clauses = []
    join_clauses = []
    
    if filter == "with_reviews":
        where_clauses.append("c.reviews_total > 0")
    elif filter == "with_signals":
        join_clauses.append("""
            INNER JOIN trends_raw_signals s ON s.steam_app_id = c.steam_app_id::bigint
            AND s.captured_at >= now() - interval '7 days'
        """)
    elif filter == "in_trends":
        join_clauses.append("""
            INNER JOIN trends_game_daily g ON g.steam_app_id = c.steam_app_id::bigint
            AND g.day = :today
        """)
    
    # Build final query
    query_sql = base_query
    if join_clauses:
        query_sql += " " + " ".join(join_clauses)
    if where_clauses:
        query_sql += " WHERE " + " AND ".join(where_clauses)
    
    query_sql += " ORDER BY COALESCE(c.reviews_total, 0) DESC LIMIT :limit"
    
    try:
        rows = db.execute(
            text(query_sql),
            {"limit": int(limit), "today": today}
        ).mappings().all()
    except Exception as e:
        # Fallback: try simple query without filters
        try:
            rows = db.execute(
                text("""
                    SELECT steam_app_id, name, steam_url, reviews_total, positive_ratio
                    FROM steam_app_cache
                    ORDER BY COALESCE(reviews_total, 0) DESC
                    LIMIT :limit
                """),
                {"limit": int(limit)}
            ).mappings().all()
        except Exception as fallback_err:
            return {"total": 0, "items": []}
    
    # Format results
    items = []
    for r in rows:
        steam_app_id = r.get("steam_app_id")
        if not steam_app_id:
            continue
        
        game_name = r.get("name") or f"App #{steam_app_id}"
        steam_url = r.get("steam_url") or f"https://store.steampowered.com/app/{steam_app_id}/"
        
        items.append({
            "steam_app_id": int(steam_app_id),
            "name": game_name,
            "game_name": game_name,
            "steam_url": steam_url,
            "reviews_total": int(r.get("reviews_total") or 0),
            "positive_ratio": float(r.get("positive_ratio") or 0.0) if r.get("positive_ratio") is not None else None,
            # Backward compatibility
            "review_count": int(r.get("reviews_total") or 0),
            "reviews": int(r.get("reviews_total") or 0),
        })
    
    # Get total count (for pagination info)
    try:
        count_query = "SELECT COUNT(*)::int as total FROM steam_app_cache"
        if where_clauses:
            count_query += " WHERE " + " AND ".join(where_clauses)
        total = db.execute(text(count_query)).scalar() or 0
    except:
        total = len(items)
    
    return {
        "total": total,
        "items": items
    }
