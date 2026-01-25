"""
Trends v1 Router - Non-breaking addition to Game Scout
Implements job enqueue, job status, and top_spikes endpoints.
"""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, date, timedelta
import logging
import uuid
import json

from apps.api.deps import get_db_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/trends", tags=["Trends Scout"])

# ============================================================
# Health & Admin Endpoints
# ============================================================

@router.get("/health")
async def trends_health(
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Health check for Trends Scout domain.
    """
    try:
        # Quick check: verify trends tables exist
        tables_check = db.execute(
            text("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN ('trends_seed_apps', 'trends_raw_signals', 'trends_game_daily', 'trends_tags_daily')
            """)
        ).scalar()
        
        return {
            "status": "ok",
            "domain": "trends_scout",
            "tables_count": tables_check,
            "healthy": tables_check == 4
        }
    except Exception as e:
        logger.error(f"trends_health_error: {e}", exc_info=True)
        return {
            "status": "error",
            "domain": "trends_scout",
            "error": str(e)
        }


# ============================================================
# Request/Response Models
# ============================================================

class EnqueueRequest(BaseModel):
    steam_app_ids: List[int] = Field(..., description="List of Steam app IDs to enqueue")
    include: Optional[List[str]] = Field(
        ["appdetails", "players", "reviews_daily"],
        description="Job types to enqueue: appdetails, players, reviews_daily"
    )
    force: bool = Field(False, description="If true, enqueue even if recently fetched")


class EnqueueResponse(BaseModel):
    status: str
    enqueued: Dict[str, int]  # job_type -> count


class JobStatusResponse(BaseModel):
    id: str
    created_at: str
    updated_at: str
    job_type: str
    payload: Dict[str, Any]
    status: str
    attempts: int
    last_error: Optional[str]


class TopSpikeItem(BaseModel):
    steam_app_id: int
    name: Optional[str]
    delta_reviews_7d: Optional[int]
    all_positive_percent: Optional[int]
    release_date: Optional[str]


# ============================================================
# Endpoints
# ============================================================

@router.post("/admin/enqueue")
async def enqueue_trends_jobs(
    request: EnqueueRequest = Body(...),
    db: Session = Depends(get_db_session),
) -> EnqueueResponse:
    """
    Enqueue jobs for Trends v1 ingestion.
    Creates jobs for appdetails, players, and reviews_daily for each steam_app_id.
    """
    enqueued = {"appdetails": 0, "players": 0, "reviews_daily": 0}
    
    for app_id in request.steam_app_ids:
        for job_type in request.include:
            if job_type not in ["appdetails", "players", "reviews_daily"]:
                continue
            
            # Check if job already exists (dedupe)
            if not request.force:
                try:
                    existing = db.execute(
                        text("""
                            SELECT id FROM trend_jobs
                            WHERE job_type = :job_type
                              AND payload->>'steam_app_id' = :app_id_str
                              AND status IN ('queued', 'running')
                            LIMIT 1
                        """),
                        {"job_type": job_type, "app_id_str": str(app_id)}
                    ).scalar()
                    
                    if existing:
                        logger.debug(f"Skipping duplicate job: {job_type} for app_id={app_id}")
                        continue
                except Exception as dedupe_error:
                    logger.warning(f"Dedupe check failed for {job_type}/{app_id}: {dedupe_error}")
                    # Continue anyway
            
            # Insert job
            try:
                payload_dict = {
                    "steam_app_id": app_id,
                    "created_at": datetime.now().isoformat()
                }
                # КРИТИЧНО: используем CAST в SQL вместо ::jsonb в параметре
                db.execute(
                    text("""
                        INSERT INTO trend_jobs (job_type, payload, status)
                        VALUES (:job_type, CAST(:payload AS jsonb), 'queued')
                    """),
                    {
                        "job_type": job_type,
                        "payload": json.dumps(payload_dict)  # Сериализуем в JSON строку
                    }
                )
                enqueued[job_type] += 1
                logger.info(f"trends_job_enqueued job_type={job_type} steam_app_id={app_id}")
            except Exception as e:
                logger.warning(f"Failed to enqueue job {job_type} for {app_id}: {e}", exc_info=True)
    
    try:
        db.commit()
    except Exception as commit_error:
        logger.error(f"Failed to commit enqueue: {commit_error}", exc_info=True)
        db.rollback()
    
    return EnqueueResponse(
        status="ok",
        enqueued=enqueued
    )


