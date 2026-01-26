"""
System Admin Dashboard Endpoints
Provides system health, trends pipeline status, and quick actions.
"""
import json
import logging
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.deps import get_db_session
# Import emerging games logic (will call the endpoint function)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/system", tags=["System Admin"])


@router.get("/summary")
async def get_system_summary(
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Comprehensive system summary for dashboard.
    Returns health, trends pipeline status, emerging games, and diagnostics.
    """
    result: Dict[str, Any] = {}
    
    # Health
    health = {}
    try:
        # API health (always ok if we're here)
        health["api"] = {"status": "ok"}
        
        # DB health
        db_check = db.execute(text("SELECT 1")).scalar()
        health["database"] = {"status": "ok" if db_check else "error"}
        
        # Worker health (check if celery is running - simplified)
        health["worker"] = {"status": "unknown"}  # Would need celery inspect
        
    except Exception as e:
        health["database"] = {"status": "error", "error": str(e)}
    
    result["health"] = health
    
    # Trends Today
    today = date.today()
    three_years_ago = today - timedelta(days=365 * 3)
    trends_today: Dict[str, Any] = {}
    
    # Seed apps count
    try:
        seed_count = db.execute(
            text("SELECT COUNT(*)::int FROM trends_seed_apps WHERE is_active = true")
        ).scalar() or 0
        trends_today["seed_apps"] = seed_count
    except:
        trends_today["seed_apps"] = 0
    
    # Jobs count
    try:
        jobs_count = db.execute(
            text("""
                SELECT COUNT(*)::int
                FROM trend_jobs
                WHERE status IN ('queued', 'running')
            """)
        ).scalar() or 0
        trends_today["jobs_queued"] = jobs_count
    except:
        trends_today["jobs_queued"] = 0
    
    # Reviews count (today)
    try:
        reviews_count = db.execute(
            text("""
                SELECT COUNT(*)::int
                FROM steam_review_daily
                WHERE day = :today
            """),
            {"today": today}
        ).scalar() or 0
        trends_today["reviews_count"] = reviews_count
    except:
        trends_today["reviews_count"] = 0
    
    # Game daily count
    try:
        game_daily_count = db.execute(
            text("""
                SELECT COUNT(*)::int
                FROM trends_game_daily
                WHERE day = :today
            """),
            {"today": today}
        ).scalar() or 0
        trends_today["trends_game_daily"] = game_daily_count
    except:
        trends_today["trends_game_daily"] = 0
    
    # Get emerging count - call the internal function
    try:
        # Простой запрос для подсчета emerging без вызова сложной функции
        emerging_count_query = db.execute(
            text("""
                SELECT COUNT(DISTINCT tgd.steam_app_id)::int
                FROM trends_game_daily tgd
                JOIN trends_seed_apps seed ON seed.steam_app_id = tgd.steam_app_id
                WHERE seed.is_active = true
                  AND tgd.day = (
                      SELECT MAX(day) FROM trends_game_daily WHERE steam_app_id = tgd.steam_app_id
                  )
                  AND tgd.reviews_delta_7d > 0
            """)
        ).scalar() or 0
        trends_today["emerging_count"] = emerging_count_query
    except Exception as e:
        trends_today["emerging_count"] = 0
        logger.warning(f"Failed to get emerging count: {e}")
    
    # Signals coverage and freshness - ТОЛЬКО реальные источники из trends_raw_signals
    signals_coverage = {}
    signals_freshness = {}
    
    try:
        today = date.today()
        week_ago = today - timedelta(days=7)
    
    # Total seed apps
        total_seed_apps = trends_today.get("seed_apps", 0)
    
    # Получаем реальные источники из БД
        real_sources = db.execute(
            text("""
                SELECT DISTINCT source
                FROM trends_raw_signals
                WHERE source IS NOT NULL
                ORDER BY source
            """)
        ).scalars().all()
    
    # Steam Reviews coverage - считаем за 24 часа для актуальности
        if 'steam_reviews' in real_sources:
            steam_stats = db.execute(
                text("""
                    SELECT 
                        COUNT(DISTINCT steam_app_id)::int as games_with_signals,
                        COUNT(*)::int as signals_total,
                        MAX(captured_at) as last_captured_at
                    FROM trends_raw_signals
                    WHERE captured_at >= now() - interval '24 hours'
                      AND source = 'steam_reviews'
                      AND value_numeric IS NOT NULL
                """)
            ).mappings().first()
            
            games_with_steam = steam_stats["games_with_signals"] if steam_stats else 0
            signals_total_steam = steam_stats["signals_total"] if steam_stats else 0
            steam_last_captured = steam_stats["last_captured_at"] if steam_stats else None
            
            signals_coverage["steam_reviews"] = {
                "apps_with_signals": games_with_steam,
                "signals_total": signals_total_steam,
                "total_apps": total_seed_apps,
                "pct": round((games_with_steam / total_seed_apps * 100) if total_seed_apps > 0 else 0, 1),
                "active": games_with_steam > 0
            }
            signals_freshness["steam_reviews"] = {
                "last_captured_at": steam_last_captured.isoformat() if steam_last_captured else None,
                "age_minutes": int((datetime.now() - steam_last_captured.replace(tzinfo=None)).total_seconds() / 60) if steam_last_captured else None
            }
        else:
            signals_coverage["steam_reviews"] = {"apps_with_signals": 0, "signals_total": 0, "total_apps": 0, "pct": 0, "active": False}
            signals_freshness["steam_reviews"] = {"last_captured_at": None, "age_minutes": None}
    
    # Steam Store coverage - считаем за 24 часа
        if 'steam_store' in real_sources:
            store_stats = db.execute(
                text("""
                    SELECT 
                        COUNT(DISTINCT steam_app_id)::int as games_with_signals,
                        COUNT(*)::int as signals_total,
                        MAX(captured_at) as last_captured_at
                    FROM trends_raw_signals
                    WHERE captured_at >= now() - interval '24 hours'
                      AND source = 'steam_store'
                      AND value_numeric IS NOT NULL
                """)
            ).mappings().first()
            
            games_with_store = store_stats["games_with_signals"] if store_stats else 0
            signals_total_store = store_stats["signals_total"] if store_stats else 0
            store_last_captured = store_stats["last_captured_at"] if store_stats else None
            
            signals_coverage["steam_store"] = {
                "apps_with_signals": games_with_store,
                "signals_total": signals_total_store,
                "total_apps": total_seed_apps,
                "pct": round((games_with_store / total_seed_apps * 100) if total_seed_apps > 0 else 0, 1),
                "active": games_with_store > 0
            }
            signals_freshness["steam_store"] = {
                "last_captured_at": store_last_captured.isoformat() if store_last_captured else None,
                "age_minutes": int((datetime.now() - store_last_captured.replace(tzinfo=None)).total_seconds() / 60) if store_last_captured and hasattr(store_last_captured, 'replace') else None
            }
        else:
            signals_coverage["steam_store"] = {"apps_with_signals": 0, "signals_total": 0, "total_apps": 0, "pct": 0, "active": False}
            signals_freshness["steam_store"] = {"last_captured_at": None, "age_minutes": None}
    
    # Reddit - проверяем наличие, но не считаем активным если нет данных
        reddit_stats = db.execute(
            text("""
                SELECT 
                    COUNT(DISTINCT steam_app_id)::int as games_with_signals,
                    COUNT(*)::int as signals_total,
                    MAX(captured_at) as last_captured_at
                FROM trends_raw_signals
                WHERE captured_at >= now() - interval '24 hours'
                  AND source = 'reddit'
                  AND value_numeric IS NOT NULL
            """)
        ).mappings().first()
    
        games_with_reddit = reddit_stats["games_with_signals"] if reddit_stats else 0
        signals_total_reddit = reddit_stats["signals_total"] if reddit_stats else 0
        reddit_last_captured = reddit_stats["last_captured_at"] if reddit_stats else None
    
        signals_coverage["reddit"] = {
            "apps_with_signals": games_with_reddit,
            "signals_total": signals_total_reddit,
            "total_apps": total_seed_apps,
            "pct": round((games_with_reddit / total_seed_apps * 100) if total_seed_apps > 0 else 0, 1),
            "active": games_with_reddit > 0
        }
        signals_freshness["reddit"] = {
            "last_captured_at": reddit_last_captured.isoformat() if reddit_last_captured else None,
            "age_minutes": int((datetime.now() - reddit_last_captured.replace(tzinfo=None)).total_seconds() / 60) if reddit_last_captured and hasattr(reddit_last_captured, 'replace') else None
        }
    
    # YouTube - проверяем наличие, но не считаем активным если нет данных
        youtube_stats = db.execute(
            text("""
                SELECT 
                    COUNT(DISTINCT steam_app_id)::int as games_with_signals,
                    COUNT(*)::int as signals_total,
                    MAX(captured_at) as last_captured_at
                FROM trends_raw_signals
                WHERE captured_at >= now() - interval '24 hours'
                  AND source = 'youtube'
                  AND value_numeric IS NOT NULL
            """)
        ).mappings().first()
    
        games_with_youtube = youtube_stats["games_with_signals"] if youtube_stats else 0
        signals_total_youtube = youtube_stats["signals_total"] if youtube_stats else 0
        youtube_last_captured = youtube_stats["last_captured_at"] if youtube_stats else None
    
        signals_coverage["youtube"] = {
        "apps_with_signals": games_with_youtube,
        "signals_total": signals_total_youtube,
        "total_apps": total_seed_apps,
        "pct": round((games_with_youtube / total_seed_apps * 100) if total_seed_apps > 0 else 0, 1),
        "active": games_with_youtube > 0
        }
        signals_freshness["youtube"] = {
        "last_captured_at": youtube_last_captured.isoformat() if youtube_last_captured else None,
        "age_minutes": int((datetime.now() - youtube_last_captured.replace(tzinfo=None)).total_seconds() / 60) if youtube_last_captured and hasattr(youtube_last_captured, 'replace') else None
        }
    
    except Exception as e:
        logger.error(f"Failed to compute signals coverage: {e}", exc_info=True)
        signals_coverage = {
            "steam_reviews": {"apps_with_signals": 0, "signals_total": 0, "total_apps": 0, "pct": 0, "active": False},
            "steam_store": {"apps_with_signals": 0, "signals_total": 0, "total_apps": 0, "pct": 0, "active": False},
            "reddit": {"apps_with_signals": 0, "signals_total": 0, "total_apps": 0, "pct": 0, "active": False},
            "youtube": {"apps_with_signals": 0, "signals_total": 0, "total_apps": 0, "pct": 0, "active": False}
        }
        signals_freshness = {
            "steam_reviews": {"last_captured_at": None, "age_minutes": None},
            "steam_store": {"last_captured_at": None, "age_minutes": None},
            "reddit": {"last_captured_at": None, "age_minutes": None},
            "youtube": {"last_captured_at": None, "age_minutes": None}
        }
    
    # Numeric signals summary
    try:
        signals = db.execute(
            text("""
                SELECT 
                    signal_type,
                    COUNT(*)::int as rows,
                    COUNT(CASE WHEN value_numeric IS NOT NULL THEN 1 END)::int as numeric_rows
                FROM trends_raw_signals
                WHERE DATE(captured_at) = :today
                GROUP BY signal_type
                ORDER BY signal_type
            """),
            {"today": today}
        ).mappings().all()
        
        # Map signal types to sources and usage
        signal_mapping = {
            "all_reviews_count": {"source": "Steam", "usage": "Emerging, Evergreen filter", "purpose": "Масштаб игры"},
            "recent_reviews_count_30d": {"source": "Steam", "usage": "Emerging score", "purpose": "Скорость роста"},
            "all_positive_ratio": {"source": "Steam", "usage": "Quality filter", "purpose": "Качество аудитории"},
            "reviews_delta_7d": {"source": "Steam", "usage": "Emerging score", "purpose": "Рост за неделю"},
            "reviews_delta_1d": {"source": "Steam", "usage": "Emerging score", "purpose": "Рост за день"},
        }
        
        # Обогащаем сигналы информацией об источнике из trends_raw_signals
        signals_numeric_enriched = []
        for s in signals:
            # Получаем source для этого signal_type из trends_raw_signals
            source_info = db.execute(
                text("""
                    SELECT DISTINCT source
                    FROM trends_raw_signals
                    WHERE signal_type = :signal_type
                      AND captured_at::date = :today
                    LIMIT 1
                """),
                {"signal_type": s["signal_type"], "today": today}
            ).scalar()
            
            signals_numeric_enriched.append({
                "signal_type": s["signal_type"],
                "rows": s["rows"],
                "numeric_rows": s["numeric_rows"],
                "source": source_info or signal_mapping.get(s["signal_type"], {}).get("source", "Unknown"),
                "usage": signal_mapping.get(s["signal_type"], {}).get("usage", "Не используется"),
                "purpose": signal_mapping.get(s["signal_type"], {}).get("purpose", "Не определено")
            })
        
        trends_today["signals_numeric"] = signals_numeric_enriched
    except Exception:
        trends_today["signals_numeric"] = []
    
    trends_today["signals_coverage"] = signals_coverage
    trends_today["signals_freshness"] = signals_freshness
    
    # Emerging influence analysis (based on actual brain components)
    try:
        # Use emerging_count from trends_today (already computed)
        emerging_count = trends_today.get("emerging_count", 0)
        
        # Count filtered evergreen giants (will be computed later in diagnostics)
        filtered_evergreen = 0  # Will be set from diagnostics
        
        # Calculate source influence - ТОЛЬКО реальные источники
        steam_reviews_pct = signals_coverage.get("steam_reviews", {}).get("pct", 0) if signals_coverage.get("steam_reviews", {}).get("active", False) else 0
        steam_store_pct = signals_coverage.get("steam_store", {}).get("pct", 0) if signals_coverage.get("steam_store", {}).get("active", False) else 0
        reddit_pct = signals_coverage.get("reddit", {}).get("pct", 0) if signals_coverage.get("reddit", {}).get("active", False) else 0
        youtube_pct = signals_coverage.get("youtube", {}).get("pct", 0) if signals_coverage.get("youtube", {}).get("active", False) else 0
        
        # Analyze which sources contribute to emerging
        sources_contribution = {
            "steam_reviews": steam_reviews_pct,
            "steam_store": steam_store_pct
        }
        
        # Добавляем только активные источники
        if reddit_pct > 0:
            sources_contribution["reddit"] = reddit_pct
        if youtube_pct > 0:
            sources_contribution["youtube"] = youtube_pct
        
        emerging_influence = {
            "games_found": emerging_count,
            "filtered_evergreen": filtered_evergreen,
            "sources_contribution": sources_contribution,
            "computed_from": "signals_coverage"
        }
        trends_today["emerging_influence"] = emerging_influence
    except Exception:
        trends_today["emerging_influence"] = {
            "games_found": 0,
            "filtered_evergreen": 0,
            "sources_contribution": {"steam_reviews": 0, "reddit": 0, "youtube": 0},
            "computed_from": "fallback"
        }
    
    # Blind spots detection (based on actual data)
    blind_spots = []
    try:
        # Check Reddit participation - только если есть в БД
        reddit_coverage = signals_coverage.get("reddit", {})
        if not reddit_coverage.get("active", False):
            blind_spots.append({
                "message": "Reddit подключён, но не участвует в scoring (нет данных в trends_raw_signals)",
                "severity": "medium"
            })
        
        # Check YouTube participation
        youtube_coverage = signals_coverage.get("youtube", {})
        if not youtube_coverage.get("active", False):
            blind_spots.append({
                "message": "YouTube подключён, но не участвует в scoring (нет данных в trends_raw_signals)",
                "severity": "medium"
            })
        
        # Check for missing temporal deltas
        missing_deltas = db.execute(
            text("""
                SELECT COUNT(DISTINCT s.steam_app_id)::int
                FROM trends_seed_apps s
                LEFT JOIN trends_game_daily g ON g.steam_app_id = s.steam_app_id
                  AND g.day >= :week_ago
                WHERE s.is_active = true
                  AND g.reviews_delta_7d IS NULL
            """),
            {"week_ago": week_ago}
        ).scalar() or 0
        
        if missing_deltas > 0:
            pct = round((missing_deltas / total_seed_apps * 100) if total_seed_apps > 0 else 0, 1)
            blind_spots.append({
                "message": f"Нет временных дельт >7 дней для {pct}% игр",
                "severity": "low"
            })
    except Exception:
        pass
    
    trends_today["blind_spots"] = blind_spots
    
    result["trends_today"] = trends_today
    
    # Freshness
    freshness = {}
    
    try:
        max_fetched = db.execute(
            text("SELECT MAX(updated_at) FROM steam_app_facts")
        ).scalar()
        freshness["steam_app_facts_max_fetched_at"] = max_fetched.isoformat() if max_fetched else None
    except Exception:
        freshness["steam_app_facts_max_fetched_at"] = None
    
    try:
        max_computed = db.execute(
            text("SELECT MAX(computed_at) FROM steam_review_daily")
        ).scalar()
        freshness["steam_review_daily_max_computed_at"] = max_computed.isoformat() if max_computed else None
    except Exception:
        freshness["steam_review_daily_max_computed_at"] = None
    
    try:
        max_updated = db.execute(
            text("SELECT MAX(updated_at) FROM trend_jobs")
        ).scalar()
        freshness["trend_jobs_max_updated_at"] = max_updated.isoformat() if max_updated else None
    except Exception:
        freshness["trend_jobs_max_updated_at"] = None
    
    try:
        max_day = db.execute(
            text("SELECT MAX(day) FROM trends_game_daily")
        ).scalar()
        freshness["trends_game_daily_max_day"] = max_day.isoformat() if max_day else None
    except Exception:
        freshness["trends_game_daily_max_day"] = None
    
    result["freshness"] = freshness
    
    # Engine v4: Events 24h summary
    from datetime import datetime, timedelta
    try:
        events_24h = db.execute(
            text("""
                SELECT 
                    source,
                    COUNT(*)::int as events_total,
                    COUNT(*) FILTER (WHERE matched_steam_app_id IS NOT NULL)::int as matched,
                    COUNT(*) FILTER (WHERE matched_steam_app_id IS NULL)::int as unmatched,
                    MAX(published_at) as last_published_at
                FROM trends_raw_events
                WHERE captured_at >= now() - interval '24 hours'
                GROUP BY source
                ORDER BY events_total DESC
            """)
        ).mappings().all()
        
        events_by_source = {}
        top_events = []
        
        for row in events_24h:
            source = row["source"]
            events_by_source[source] = {
                "events_total": row["events_total"],
                "matched": row["matched"],
                "unmatched": row["unmatched"],
                "last_published_at": row["last_published_at"].isoformat() if row["last_published_at"] else None
            }
        
        # Get top 20 events with game names
        top_events_rows = db.execute(
            text("""
                SELECT 
                    e.source,
                    e.title,
                    e.url,
                    e.published_at,
                    e.matched_steam_app_id,
                    COALESCE(c.name, f.name, 'App ' || e.matched_steam_app_id::text) as game_name
                FROM trends_raw_events e
                LEFT JOIN steam_app_cache c ON c.steam_app_id = e.matched_steam_app_id::bigint
                LEFT JOIN steam_app_facts f ON f.steam_app_id = e.matched_steam_app_id
                WHERE e.captured_at >= now() - interval '24 hours'
                  AND e.matched_steam_app_id IS NOT NULL
                ORDER BY e.published_at DESC
                LIMIT 20
            """)
        ).mappings().all()
        
        for row in top_events_rows:
            top_events.append({
                "source": row["source"],
                "title": row["title"],
                "url": row["url"],
                "published_at": row["published_at"].isoformat() if row["published_at"] else None,
                "steam_app_id": row["matched_steam_app_id"],
                "game_name": row["game_name"]
            })
        
        result["events_24h"] = {
            "events_by_source": events_by_source,
            "top_events": top_events
        }
    except Exception as e:
        logger.warning(f"Failed to get events_24h: {e}")
        result["events_24h"] = {"events_by_source": {}, "top_events": []}
    
    # Emerging Top 20 - упрощенный запрос без вызова сложной функции
    # Это временное решение, чтобы endpoint не падал
    # Rollback any pending/failed transaction to ensure clean state
    try:
        db.rollback()
    except Exception:
        pass
    
    # Простой запрос для получения топ игр с данными
    try:
        games_query = db.execute(
            text("""
                SELECT DISTINCT
                    tgd.steam_app_id,
                    COALESCE(c.name, 'App #' || tgd.steam_app_id::text) as game_name,
                    COALESCE(c.steam_url, 'https://store.steampowered.com/app/' || tgd.steam_app_id::text || '/') as steam_url,
                    tgd.reviews_total,
                    tgd.reviews_delta_7d,
                    tgd.positive_ratio
                FROM trends_game_daily tgd
                JOIN trends_seed_apps seed ON seed.steam_app_id = tgd.steam_app_id
                LEFT JOIN steam_app_cache c ON c.steam_app_id = tgd.steam_app_id::bigint
                WHERE seed.is_active = true
                  AND tgd.day = (
                      SELECT MAX(day) FROM trends_game_daily WHERE steam_app_id = tgd.steam_app_id
                  )
                  AND tgd.reviews_delta_7d > 0
                ORDER BY tgd.reviews_delta_7d DESC
                LIMIT 20
            """)
        ).mappings().all()
        
        games = []
        for idx, row in enumerate(games_query, 1):
            games.append({
                "steam_app_id": row["steam_app_id"],
                "game_name": row["game_name"],
                "name": row["game_name"],
                "steam_url": row["steam_url"],
                "reviews_total": row["reviews_total"],
                "reviews_delta_7d": row["reviews_delta_7d"],
                "positive_ratio": float(row["positive_ratio"]) if row["positive_ratio"] else None,
                "emerging_score": float(row["reviews_delta_7d"] or 0),  # Простой score
                "rank": idx
            })
        
        logger.info(f"Simple emerging query returned {len(games)} games")
        
        # Format games for dashboard (games уже получены из упрощенного запроса)
        emerging_top20 = []
        for game in games:
            app_id = game.get("steam_app_id")
            if not app_id:
                continue
            
            # Форматируем для dashboard с минимальными полями
            formatted = {
                "rank": game.get("rank", 0),
                "steam_app_id": app_id,
                "name": game.get("game_name") or game.get("name") or f"App #{app_id}",
                "game_name": game.get("game_name") or game.get("name") or f"App #{app_id}",
                "steam_url": game.get("steam_url") or f"https://store.steampowered.com/app/{app_id}/",
                "reviews_total": game.get("reviews_total"),
                "positive_ratio": game.get("positive_ratio"),
                "reviews_delta_7d": game.get("reviews_delta_7d"),
                "score": game.get("emerging_score", 0),
                "trend_score": game.get("emerging_score", 0),
                "emerging_score": game.get("emerging_score", 0),
                "verdict": "Weak signal",  # Простой fallback
                "confidence_score": 50,  # Простой fallback
                "confidence_level": "MEDIUM",  # Простой fallback
                "stage": "CONFIRMING",  # Простой fallback
                "why_now": f"Рост отзывов на {game.get('reviews_delta_7d', 0)} за 7 дней",
                "signals_used": ["steam_reviews"],
                "evidence": [],  # Пустой массив для упрощения
                "score_components": {}  # Пустой объект для упрощения
            }
            emerging_top20.append(formatted)
        
        result["emerging_top20"] = emerging_top20
    except Exception as e:
        logger.error(f"Failed to get emerging top 20: {e}", exc_info=True)
        result["emerging_top20"] = []
    
    # Diagnostics
    diagnostics = {}
    
    # Seeds missing numeric signals
    try:
        missing_signals = db.execute(
            text("""
                SELECT COUNT(DISTINCT s.steam_app_id)::int
                FROM trends_seed_apps s
                LEFT JOIN trends_game_daily g ON g.steam_app_id = s.steam_app_id AND g.day = :today
                WHERE s.is_active = true
                  AND (g.reviews_total IS NULL AND g.positive_ratio IS NULL)
            """),
            {"today": today}
        ).scalar() or 0
        diagnostics["seeds_missing_numeric_signals"] = missing_signals
    except Exception:
        diagnostics["seeds_missing_numeric_signals"] = 0
    
    # Filtered evergreen giants
    try:
        filtered = db.execute(
            text("""
                SELECT COUNT(*)::int
                FROM trends_game_daily g
                JOIN steam_app_facts f ON f.steam_app_id = g.steam_app_id
                WHERE g.day = :today
                  AND f.release_date < :three_years_ago
                  AND g.reviews_total >= 10000
                  AND (g.reviews_delta_7d IS NULL OR g.reviews_delta_7d < 500)
            """),
            {"today": today, "three_years_ago": three_years_ago}
        ).scalar() or 0
        diagnostics["filtered_evergreen_giants"] = filtered
    except Exception:
        diagnostics["filtered_evergreen_giants"] = 0
    
    result["diagnostics"] = diagnostics
    
    return result


@router.post("/action")
async def trigger_system_action(
    request: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Trigger system actions: seed, collect, ingest_reviews, aggregate, verify
    Engine v4: collect_events, match_events, generate_aliases, events_to_signals
    """
    action = request.get("action", "")
    request_body = request  # Full request body for additional params
    
    if action == "seed":
        try:
            from apps.api.routers.trends_v1 import seed_trends_apps
            steam_app_ids = request_body.get("steam_app_ids", [])
            result = await seed_trends_apps({"steam_app_ids": steam_app_ids}, db=db)
            return {"ok": True, "message": "Apps seeded", "details": result}
        except Exception as e:
            logger.error(f"Seed action failed: {e}", exc_info=True)
            return {"ok": False, "message": f"Seed failed: {e}", "details": {"error": str(e)}}
    
    elif action == "collect":
        try:
            from apps.api.routers.trends_v1 import collect_trends_signals
            result = await collect_trends_signals(limit=20, db=db)
            return {"ok": True, "message": "Collection jobs enqueued", "details": result}
        except Exception as e:
            logger.error(f"Collect action failed: {e}", exc_info=True)
            return {"ok": False, "message": f"Collect failed: {e}", "details": {"error": str(e)}}
    
    elif action == "ingest_reviews":
        try:
            from apps.api.routers.trends_v1 import ingest_review_signals
            result = await ingest_review_signals(days_back=0, db=db)
            return {"ok": True, "message": "Reviews ingested", "details": result}
        except Exception as e:
            logger.error(f"Ingest action failed: {e}", exc_info=True)
            return {"ok": False, "message": f"Ingest failed: {e}", "details": {"error": str(e)}}
    
    elif action == "aggregate":
        try:
            from apps.api.routers.trends_v1 import aggregate_trends_daily
            result = await aggregate_trends_daily(days_back=7, db=db)
            return {"ok": True, "message": "Aggregation completed", "details": result}
        except Exception as e:
            logger.error(f"Aggregate action failed: {e}", exc_info=True)
            return {"ok": False, "message": f"Aggregate failed: {e}", "details": {"error": str(e)}}
    
    elif action == "verify":
        try:
            # Run verification checks
            today = date.today()
            checks = {}
            
            # Check queued jobs older than 1 hour
            old_jobs = db.execute(
                text("""
                    SELECT COUNT(*)::int
                    FROM trend_jobs
                    WHERE status = 'queued'
                      AND created_at < NOW() - INTERVAL '1 hour'
                """)
            ).scalar() or 0
            checks["old_queued_jobs"] = old_jobs
            
            # Check signals missing for seeded apps
            missing = db.execute(
                text("""
                    SELECT COUNT(DISTINCT s.steam_app_id)::int
                    FROM trends_seed_apps s
                    LEFT JOIN trends_raw_signals rs ON rs.steam_app_id = s.steam_app_id
                      AND DATE(rs.captured_at) = :today
                      AND rs.value_numeric IS NOT NULL
                    WHERE s.is_active = true
                      AND rs.steam_app_id IS NULL
                """),
                {"today": today}
            ).scalar() or 0
            checks["seeds_missing_signals"] = missing
            
            return {
                "ok": True,
                "message": "Verification completed",
                "details": checks
            }
        except Exception as e:
            return {"ok": False, "message": f"Verify failed: {e}", "details": {"error": str(e)}}
    
    # Engine v4: Events pipeline actions
    elif action == "generate_aliases":
        try:
            from apps.worker.tasks.generate_aliases import generate_aliases_for_all_games
            stats = generate_aliases_for_all_games(db)
            return {"ok": True, "message": "Aliases generated", "details": stats}
        except Exception as e:
            logger.error(f"Generate aliases failed: {e}", exc_info=True)
            return {"ok": False, "message": f"Generate aliases failed: {e}", "details": {"error": str(e)}}
    
    elif action == "collect_events":
        try:
            from apps.worker.tasks.collect_steam_news import collect_steam_news_for_apps
            sources = request_body.get("sources", ["steam_news"])
            limit_apps = request_body.get("limit_apps", 100)
            app_ids = request_body.get("app_ids")  # Optional: specific apps
            stats = collect_steam_news_for_apps(db, app_ids=app_ids, max_news_per_app=10, days_back=7)
            return {"ok": True, "message": "Events collected", "details": stats}
        except Exception as e:
            logger.error(f"Collect events failed: {e}", exc_info=True)
            return {"ok": False, "message": f"Collect events failed: {e}", "details": {"error": str(e)}}
    
    elif action == "match_events":
        try:
            from apps.worker.tasks.entity_matcher import match_events_batch
            # Get unmatched events
            events = db.execute(
                text("""
                    SELECT id, title, body
                    FROM trends_raw_events
                    WHERE matched_steam_app_id IS NULL
                    LIMIT 100
                """)
            ).mappings().all()
            
            stats = match_events_batch([dict(e) for e in events], db)
            return {"ok": True, "message": "Events matched", "details": stats}
        except Exception as e:
            logger.error(f"Match events failed: {e}", exc_info=True)
            return {"ok": False, "message": f"Match events failed: {e}", "details": {"error": str(e)}}
    
    elif action == "events_to_signals":
        try:
            from apps.worker.tasks.events_to_signals import aggregate_events_to_signals
            sources = request_body.get("sources", ["steam_news"])
            total_stats = {"signals_inserted": 0, "games_processed": 0}
            
            for source in sources:
                stats = aggregate_events_to_signals(db, source)
                total_stats["signals_inserted"] += stats.get("signals_inserted", 0)
                total_stats["games_processed"] += stats.get("games_processed", 0)
            
            return {"ok": True, "message": "Events aggregated to signals", "details": total_stats}
        except Exception as e:
            logger.error(f"Events to signals failed: {e}", exc_info=True)
            return {"ok": False, "message": f"Events to signals failed: {e}", "details": {"error": str(e)}}
    
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action}")


