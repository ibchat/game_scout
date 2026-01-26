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
# Translation helpers (Lifecycle Intelligence v5)
# ============================================================

def translate_stage_to_russian(stage: str) -> str:
    """Переводит stage на русский язык"""
    mapping = {
        "EARLY": "Ранний интерес",
        "CONFIRMING": "Подтверждение",
        "BREAKOUT": "Прорыв",
        "FADING": "Затухание",
        "NOISE": "Шум",
        "MOMENTUM": "Импульс"
    }
    return mapping.get(stage, stage)

def translate_confidence_level_to_russian(level: str) -> str:
    """Переводит confidence_level на русский язык"""
    mapping = {
        "LOW": "Низкая",
        "MEDIUM": "Средняя",
        "HIGH": "Высокая"
    }
    return mapping.get(level, level)

def translate_lifecycle_stage_to_russian(stage: str) -> str:
    """Переводит lifecycle_stage на русский язык"""
    mapping = {
        "PRE_RELEASE": "До релиза",
        "SOFT_LAUNCH": "Мягкий запуск",
        "BREAKOUT": "Прорыв",
        "GROWTH": "Рост",
        "MATURITY": "Зрелость",
        "DECLINE": "Спад",
        "RELAUNCH_CANDIDATE": "Кандидат на перезапуск"
    }
    return mapping.get(stage, stage)

def translate_growth_type_to_russian(growth_type: str) -> str:
    """Переводит growth_type на русский язык"""
    mapping = {
        "ORGANIC": "Органический",
        "HYPE": "Хайп",
        "NEWS_DRIVEN": "Новостной",
        "PLATFORM_DRIVEN": "Платформенный",
        "MIXED": "Смешанный"
    }
    return mapping.get(growth_type, growth_type)

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


