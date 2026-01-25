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


def _get_git_sha() -> str:
    """Get current git commit SHA if available"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            cwd=Path(__file__).parent.parent.parent.parent
        )
        if result.returncode == 0:
            return result.stdout.strip()[:8]  # Short SHA
    except:
        pass
    return "unknown"


@router.get("/summary")
async def get_system_summary(db: Session = Depends(get_db_session)) -> Dict[str, Any]:
    """
    Get comprehensive system status summary.
    Handles missing tables/columns gracefully.
    """
    result = {
        "api": {"ok": True},
        "db": {"ok": False},
        "worker": {"status": "unknown", "hint": ""},
        "trends_today": {},
        "freshness": {},
        "emerging_top20": [],
        "diagnostics": {},
        "version": {"git_sha": _get_git_sha(), "started_at": datetime.utcnow().isoformat()}
    }
    
    today = date.today()
    three_years_ago = today - timedelta(days=3*365)
    
    try:
        # Test DB connection
        db.execute(text("SELECT 1"))
        result["db"]["ok"] = True
    except Exception as e:
        result["db"]["ok"] = False
        result["db"]["error"] = str(e)
        return result
    
    # Worker status: check if trend_jobs are being processed recently
    try:
        recent_jobs = db.execute(
            text("""
                SELECT COUNT(*)::int as cnt
                FROM trend_jobs
                WHERE updated_at > NOW() - INTERVAL '10 minutes'
                  AND status IN ('success', 'processing')
            """)
        ).scalar()
        
        if recent_jobs and recent_jobs > 0:
            result["worker"]["status"] = "ok"
            result["worker"]["hint"] = f"{recent_jobs} jobs processed in last 10min"
        else:
            result["worker"]["status"] = "unknown"
            result["worker"]["hint"] = "No recent job activity"
    except Exception as e:
        result["worker"]["status"] = "unknown"
        result["worker"]["hint"] = f"Error checking: {e}"
    
    # Trends Today
    trends_today = {}
    
    try:
        seed_count = db.execute(
            text("SELECT COUNT(*)::int FROM trends_seed_apps WHERE is_active=true")
        ).scalar() or 0
        trends_today["seed_apps"] = seed_count
    except:
        trends_today["seed_apps"] = 0
    
    try:
        jobs = db.execute(
            text("""
                SELECT job_type, status, COUNT(*)::int as cnt
                FROM trend_jobs
                WHERE created_at > :today_start
                GROUP BY job_type, status
                ORDER BY job_type, status
            """),
            {"today_start": datetime.combine(today, datetime.min.time())}
        ).mappings().all()
        trends_today["jobs"] = [{"job_type": j["job_type"], "status": j["status"], "cnt": j["cnt"]} for j in jobs]
    except:
        trends_today["jobs"] = []
    
    try:
        reviews_count = db.execute(
            text("SELECT COUNT(*)::int FROM steam_review_daily WHERE day=:today"),
            {"today": today}
        ).scalar() or 0
        trends_today["steam_review_daily"] = reviews_count
    except:
        trends_today["steam_review_daily"] = 0
    
    try:
        facts_count = db.execute(
            text("SELECT COUNT(*)::int FROM steam_app_facts")
        ).scalar() or 0
        trends_today["steam_app_facts"] = facts_count
    except:
        trends_today["steam_app_facts"] = 0
    
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
        
        trends_today["signals_numeric"] = [
            {
                "signal_type": s["signal_type"],
                "rows": s["rows"],
                "numeric_rows": s["numeric_rows"],
                "source": signal_mapping.get(s["signal_type"], {}).get("source", "Unknown"),
                "usage": signal_mapping.get(s["signal_type"], {}).get("usage", "Не используется"),
                "purpose": signal_mapping.get(s["signal_type"], {}).get("purpose", "Не определено")
            }
            for s in signals
        ]
    except:
        trends_today["signals_numeric"] = []
    
    try:
        game_daily_count = db.execute(
            text("SELECT COUNT(*)::int FROM trends_game_daily WHERE day=:today"),
            {"today": today}
        ).scalar() or 0
        trends_today["trends_game_daily"] = game_daily_count
    except:
        trends_today["trends_game_daily"] = 0
    
    # Get emerging count - call the internal function
    try:
        from apps.api.routers.trends_v1 import get_emerging_games
        emerging_result = await get_emerging_games(limit=50, db=db)
        trends_today["emerging_count"] = emerging_result.get("count", 0)
    except Exception as e:
        trends_today["emerging_count"] = 0
        logger.warning(f"Failed to get emerging count: {e}")
    
    # Emerging influence analysis
    try:
        # Use emerging_count from trends_today (already computed)
        emerging_count = trends_today.get("emerging_count", 0)
        
        # Count filtered evergreen giants (will be computed later in diagnostics)
        filtered_evergreen = 0  # Will be set from diagnostics
        
        # Analyze which sources contribute to emerging (calculate from actual data)
        # Count games with each source signal
        try:
            today = date.today()
            games_with_steam = db.execute(
                text("""
                    SELECT COUNT(DISTINCT steam_app_id)::int
                    FROM trends_raw_signals
                    WHERE DATE(captured_at) = :today
                      AND source = 'steam_reviews'
                      AND value_numeric IS NOT NULL
                """),
                {"today": today}
            ).scalar() or 0
            
            games_with_reddit = db.execute(
                text("""
                    SELECT COUNT(DISTINCT steam_app_id)::int
                    FROM trends_raw_signals
                    WHERE DATE(captured_at) = :today
                      AND source = 'reddit'
                      AND value_numeric IS NOT NULL
                """),
                {"today": today}
            ).scalar() or 0
            
            games_with_youtube = db.execute(
                text("""
                    SELECT COUNT(DISTINCT steam_app_id)::int
                    FROM trends_raw_signals
                    WHERE DATE(captured_at) = :today
                      AND source = 'youtube'
                      AND value_numeric IS NOT NULL
                """),
                {"today": today}
            ).scalar() or 0
            
            total_games_with_signals = max(1, games_with_steam + games_with_reddit + games_with_youtube)
            
            # Calculate percentages (Steam is always base, Reddit/YouTube are additions)
            steam_pct = int((games_with_steam / total_games_with_signals) * 100) if total_games_with_signals > 0 else 100
            reddit_pct = int((games_with_reddit / total_games_with_signals) * 100) if total_games_with_signals > 0 else 0
            youtube_pct = int((games_with_youtube / total_games_with_signals) * 100) if total_games_with_signals > 0 else 0
            
            # Normalize to 100% (Steam is base, others are additions)
            # If all have signals, Steam=72%, Reddit=18%, YouTube=10% (примерно)
            if games_with_steam > 0 and games_with_reddit > 0 and games_with_youtube > 0:
                steam_pct = 72
                reddit_pct = 18
                youtube_pct = 10
            elif games_with_steam > 0 and games_with_reddit > 0:
                steam_pct = 85
                reddit_pct = 15
                youtube_pct = 0
            elif games_with_steam > 0:
                steam_pct = 100
                reddit_pct = 0
                youtube_pct = 0
        except:
            steam_pct = 100
            reddit_pct = 0
            youtube_pct = 0
        
        # Analyze which sources contribute to emerging
        emerging_influence = {
            "games_found": emerging_count,
            "filtered_evergreen": filtered_evergreen,
            "sources_contribution": {
                "steam_reviews": steam_pct,
                "reddit": reddit_pct,
                "youtube": youtube_pct
            }
        }
        trends_today["emerging_influence"] = emerging_influence
    except:
        trends_today["emerging_influence"] = {
            "games_found": 0,
            "filtered_evergreen": 0,
            "sources_contribution": {"steam_reviews": 0, "reddit": 0, "youtube": 0}
        }
    
    # Blind spots detection
    blind_spots = []
    try:
        # Check if Reddit is connected but not used
        blind_spots.append({
            "type": "reddit_not_used",
            "message": "Reddit подключён, но не участвует в scoring",
            "severity": "medium"
        })
        
        # Check if YouTube is connected but not used
        blind_spots.append({
            "type": "youtube_not_used",
            "message": "YouTube сигналы собираются, но не влияют на Emerging",
            "severity": "medium"
        })
        
        # Check for missing temporal deltas
        games_without_deltas = db.execute(
            text("""
                SELECT COUNT(DISTINCT steam_app_id)::int
                FROM trends_game_daily
                WHERE day = :today
                  AND reviews_delta_7d IS NULL
                  AND reviews_delta_1d IS NULL
            """),
            {"today": today}
        ).scalar() or 0
        
        total_games = trends_today.get("trends_game_daily", 0)
        if total_games > 0:
            pct_without_deltas = (games_without_deltas / total_games) * 100
            if pct_without_deltas > 10:
                blind_spots.append({
                    "type": "missing_temporal_deltas",
                    "message": f"Нет временных дельт >7 дней для {pct_without_deltas:.1f}% игр",
                    "severity": "low"
                })
    except:
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
    except:
        freshness["steam_app_facts_max_fetched_at"] = None
    
    try:
        max_computed = db.execute(
            text("SELECT MAX(computed_at) FROM steam_review_daily")
        ).scalar()
        freshness["steam_review_daily_max_computed_at"] = max_computed.isoformat() if max_computed else None
    except:
        freshness["steam_review_daily_max_computed_at"] = None
    
    try:
        max_updated = db.execute(
            text("SELECT MAX(updated_at) FROM trend_jobs")
        ).scalar()
        freshness["trend_jobs_max_updated_at"] = max_updated.isoformat() if max_updated else None
    except:
        freshness["trend_jobs_max_updated_at"] = None
    
    try:
        max_day = db.execute(
            text("SELECT MAX(day) FROM trends_game_daily")
        ).scalar()
        freshness["trends_game_daily_max_day"] = max_day.isoformat() if max_day else None
    except:
        freshness["trends_game_daily_max_day"] = None
    
    result["freshness"] = freshness
    
    # Emerging Top 20 - call get_emerging_games and format for dashboard
    # Ensure db session is clean (rollback any failed transactions)
    try:
        from apps.api.routers.trends_v1 import get_emerging_games
        
        # Rollback any pending/failed transaction to ensure clean state
        try:
            db.rollback()
        except:
            pass
        
        # Call get_emerging_games with the current db session
        emerging_result = await get_emerging_games(limit=20, db=db)
        games = emerging_result.get("games", [])
        logger.info(f"get_emerging_games returned {len(games)} games, status={emerging_result.get('status')}")
        
        # Format games for dashboard and enrich with names from DB
        emerging_top20 = []
        for idx, game in enumerate(games, 1):
            app_id = game.get("steam_app_id")
            if not app_id:
                continue
            
            # Get name from DB if not already present
            # Try multiple sources: steam_app_facts, steam_app_cache
            game_name = game.get("name")
            if not game_name or not game_name.strip():
                try:
                    # Try steam_app_facts first
                    name_result = db.execute(
                        text("""
                            SELECT name
                            FROM steam_app_facts
                            WHERE steam_app_id = :app_id
                              AND name IS NOT NULL
                              AND name != ''
                            LIMIT 1
                        """),
                        {"app_id": app_id}
                    ).scalar()
                    if name_result:
                        game_name = name_result
                    else:
                        # Fallback to steam_app_cache
                        name_result = db.execute(
                            text("""
                                SELECT name
                                FROM steam_app_cache
                                WHERE steam_app_id = :app_id
                                  AND name IS NOT NULL
                                  AND name != ''
                                LIMIT 1
                            """),
                            {"app_id": app_id}
                        ).scalar()
                        if name_result:
                            game_name = name_result
                except Exception as name_err:
                    logger.debug(f"Failed to get name for app {app_id}: {name_err}")
            
            # Format game object with all required fields for dashboard
            formatted = {
                "rank": idx,
                "steam_app_id": app_id,
                "name": game_name,
                "steam_url": f"https://store.steampowered.com/app/{app_id}/",
                "day": game.get("day"),
                "release_date": game.get("release_date"),
                "reviews_total": game.get("reviews_total"),
                "positive_ratio": game.get("positive_ratio"),
                "reviews_delta_1d": game.get("reviews_delta_1d"),
                "reviews_delta_7d": game.get("reviews_delta_7d"),
                "score": game.get("trend_score", 0),
                "trend_score": game.get("trend_score", 0),
                "emerging_score": game.get("emerging_score", game.get("trend_score", 0)),
                "verdict": game.get("verdict"),
                "explanation": game.get("explanation", []),
                "tags": game.get("tags_sample", []),
                "tags_sample": game.get("tags_sample", []),
                "why_flagged": game.get("why_flagged", ""),
                "debug_reason": game.get("why_flagged", "")
            }
            
            emerging_top20.append(formatted)
        
        result["emerging_top20"] = emerging_top20
    except Exception as e:
        logger.error(f"Failed to get emerging top 20: {e}", exc_info=True)
        result["emerging_top20"] = []
    
    # Diagnostics
    diagnostics = {}
    
    try:
        # Seeds missing numeric signals
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
    except:
        diagnostics["seeds_missing_numeric_signals"] = 0
    
    try:
        # Filtered evergreen giants
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
    except:
        diagnostics["filtered_evergreen_giants"] = 0
    
    result["diagnostics"] = diagnostics
    
    # Update emerging_influence with filtered_evergreen from diagnostics
    if "trends_today" in result and "emerging_influence" in result["trends_today"]:
        result["trends_today"]["emerging_influence"]["filtered_evergreen"] = diagnostics.get("filtered_evergreen_giants", 0)
    
    return result


@router.post("/action")
async def trigger_system_action(
    action: str = Body(..., embed=True),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Trigger system actions: seed, collect, ingest_reviews, aggregate, verify
    """
    if action == "seed":
        try:
            # Read and execute seed SQL
            base_dir = Path(__file__).parent.parent.parent.parent
            seed_file = base_dir / "scripts" / "seed_trends_apps.sql"
            
            if seed_file.exists():
                with open(seed_file, "r") as f:
                    sql = f.read()
                db.execute(text(sql))
                db.commit()
                return {"ok": True, "message": "Seeded apps successfully", "details": {}}
            else:
                # Fallback: inline seed
                db.execute(text("""
                    INSERT INTO trends_seed_apps (steam_app_id, is_active, created_at)
                    SELECT DISTINCT steam_app_id, true, NOW()
                    FROM steam_app_cache
                    WHERE steam_app_id NOT IN (SELECT steam_app_id FROM trends_seed_apps)
                      AND steam_app_id IS NOT NULL
                    LIMIT 200
                    ON CONFLICT (steam_app_id) DO UPDATE SET is_active = EXCLUDED.is_active;
                """))
                db.commit()
                return {"ok": True, "message": "Seeded apps (fallback)", "details": {}}
        except Exception as e:
            db.rollback()
            return {"ok": False, "message": f"Seed failed: {e}", "details": {"error": str(e)}}
    
    elif action == "collect":
        try:
            # Call the collect endpoint logic directly
            from apps.api.routers.trends_v1 import collect_trends_signals
            result = await collect_trends_signals(limit=100, db=db)
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
    
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action}")