@router.get("/events_24h")
async def get_events_24h(
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Get events summary for last 24 hours (Engine v4).
    """
    try:
        events_24h = db.execute(
            text("""
                SELECT 
                    source,
                    COUNT(*)::int as events_total,
                    COUNT(*) FILTER (WHERE matched_steam_app_id IS NOT NULL)::int as matched,
                    COUNT(*) FILTER (WHERE matched_steam_app_id IS NULL)::int as unmatched,
                    MAX(published_at) as last_published_at
                FROM trends_raw_events
                WHERE captured_at >= now() - interval '24 hours'
                GROUP BY source
                ORDER BY events_total DESC
            """)
        ).mappings().all()
        
        events_by_source = {}
        for row in events_24h:
            source = row["source"]
            events_by_source[source] = {
                "events_total": row["events_total"],
                "matched": row["matched"],
                "unmatched": row["unmatched"],
                "last_published_at": row["last_published_at"].isoformat() if row["last_published_at"] else None
            }
        
        # Get top 20 events with game names
        top_events_rows = db.execute(
            text("""
                SELECT 
                    e.source,
                    e.title,
                    e.url,
                    e.published_at,
                    e.matched_steam_app_id,
                    COALESCE(c.name, f.name, 'App ' || e.matched_steam_app_id::text) as game_name
                FROM trends_raw_events e
                LEFT JOIN steam_app_cache c ON c.steam_app_id = e.matched_steam_app_id::bigint
                LEFT JOIN steam_app_facts f ON f.steam_app_id = e.matched_steam_app_id
                WHERE e.captured_at >= now() - interval '24 hours'
                  AND e.matched_steam_app_id IS NOT NULL
                ORDER BY e.published_at DESC
                LIMIT 20
            """)
        ).mappings().all()
        
        top_events = []
        for row in top_events_rows:
            top_events.append({
                "source": row["source"],
                "title": row["title"],
                "url": row["url"],
                "published_at": row["published_at"].isoformat() if row["published_at"] else None,
                "steam_app_id": row["matched_steam_app_id"],
                "game_name": row["game_name"]
            })
        
        return {
            "events_by_source": events_by_source,
            "top_events": top_events
        }
    except Exception as e:
        logger.error(f"Failed to get events_24h: {e}", exc_info=True)
        return {"events_by_source": {}, "top_events": []}