@router.get("/admin/jobs")
async def get_trends_jobs(
    status: Optional[str] = Query(None, description="Filter by status: queued|running|success|failed"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db_session),
) -> List[JobStatusResponse]:
    """
    Get list of trend jobs, optionally filtered by status.
    """
    query = "SELECT id, created_at, updated_at, job_type, payload, status, attempts, last_error FROM trend_jobs"
    params = {"limit": limit}
    
    if status:
        query += " WHERE status = :status"
        params["status"] = status
    
    query += " ORDER BY created_at DESC LIMIT :limit"
    
    rows = db.execute(text(query), params).mappings().all()
    
    result = []
    for row in rows:
        payload = row["payload"]
        if isinstance(payload, str):
            import json
            try:
                payload = json.loads(payload)
            except:
                payload = {}
        elif payload is None:
            payload = {}
        
        result.append(JobStatusResponse(
            id=str(row["id"]),
            created_at=row["created_at"].isoformat() if row["created_at"] else "",
            updated_at=row["updated_at"].isoformat() if row["updated_at"] else "",
            job_type=row["job_type"],
            payload=payload,
            status=row["status"],
            attempts=row["attempts"],
            last_error=row["last_error"]
        ))
    
    return result


@router.get("/top_spikes")
async def get_top_spikes(
    metric: str = Query("reviews_velocity_7d", description="Metric: reviews_velocity_7d"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db_session),
) -> List[TopSpikeItem]:
    """
    Get top spikes by review velocity (7d delta).
    Computes velocity as delta of all_reviews_count over last 7 days from steam_review_daily.
    """
    if metric != "reviews_velocity_7d":
        raise HTTPException(400, f"Unsupported metric: {metric}")
    
    # Get today and 7 days ago
    today = date.today()
    seven_days_ago = today - timedelta(days=7)
    
    # Compute velocity (delta over 7 days)
    query = text("""
        WITH daily_data AS (
            SELECT 
                steam_app_id,
                day,
                all_reviews_count,
                all_positive_percent
            FROM steam_review_daily
            WHERE day IN (:today, :seven_days_ago)
        ),
        velocity AS (
            SELECT 
                d1.steam_app_id,
                COALESCE(d1.all_reviews_count, 0) - COALESCE(d0.all_reviews_count, 0) as delta_reviews_7d,
                d1.all_positive_percent
            FROM daily_data d1
            LEFT JOIN daily_data d0 ON d1.steam_app_id = d0.steam_app_id AND d0.day = :seven_days_ago
            WHERE d1.day = :today
              AND COALESCE(d1.all_reviews_count, 0) > COALESCE(d0.all_reviews_count, 0)
        )
        SELECT 
            v.steam_app_id,
            f.name,
            v.delta_reviews_7d,
            v.all_positive_percent,
            f.release_date
        FROM velocity v
        LEFT JOIN steam_app_facts f ON f.steam_app_id = v.steam_app_id
        ORDER BY v.delta_reviews_7d DESC
        LIMIT :limit
    """)
    
    rows = db.execute(
        query,
        {"today": today, "seven_days_ago": seven_days_ago, "limit": limit}
    ).mappings().all()
    
    result = []
    for row in rows:
        result.append(TopSpikeItem(
            steam_app_id=row["steam_app_id"],
            name=row["name"],
            delta_reviews_7d=row["delta_reviews_7d"],
            all_positive_percent=row["all_positive_percent"],
            release_date=row["release_date"].isoformat() if row["release_date"] else None
        ))
    
    return result


# ============================================================
# Phase 2: Emerging Games & Tags
# ============================================================