@router.get("/emerging")
async def get_emerging_games(
    limit: int = Query(50, ge=1, le=100),
    min_score: float = Query(2.0, ge=0.0, le=100.0, description="Минимальный emerging_score"),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Emerging Games v4 Final - Steam-only, честный радар.
    
    Использует только steam_review_daily и steam_app_cache.
    Полностью отделён от TrendsBrain.
    
    Returns:
        {
            "status": "ok",
            "emerging": [
                {
                    "app_id": int,
                    "name": str,
                    "recent_reviews_30d": int,
                    "positive_ratio": float,
                    "emerging_score": float,
                    "verdict": str
                }
            ]
        }
    """
    try:
        from apps.worker.analysis.emerging_engine_v4 import analyze_emerging
        
        # SQL запрос: только steam_review_daily и steam_app_cache
        query = text("""
        SELECT 
            seed.steam_app_id,
            srd.all_reviews_count,
            srd.recent_reviews_count_30d,
            srd.all_positive_percent,
            srd.day,
            -- Game name: prefer cache.name (most reliable), fallback to facts.name
            COALESCE(
                NULLIF(c.name, ''),
                NULLIF(f.name, ''),
                'App #' || seed.steam_app_id::text
            ) as game_name,
            -- Steam URL: prefer cache.steam_url, fallback to constructed URL
            COALESCE(
                NULLIF(c.steam_url, ''),
                'https://store.steampowered.com/app/' || seed.steam_app_id::text || '/'
            ) as steam_url,
            f.release_date
        FROM trends_seed_apps seed
        LEFT JOIN steam_review_daily srd ON srd.steam_app_id = seed.steam_app_id
            AND srd.day = (
                SELECT MAX(day) FROM steam_review_daily WHERE steam_app_id = seed.steam_app_id
            )
        LEFT JOIN steam_app_facts f ON f.steam_app_id = seed.steam_app_id
        LEFT JOIN steam_app_cache c ON c.steam_app_id = seed.steam_app_id::bigint
        WHERE seed.is_active = true
          AND srd.all_reviews_count IS NOT NULL
        ORDER BY seed.steam_app_id
        """)
        
        try:
            rows = db.execute(query).mappings().all()
        except Exception as e:
            logger.error(f"Failed to fetch emerging games data: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "emerging": []
            }
        
        # Анализируем каждую игру через Emerging Engine v4
        emerging_games = []
        
        for row in rows:
            try:
                # Преобразуем row в dict для analyze_emerging
                app_row = {
                    "steam_app_id": row["steam_app_id"],
                    "all_reviews_count": row["all_reviews_count"],
                    "recent_reviews_count_30d": row["recent_reviews_count_30d"],
                    "all_positive_percent": row["all_positive_percent"],
                    "game_name": row.get("game_name"),
                    "steam_url": row.get("steam_url"),
                    "release_date": row.get("release_date")
                }
                
                result = analyze_emerging(app_row)
                
                # Фильтруем по min_score и passed_filters
                if result["passed_filters"] and result["emerging_score"] >= min_score:
                    emerging_games.append(result)
                    
            except Exception as e:
                logger.error(f"Error analyzing game {row.get('steam_app_id')}: {e}", exc_info=True)
                continue
        
        # Сортируем по emerging_score (по убыванию)
        emerging_games.sort(key=lambda x: x["emerging_score"], reverse=True)
        
        # Возвращаем top N
        result = emerging_games[:limit]
        
        return {
            "status": "ok",
            "emerging": result,
            "count": len(result),
            "total_analyzed": len(rows),
            "filters_applied": {
                "min_score": min_score
            }
        }
    except Exception as e:
        logger.exception("get_emerging_games failed")
        return {
            "status": "error",
            "error": str(e),
            "emerging": []
        }


@router.get("/emerging/diagnostics")
async def get_emerging_diagnostics(
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Emerging Diagnostics v4 Final - честный truth-endpoint.
    Показывает ПОЧЕМУ emerging = 0, если это так.
    Использует реальные фильтры v4.
    """
    from apps.worker.analysis.emerging_engine_v4 import analyze_emerging
    
    try:
        # Получаем все seed apps с данными из steam_review_daily
        query = text("""
            SELECT 
                seed.steam_app_id,
                srd.all_reviews_count,
                srd.recent_reviews_count_30d,
                srd.all_positive_percent,
                f.release_date,
                COALESCE(
                    NULLIF(c.name, ''),
                    NULLIF(f.name, ''),
                    'App #' || seed.steam_app_id::text
                ) as game_name,
                COALESCE(
                    NULLIF(c.steam_url, ''),
                    'https://store.steampowered.com/app/' || seed.steam_app_id::text || '/'
                ) as steam_url
            FROM trends_seed_apps seed
            LEFT JOIN steam_review_daily srd ON srd.steam_app_id = seed.steam_app_id
                AND srd.day = (
                    SELECT MAX(day) FROM steam_review_daily WHERE steam_app_id = seed.steam_app_id
                )
            LEFT JOIN steam_app_facts f ON f.steam_app_id = seed.steam_app_id
            LEFT JOIN steam_app_cache c ON c.steam_app_id = seed.steam_app_id::bigint
            WHERE seed.is_active = true
            ORDER BY seed.steam_app_id
        """)
        
        rows = db.execute(query).mappings().all()
        
        # Счётчики фильтров (реальные фильтры v4)
        total_seed_apps = len(rows)
        passed_growth = 0
        passed_quality = 0
        filtered_evergreen = 0
        below_score_threshold = 0
        emerging_final = 0
        
        for row in rows:
            app_row = {
                "steam_app_id": row["steam_app_id"],
                "all_reviews_count": row["all_reviews_count"],
                "recent_reviews_count_30d": row["recent_reviews_count_30d"],
                "all_positive_percent": row["all_positive_percent"],
                "game_name": row.get("game_name"),
                "steam_url": row.get("steam_url"),
                "release_date": row.get("release_date")
            }
            
            try:
                result = analyze_emerging(app_row)
                filter_results = result.get("filter_results", {})
                
                # Подсчитываем прохождение фильтров
                if filter_results.get("growth"):
                    passed_growth += 1
                if filter_results.get("quality"):
                    passed_quality += 1
                if filter_results.get("evergreen"):
                    filtered_evergreen += 1
                if filter_results.get("score"):
                    emerging_final += 1
                elif filter_results.get("growth") and filter_results.get("quality") and not filter_results.get("evergreen"):
                    below_score_threshold += 1
                    
            except Exception as e:
                logger.warning(f"Failed to analyze game {row.get('steam_app_id')} for diagnostics: {e}")
                continue
        
        return {
            "status": "ok",
            "total_seed_apps": total_seed_apps,
            "passed_growth": passed_growth,
            "passed_quality": passed_quality,
            "filtered_evergreen": filtered_evergreen,
            "below_score_threshold": below_score_threshold,
            "emerging_final": emerging_final
        }
        
    except Exception as e:
        logger.error(f"Emerging diagnostics failed: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "total_seed_apps": 0,
            "passed_growth": 0,
            "passed_quality": 0,
            "filtered_evergreen": 0,
            "below_score_threshold": 0,
            "emerging_final": 0
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