@router.post("/admin/seed_apps")
async def seed_trends_apps(
    request: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Seed apps into trends_seed_apps table.
    Accepts: {"steam_app_ids": [620, 730, ...]}
    """
    steam_app_ids = request.get("steam_app_ids", [])
    if not steam_app_ids:
        raise HTTPException(400, "steam_app_ids required")
    
    upserted = 0
    for app_id in steam_app_ids:
        try:
            db.execute(
                text("""
                    INSERT INTO trends_seed_apps (steam_app_id, is_active, reason)
                    VALUES (:app_id, true, 'manual_seed')
                    ON CONFLICT (steam_app_id) 
                    DO UPDATE SET is_active = true, updated_at = now()
                """),
                {"app_id": app_id}
            )
            upserted += 1
        except Exception as e:
            logger.warning(f"Failed to seed app {app_id}: {e}")
    
    try:
        db.commit()
    except Exception as e:
        logger.error(f"Failed to commit seed: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(500, f"Seed failed: {e}")
    
    return {
        "status": "ok",
        "upserted": upserted
    }


@router.post("/admin/collect")
async def collect_trends_signals(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Trigger data collection for active seed apps.
    Creates jobs for each active seed app.
    """
    # Get active seed apps
    seed_apps = db.execute(
        text("SELECT steam_app_id FROM trends_seed_apps WHERE is_active = true LIMIT :limit"),
        {"limit": limit}
    ).scalars().all()
    
    collected = {"appdetails": 0, "reviews": 0}
    
    for app_id in seed_apps:
        try:
            payload_dict = {"steam_app_id": app_id}
            payload_json = json.dumps(payload_dict)
            
            # Check for existing queued/running appdetails job
            existing_appdetails = db.execute(
                text("""
                    SELECT id FROM trend_jobs
                    WHERE job_type = 'appdetails'
                      AND payload->>'steam_app_id' = :app_id_str
                      AND status IN ('queued', 'running')
                    LIMIT 1
                """),
                {"app_id_str": str(app_id)}
            ).scalar()
            
            if not existing_appdetails:
                db.execute(
                    text("""
                        INSERT INTO trend_jobs (job_type, payload, status)
                        VALUES ('appdetails', CAST(:payload AS jsonb), 'queued')
                    """),
                    {"payload": payload_json}
                )
                collected["appdetails"] += 1
            
            # Check for existing queued/running reviews job
            existing_reviews = db.execute(
                text("""
                    SELECT id FROM trend_jobs
                    WHERE job_type = 'reviews_daily'
                      AND payload->>'steam_app_id' = :app_id_str
                      AND status IN ('queued', 'running')
                    LIMIT 1
                """),
                {"app_id_str": str(app_id)}
            ).scalar()
            
            if not existing_reviews:
                db.execute(
                    text("""
                        INSERT INTO trend_jobs (job_type, payload, status)
                        VALUES ('reviews_daily', CAST(:payload AS jsonb), 'queued')
                    """),
                    {"payload": payload_json}
                )
                collected["reviews"] += 1
        except Exception as e:
            logger.warning(f"Failed to enqueue jobs for app {app_id}: {e}")
    
    try:
        db.commit()
    except Exception as e:
        logger.error(f"Failed to commit collect: {e}", exc_info=True)
        db.rollback()
    
    return {
        "status": "ok",
        "collected": collected
    }


@router.post("/admin/ingest_reviews")
async def ingest_review_signals(
    days_back: int = Query(0, ge=0, le=7),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Ingest numeric signals from steam_review_daily into trends_raw_signals.
    """
    from apps.worker.tasks.trends_collectors import ingest_review_signals_from_daily
    
    today = date.today()
    dates_to_process = [today - timedelta(days=i) for i in range(days_back + 1)]
    
    seed_apps = db.execute(
        text("SELECT steam_app_id FROM trends_seed_apps WHERE is_active = true")
    ).scalars().all()
    
    ingested = 0
    for app_id in seed_apps:
        for process_date in dates_to_process:
            if ingest_review_signals_from_daily(db, app_id, process_date):
                ingested += 1
    
    return {
        "status": "ok",
        "ingested": ingested
    }


@router.post("/admin/aggregate")
async def aggregate_trends_daily(
    days_back: int = Query(7, ge=1, le=30),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Trigger daily aggregation for trends_game_daily and trends_tags_daily.
    """
    from apps.worker.tasks.trends_aggregate import aggregate_daily_trends
    
    try:
        result = aggregate_daily_trends(db, days_back=days_back)
        if result.get("ok", False):
            return {
                "status": "ok",
                "aggregated_rows": result.get("rows", 0)
            }
        else:
            error_msg = result.get("error", "Aggregation failed (check logs)")
            logger.error(f"Aggregate failed: {error_msg}")
            return {
                "status": "error",
                "error": error_msg
            }
    except Exception as e:
        error_msg = f"Aggregate exception: {repr(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "status": "error",
            "error": error_msg
        }


@router.get("/games/emerging")
async def get_emerging_games(
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Get emerging games with investment intelligence (v2).
    
    Returns games with:
    - emerging_score (computed from components)
    - verdict (human-readable interpretation)
    - explanation (list of reasons)
    - flags (logical flags with reasons)
    - score_components (breakdown of score calculation)
    """
    from apps.worker.analysis.trends_brain import TrendsBrain
    
    today = date.today()
    
    # Get latest daily aggregates for all active seed apps with review data
    # + Reddit and YouTube signals
    query = text("""
        SELECT 
            tgd.steam_app_id,
            tgd.day,
            tgd.reviews_total,
            tgd.reviews_delta_1d,
            tgd.reviews_delta_7d,
            tgd.discussions_delta_7d,
            tgd.positive_ratio,
            tgd.tags,
            COALESCE(f.name, c.name, NULL) as name,
            f.release_date,
            -- Reddit signals
            MAX(CASE WHEN rs_reddit.source = 'reddit' AND rs_reddit.signal_type = 'reddit_posts_count_7d' THEN rs_reddit.value_numeric END)::int as reddit_posts_count_7d,
            MAX(CASE WHEN rs_reddit.source = 'reddit' AND rs_reddit.signal_type = 'reddit_comments_count_7d' THEN rs_reddit.value_numeric END)::int as reddit_comments_count_7d,
            MAX(CASE WHEN rs_reddit.source = 'reddit' AND rs_reddit.signal_type = 'reddit_velocity' THEN rs_reddit.value_numeric END)::int as reddit_velocity,
            -- YouTube signals
            MAX(CASE WHEN rs_yt.source = 'youtube' AND rs_yt.signal_type = 'youtube_videos_count_7d' THEN rs_yt.value_numeric END)::int as youtube_videos_count_7d,
            MAX(CASE WHEN rs_yt.source = 'youtube' AND rs_yt.signal_type = 'youtube_views_7d' THEN rs_yt.value_numeric END)::int as youtube_views_7d,
            MAX(CASE WHEN rs_yt.source = 'youtube' AND rs_yt.signal_type = 'youtube_velocity' THEN rs_yt.value_numeric END)::int as youtube_velocity
        FROM trends_game_daily tgd
        JOIN trends_seed_apps seed ON seed.steam_app_id = tgd.steam_app_id
        LEFT JOIN steam_app_facts f ON f.steam_app_id = tgd.steam_app_id
        LEFT JOIN steam_app_cache c ON c.steam_app_id = tgd.steam_app_id
        LEFT JOIN trends_raw_signals rs_reddit ON rs_reddit.steam_app_id = tgd.steam_app_id
            AND rs_reddit.source = 'reddit'
            AND DATE(rs_reddit.captured_at) = tgd.day
        LEFT JOIN trends_raw_signals rs_yt ON rs_yt.steam_app_id = tgd.steam_app_id
            AND rs_yt.source = 'youtube'
            AND DATE(rs_yt.captured_at) = tgd.day
        WHERE seed.is_active = true
          AND tgd.day = (
              SELECT MAX(day) FROM trends_game_daily WHERE steam_app_id = tgd.steam_app_id
          )
        GROUP BY tgd.steam_app_id, tgd.day, tgd.reviews_total, tgd.reviews_delta_1d, tgd.reviews_delta_7d,
                 tgd.discussions_delta_7d, tgd.positive_ratio, tgd.tags, f.name, f.release_date
        ORDER BY tgd.steam_app_id
    """)
    
    rows = db.execute(query).mappings().all()
    
    # Инициализируем "мозг" платформы
    brain = TrendsBrain(db)
    
    # Анализируем каждую игру
    games_analyzed = []
    
    for row in rows:
        steam_app_id = row["steam_app_id"]
        release_date = row["release_date"]
        reviews_total = row["reviews_total"]
        reviews_delta_7d = row["reviews_delta_7d"]
        reviews_delta_1d = row["reviews_delta_1d"]
        positive_ratio = row["positive_ratio"]
        
        # Парсим теги
        tags = row["tags"]
        tags_list = []
        if tags:
            if isinstance(tags, str):
                try:
                    tags_list = json.loads(tags)
                except:
                    tags_list = []
            elif isinstance(tags, list):
                tags_list = tags
        
        # Получаем name из БД если не пришёл из запроса
        # Try multiple sources: steam_app_facts, steam_app_cache
        game_name = row["name"]
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
                    {"app_id": steam_app_id}
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
                        {"app_id": steam_app_id}
                    ).scalar()
                    if name_result:
                        game_name = name_result
            except Exception as name_err:
                logger.debug(f"Failed to get name for app {steam_app_id}: {name_err}")
        
        # Reddit signals
        reddit_posts_count_7d = row.get("reddit_posts_count_7d")
        reddit_comments_count_7d = row.get("reddit_comments_count_7d")
        reddit_velocity = row.get("reddit_velocity")
        
        # YouTube signals
        youtube_videos_count_7d = row.get("youtube_videos_count_7d")
        youtube_views_7d = row.get("youtube_views_7d")
        youtube_velocity = row.get("youtube_velocity")
        
        # Полный анализ игры (мультимодальный)
        try:
            analysis = brain.analyze_game(
                steam_app_id=steam_app_id,
                name=game_name,
                release_date=release_date,
                reviews_total=reviews_total,
                reviews_delta_7d=reviews_delta_7d,
                reviews_delta_1d=reviews_delta_1d,
                positive_ratio=positive_ratio,
                tags=tags_list,
                # Reddit signals
                reddit_posts_count_7d=reddit_posts_count_7d,
                reddit_comments_count_7d=reddit_comments_count_7d,
                reddit_velocity=reddit_velocity,
                # YouTube signals
                youtube_videos_count_7d=youtube_videos_count_7d,
                youtube_views_7d=youtube_views_7d,
                youtube_velocity=youtube_velocity
            )
            
            # Исключаем evergreen giants
            if analysis.flags.is_evergreen_giant:
                continue
            
            # Исключаем игры без сигналов
            if analysis.emerging_score == 0 and not (reviews_delta_7d or reviews_delta_1d or positive_ratio):
                continue
            
            # Формируем ответ
            game_result = {
                "steam_app_id": steam_app_id,
                "name": analysis.name or game_name,  # Используем name из анализа или из БД
                "steam_url": f"https://store.steampowered.com/app/{steam_app_id}/",
                "day": row["day"].isoformat() if row["day"] else None,
                "release_date": release_date.isoformat() if release_date else None,
                "emerging_score": analysis.emerging_score,
                "verdict": analysis.verdict,
                "explanation": analysis.explanation,
                "flags": {
                    "has_real_growth": analysis.flags.has_real_growth,
                    "is_evergreen_giant": analysis.flags.is_evergreen_giant,
                    "is_hype_spike": analysis.flags.is_hype_spike,
                    "is_low_quality_growth": analysis.flags.is_low_quality_growth,
                    "is_new_release": analysis.flags.is_new_release,
                    "is_rediscovered_old_game": analysis.flags.is_rediscovered_old_game,
                    "reasons": analysis.flags.reasons
                },
                "score_components": {
                    "growth_component": round(analysis.score_components.growth_component, 2),
                    "velocity_component": round(analysis.score_components.velocity_component, 2),
                    "sentiment_component": round(analysis.score_components.sentiment_component, 2),
                    "novelty_component": round(analysis.score_components.novelty_component, 2),
                    "penalty_component": round(analysis.score_components.penalty_component, 2),
                    "total": round(analysis.score_components.total(), 2)
                },
                # Оставляем старые поля для обратной совместимости
                "trend_score": analysis.emerging_score,
                "positive_ratio": float(positive_ratio) if positive_ratio else None,
                "reviews_delta_7d": reviews_delta_7d,
                "reviews_delta_1d": reviews_delta_1d,
                "reviews_total": reviews_total,
                "discussions_delta_7d": row["discussions_delta_7d"],
                "why_flagged": ", ".join(analysis.explanation),
                "tags_sample": tags_list[:5] if tags_list else []
            }
            
            games_analyzed.append(game_result)
            
        except Exception as e:
            logger.error(f"Error analyzing game {steam_app_id}: {e}", exc_info=True)
            continue
    
    # Sort by emerging_score descending
    games_analyzed.sort(key=lambda x: x["emerging_score"], reverse=True)
    
    # Return top N
    result = games_analyzed[:limit]
    
    return {
        "status": "ok",
        "reason": "success",
        "count": len(result),
        "games": result
    }


@router.get("/tags/emerging")
async def get_emerging_tags(
    window_days: int = Query(7, ge=1, le=30, description="Window for tag analysis"),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Get emerging tags based on daily aggregates.
    Returns tags that are growing faster than average.
    """
    from apps.worker.tasks.trends_aggregate import compute_emerging_tags
    
    result = compute_emerging_tags(db, window_days=window_days)
    
    return result


@router.get("/debug/{steam_app_id}")
async def get_trends_debug(
    steam_app_id: int,
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Debug endpoint: shows raw signals, daily aggregates, and last snapshots for a game.
    """
    # Raw signals (last 24h)
    raw_signals = db.execute(
        text("""
            SELECT source, signal_type, value_numeric, value_text, captured_at
            FROM trends_raw_signals
            WHERE steam_app_id = :app_id
              AND captured_at > now() - interval '24 hours'
            ORDER BY captured_at DESC
            LIMIT 50
        """),
        {"app_id": steam_app_id}
    ).mappings().all()
    
    # Daily aggregates (last 7 days)
    daily_aggregates = db.execute(
        text("""
            SELECT day, reviews_total, reviews_delta_1d, reviews_delta_7d,
                   discussions_delta_1d, discussions_delta_7d, positive_ratio, tags, why_flagged
            FROM trends_game_daily
            WHERE steam_app_id = :app_id
              AND day >= CURRENT_DATE - interval '7 days'
            ORDER BY day DESC
        """),
        {"app_id": steam_app_id}
    ).mappings().all()
    
    # Last snapshot from steam_app_facts
    last_snapshot = db.execute(
        text("""
            SELECT steam_app_id, name, fetched_at, release_date, price_eur, is_free
            FROM steam_app_facts
            WHERE steam_app_id = :app_id
            ORDER BY fetched_at DESC
            LIMIT 1
        """),
        {"app_id": steam_app_id}
    ).mappings().first()
    
    return {
        "steam_app_id": steam_app_id,
        "raw_signals": [
            {
                "source": r["source"],
                "signal_type": r["signal_type"],
                "value_numeric": float(r["value_numeric"]) if r["value_numeric"] else None,
                "value_text": r["value_text"],
                "captured_at": r["captured_at"].isoformat() if r["captured_at"] else None,
            }
            for r in raw_signals
        ],
        "daily_aggregates": [
            {
                "day": d["day"].isoformat() if d["day"] else None,
                "reviews_total": d["reviews_total"],
                "reviews_delta_1d": d["reviews_delta_1d"],
                "reviews_delta_7d": d["reviews_delta_7d"],
                "discussions_delta_1d": d["discussions_delta_1d"],
                "discussions_delta_7d": d["discussions_delta_7d"],
                "positive_ratio": float(d["positive_ratio"]) if d["positive_ratio"] else None,
                "tags": d["tags"],
                "why_flagged": d["why_flagged"],
            }
            for d in daily_aggregates
        ],
        "last_snapshot": {
            "name": last_snapshot["name"] if last_snapshot else None,
            "fetched_at": last_snapshot["fetched_at"].isoformat() if last_snapshot and last_snapshot["fetched_at"] else None,
            "release_date": last_snapshot["release_date"].isoformat() if last_snapshot and last_snapshot["release_date"] else None,
            "price_eur": float(last_snapshot["price_eur"]) if last_snapshot and last_snapshot["price_eur"] else None,
            "is_free": last_snapshot["is_free"] if last_snapshot else None,
        } if last_snapshot else None,
    }
