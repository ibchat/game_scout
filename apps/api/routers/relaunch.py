from typing import Any, Dict, List, Optional, Set
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session
from datetime import datetime
import logging
import json

logger = logging.getLogger(__name__)

# ============================================================
# SCANNER_BUILD_ID - для проверки что код применяется
# ============================================================
SCANNER_BUILD_ID = "2026-01-16_20-00"  # Увеличивай при каждом изменении (fix: парсинг Steam Search, UI compute_scores)

# ============================================================
# Relaunch Scout Router
# ============================================================
# Итоговые эндпоинты:
#   /api/v1/relaunch/health
#   /api/v1/relaunch/candidates
#   /api/v1/relaunch/admin/track
#   /api/v1/relaunch/admin/bulk_track
# ============================================================

router = APIRouter(prefix="/relaunch", tags=["Relaunch Scout"])

# ============================================================
# Поиск get_db_session (страховка под разные архитектуры)
# ============================================================

get_db_session = None

try:
    from apps.api.deps import get_db_session as _get_db_session  # type: ignore
    get_db_session = _get_db_session
except Exception:
    pass

if get_db_session is None:
    try:
        from apps.api.db import get_db_session as _get_db_session  # type: ignore
        get_db_session = _get_db_session
    except Exception:
        pass

if get_db_session is None:
    try:
        from apps.db.session import get_db_session as _get_db_session  # type: ignore
        get_db_session = _get_db_session
    except Exception:
        pass

if get_db_session is None:
    raise ImportError(
        "Relaunch Scout: не найден get_db_session. Проверь, где он лежит в проекте."
    )

# ============================================================
# Pydantic схемы
# ============================================================

class TrackRequest(BaseModel):
    """Добавление одной игры в трекинг."""
    steam_app_id: int = Field(..., ge=1, description="Steam App ID")
    name: str = Field(..., min_length=1, description="Название для интерфейса")
    tracking_priority: int = Field(50, ge=0, le=100, description="Приоритет 0–100")


class BulkTrackRequest(BaseModel):
    """Массовое добавление в трекинг по списку Steam App ID."""
    steam_app_ids: Optional[List[int]] = Field(default=None, description="Список Steam App ID")
    tracking_priority: int = Field(50, ge=0, le=100)

    # Задел на будущее (пока не используем, чтобы контракт не ломался)
    limit: Optional[int] = None
    min_reviews: Optional[int] = None


# ============================================================
# Вспомогательные функции
# ============================================================

def table_exists(db: Session, table_name: str) -> bool:
    """Проверяем наличие таблицы в public schema (Postgres)."""
    q = text(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema='public' AND table_name=:t
        )
        """
    )
    return bool(db.execute(q, {"t": table_name}).scalar())


# ============================================================
# API
# ============================================================

@router.get("/health")
def relaunch_health(db: Session = Depends(get_db_session)) -> Dict[str, Any]:
    """Healthcheck. Возвращаем количество активных приложений в трекинге."""
    from apps.api.routers.relaunch_config import SCANNER_VERSION
    
    if not table_exists(db, "relaunch_apps"):
        return {
            "status": "healthy",
            "tracked_apps": 0,
            "scanner_build_id": SCANNER_BUILD_ID,  # Ключевое поле для проверки
            "scanner_version": SCANNER_VERSION,
            "note": "Таблица relaunch_apps не найдена"
        }

    cnt = db.execute(
        text("SELECT COUNT(*) FROM relaunch_apps WHERE is_active = true")
    ).scalar() or 0

    # Получаем информацию о последнем скане (опционально)
    last_scan = None
    if table_exists(db, "relaunch_scan_runs"):
        scan_row = db.execute(
            text("""
                SELECT id, started_at, finished_at, seed_found, eligible, added, status
                FROM relaunch_scan_runs
                ORDER BY started_at DESC
                LIMIT 1
            """)
        ).mappings().first()
        
        if scan_row:
            last_scan = {
                "scan_run_id": str(scan_row["id"]),
                "started_at": scan_row["started_at"].isoformat() if scan_row["started_at"] else None,
                "finished_at": scan_row["finished_at"].isoformat() if scan_row["finished_at"] else None,
                "seed_found": scan_row["seed_found"],
                "eligible": scan_row["eligible"],
                "added": scan_row["added"],
                "status": scan_row["status"],
            }

    return {
        "status": "healthy",
        "tracked_apps": int(cnt),
        "scanner_build_id": SCANNER_BUILD_ID,  # Ключевое поле для проверки
        "scanner_version": SCANNER_VERSION,
        "last_scan": last_scan,
    }


@router.get("/candidates")
def relaunch_candidates(
    min_score: float = Query(0.0, ge=0.0, le=100.0),
    limit: int = Query(200, ge=1, le=1000),
    classification: Optional[str] = Query(None, description="candidate/watchlist/rejected"),
    db: Session = Depends(get_db_session),
) -> List[Dict[str, Any]]:
    """Список кандидатов (последний скор по каждой игре)."""
    from apps.api.routers.relaunch_config import EXCLUDE_APP_IDS, EXCLUDE_NAME_CONTAINS
    
    if not table_exists(db, "relaunch_apps"):
        return []

    has_scores = table_exists(db, "relaunch_scores")
    
    # Автоматически запускаем compute_scores, если таблица пустая
    if has_scores:
        scores_count = db.execute(
            text("SELECT COUNT(*) FROM relaunch_scores")
        ).scalar() or 0
        
        # Если таблица пустая, но есть активные игры - запускаем compute_scores автоматически
        if scores_count == 0:
            active_count = db.execute(
                text("SELECT COUNT(*) FROM relaunch_apps WHERE is_active = true")
            ).scalar() or 0
            
            if active_count > 0:
                logger.info(f"relaunch_scores пустая, но есть {active_count} активных игр. Запускаем автоматический compute_scores...")
                try:
                    # Вызываем логику compute_scores напрямую (без рекурсивного вызова endpoint)
                    from datetime import datetime, timezone
                    from apps.worker.relaunch_scorer import compute_relaunch_score
                    
                    apps_to_score = db.execute(
                        text("""
                            SELECT id, steam_app_id, name
                            FROM relaunch_apps
                            WHERE is_active = true
                            ORDER BY tracking_priority DESC, id DESC
                            LIMIT :limit
                        """),
                        {"limit": min(active_count, 200)},
                    ).mappings().all()
                    
                    now = datetime.now(timezone.utc)
                    auto_processed = 0
                    
                    for app in apps_to_score:
                        try:
                            app_id = app["id"]
                            steam_app_id_int = int(app["steam_app_id"])
                            name = app["name"] or ""
                            
                            result = compute_relaunch_score(
                                steam_app_id=steam_app_id_int,
                                name=name,
                                reviews_total=None,
                                recent_reviews=None,
                                rating_pct=None,
                                price_eur=None,
                                tags=[],
                            )
                            
                            db.execute(
                                text("""
                                    INSERT INTO relaunch_scores
                                        (app_id, computed_at, relaunch_score, classification,
                                         failure_reasons, relaunch_angles, reasoning_text)
                                    VALUES
                                        (:app_id, :computed_at, :score, :classification,
                                         :failure_reasons, :relaunch_angles, :reasoning_text)
                                """),
                                {
                                    "app_id": app_id,
                                    "computed_at": now,
                                    "score": float(result.relaunch_score),
                                    "classification": str(result.classification),
                                    "failure_reasons": result.failure_reasons if hasattr(result, 'failure_reasons') else [],
                                    "relaunch_angles": result.relaunch_angles if hasattr(result, 'relaunch_angles') else [],
                                    "reasoning_text": str(result.reasoning_text) if hasattr(result, 'reasoning_text') else "",
                                },
                            )
                            auto_processed += 1
                        except Exception as e:
                            logger.warning(f"Auto-score error for {app.get('steam_app_id')}: {e}")
                    
                    db.commit()
                    logger.info(f"Автоматический compute_scores завершён: processed={auto_processed}")
                except Exception as auto_score_error:
                    logger.warning(f"Ошибка автоматического compute_scores: {auto_score_error}")
                    db.rollback()

    if has_scores:
        sql = """
        WITH latest AS (
            SELECT DISTINCT ON (app_id)
                app_id,
                relaunch_score,
                classification,
                failure_reasons,
                relaunch_angles,
                reasoning_text,
                computed_at
            FROM relaunch_scores
            ORDER BY app_id, computed_at DESC
        )
        SELECT
            ra.id AS app_id,
            ra.steam_app_id,
            ra.name,
            l.relaunch_score,
            l.classification,
            l.failure_reasons,
            l.relaunch_angles,
            l.reasoning_text,
            l.computed_at
        FROM relaunch_apps ra
        LEFT JOIN latest l ON l.app_id = ra.id
        WHERE ra.is_active = true
          AND COALESCE(l.relaunch_score, 0) >= :min_score
        """

        params: Dict[str, Any] = {"min_score": float(min_score), "limit": int(limit)}

        if classification:
            sql += " AND l.classification = :classification"
            params["classification"] = classification

        sql += " ORDER BY COALESCE(l.relaunch_score, 0) DESC LIMIT :limit"

        rows = db.execute(text(sql), params).mappings().all()

        # Получаем failure_analysis для каждого app_id + фильтруем blacklist
        result = []
        for r in rows:
            app_id_uuid = r["app_id"]
            steam_app_id_int = int(r["steam_app_id"])
            steam_app_id = str(r["steam_app_id"])
            name = r["name"] or ""
            
            # КРИТИЧНО: фильтруем blacklist по app_id
            if steam_app_id_int in EXCLUDE_APP_IDS:
                logger.debug(f"Filtering blacklisted app_id from candidates: {steam_app_id_int}")
                continue
            
            # КРИТИЧНО: фильтруем blacklist по имени
            name_lower = name.lower()
            is_blacklisted_name = False
            for exclude_name in EXCLUDE_NAME_CONTAINS:
                if exclude_name.lower() in name_lower:
                    is_blacklisted_name = True
                    logger.debug(f"Filtering blacklisted name from candidates: {name}")
                    break
            
            if is_blacklisted_name:
                continue
            
            # Получаем последний failure_analysis
            failure_analysis = None
            if table_exists(db, "relaunch_failure_analysis"):
                fa_row = db.execute(
                    text("""
                        SELECT failure_categories, suggested_angles, signals, computed_at
                        FROM relaunch_failure_analysis
                        WHERE app_id = :app_id
                        ORDER BY computed_at DESC
                        LIMIT 1
                    """),
                    {"app_id": app_id_uuid},
                ).mappings().first()
                
                if fa_row:
                    failure_analysis = {
                        "failure_categories": fa_row.get("failure_categories") or [],
                        "suggested_angles": fa_row.get("suggested_angles") or [],
                        "key_signals": fa_row.get("signals") or {},
                    }
            
            result.append({
                "app_id": str(app_id_uuid),
                "steam_app_id": steam_app_id,
                "name": name,
                "steam_url": f"https://store.steampowered.com/app/{steam_app_id}",
                "relaunch_score": float(r["relaunch_score"] or 0.0),
                "classification": r["classification"] or "candidate",
                "failure_reasons": r["failure_reasons"] or [],
                "relaunch_angles": r["relaunch_angles"] or [],
                "reasoning": r["reasoning_text"] or "",
                "computed_at": r["computed_at"],
                "failure_categories": failure_analysis["failure_categories"] if failure_analysis else [],
                "suggested_angles": failure_analysis["suggested_angles"] if failure_analysis else [],
                "key_signals": failure_analysis["key_signals"] if failure_analysis else {},
            })
        
        return result

    # Если таблицы скоринга нет — отдаем просто трекаемые игры
    rows = db.execute(
        text(
            """
            SELECT id, steam_app_id, name
            FROM relaunch_apps
            WHERE is_active = true
            ORDER BY tracking_priority DESC, id DESC
            LIMIT :limit
            """
        ),
        {"limit": int(limit)},
    ).mappings().all()

    # Получаем failure_analysis для каждого app_id + фильтруем blacklist
    from apps.api.routers.relaunch_config import EXCLUDE_APP_IDS, EXCLUDE_NAME_CONTAINS
    
    result = []
    for r in rows:
        app_id_uuid = r["id"]
        steam_app_id_int = int(r["steam_app_id"])
        steam_app_id = str(r["steam_app_id"])
        name = r["name"] or ""
        
        # КРИТИЧНО: фильтруем blacklist по app_id
        if steam_app_id_int in EXCLUDE_APP_IDS:
            logger.debug(f"Filtering blacklisted app_id from candidates: {steam_app_id_int}")
            continue
        
        # КРИТИЧНО: фильтруем blacklist по имени
        name_lower = name.lower()
        is_blacklisted_name = False
        for exclude_name in EXCLUDE_NAME_CONTAINS:
            if exclude_name.lower() in name_lower:
                is_blacklisted_name = True
                logger.debug(f"Filtering blacklisted name from candidates: {name}")
                break
        
        if is_blacklisted_name:
            continue
        
        # Получаем последний failure_analysis
        failure_analysis = None
        if table_exists(db, "relaunch_failure_analysis"):
            fa_row = db.execute(
                text("""
                    SELECT failure_categories, suggested_angles, signals, computed_at
                    FROM relaunch_failure_analysis
                    WHERE app_id = :app_id
                    ORDER BY computed_at DESC
                    LIMIT 1
                """),
                {"app_id": app_id_uuid},
            ).mappings().first()
            
            if fa_row:
                failure_analysis = {
                    "failure_categories": fa_row.get("failure_categories") or [],
                    "suggested_angles": fa_row.get("suggested_angles") or [],
                    "key_signals": fa_row.get("signals") or {},
                }
        
        result.append({
            "app_id": str(app_id_uuid),
            "steam_app_id": steam_app_id,
            "name": name,
            "steam_url": f"https://store.steampowered.com/app/{steam_app_id}",
            "relaunch_score": 0.0,
            "classification": "candidate",
            "failure_reasons": [],
            "relaunch_angles": [],
            "reasoning": "Скоринг ещё не запускался (нет relaunch_scores).",
            "computed_at": None,
            "failure_categories": failure_analysis["failure_categories"] if failure_analysis else [],
            "suggested_angles": failure_analysis["suggested_angles"] if failure_analysis else [],
            "key_signals": failure_analysis["key_signals"] if failure_analysis else {},
        })
    
    return result


@router.post("/admin/track")
def relaunch_track(request: TrackRequest, db: Session = Depends(get_db_session)) -> Dict[str, Any]:
    """Добавить одну игру в relaunch_apps (upsert по steam_app_id)."""
    if not table_exists(db, "relaunch_apps"):
        raise HTTPException(status_code=500, detail="Таблица relaunch_apps не найдена")

    try:
        row = db.execute(
            text(
                """
                INSERT INTO relaunch_apps (steam_app_id, name, tracking_priority, is_active)
                VALUES (:steam_app_id, :name, :priority, true)
                ON CONFLICT (steam_app_id)
                DO UPDATE SET
                    name = EXCLUDED.name,
                    tracking_priority = EXCLUDED.tracking_priority,
                    is_active = true
                RETURNING id, steam_app_id, name, tracking_priority, is_active
                """
            ),
            {
                "steam_app_id": int(request.steam_app_id),  # КРИТИЧНО: int (БД BIGINT после миграции)
                "name": request.name,
                "priority": int(request.tracking_priority),
            },
        ).mappings().first()
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"DB error in track: {e}")

    return {"status": "ok", "tracked": dict(row) if row else None}


@router.post("/admin/bulk_track")
def relaunch_bulk_track(request: BulkTrackRequest, db: Session = Depends(get_db_session)) -> Dict[str, Any]:
    """Массовое добавление в трекинг по списку steam_app_ids."""
    if not table_exists(db, "relaunch_apps"):
        raise HTTPException(status_code=500, detail="Таблица relaunch_apps не найдена")

    if not request.steam_app_ids:
        return {
            "status": "ok",
            "added": 0,
            "note": "Передай steam_app_ids: [..]. Пример: {'steam_app_ids':[1091500,570,730],'tracking_priority':50}",
        }

    ids = [int(x) for x in request.steam_app_ids if int(x) > 0]
    if not ids:
        return {"status": "ok", "added": 0, "note": "steam_app_ids пустой после фильтрации"}

    added = 0
    try:
        for sid in ids:
            db.execute(
                text(
                    """
                    INSERT INTO relaunch_apps (steam_app_id, name, tracking_priority, is_active)
                    VALUES (:steam_app_id, :name, :priority, true)
                    ON CONFLICT (steam_app_id)
                    DO UPDATE SET
                        tracking_priority = EXCLUDED.tracking_priority,
                        is_active = true
                    """
                ),
                    {
                        "steam_app_id": int(sid),  # КРИТИЧНО: int (БД BIGINT после миграции)
                        "name": f"Steam #{sid}",
                        "priority": int(request.tracking_priority),
                    },
            )
            added += 1
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"DB error in bulk_track: {e}")

    return {"status": "ok", "added": added, "tracking_priority": int(request.tracking_priority)}


from datetime import datetime, timedelta
from typing import Tuple
import re

import httpx


# ============================================================
# Steam client (минимально, но надежно)
# ============================================================

STEAM_APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"
STEAM_APPREVIEWS_URL = "https://store.steampowered.com/appreviews/{app_id}"


async def _steam_fetch_appdetails(app_id: int) -> Dict[str, Any]:
    """
    Тянем базовые метаданные игры из Steam Store.
    Важно: это публичный endpoint (не Steamworks).
    """
    params = {"appids": app_id, "l": "english"}
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(STEAM_APPDETAILS_URL, params=params)
        r.raise_for_status()
        data = r.json()
        # Формат: { "<app_id>": { success: bool, data: {...} } }
        payload = data.get(str(app_id), {})
        if not payload.get("success"):
            return {"success": False, "data": None}
        return {"success": True, "data": payload.get("data")}


async def _steam_fetch_reviews_summary(app_id: int) -> Dict[str, Any]:
    """
    Тянем summary по обзорам: total/positive/negative и т.п.
    num_per_page=0 -> только summary, быстро.
    """
    url = STEAM_APPREVIEWS_URL.format(app_id=app_id)
    params = {
        "json": 1,
        "filter": "all",
        "language": "all",
        "purchase_type": "all",
        "num_per_page": 0,
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()
        return data.get("query_summary", {}) or {}


def _pick_source_table(db: Session) -> Tuple[str, str]:
    """
    Выбираем, откуда брать рынок для скана.
    Приоритет:
      1) steam_games
      2) games (где source='steam' и source_id = steam_app_id как строка)
    Возвращаем (table_name, id_column)
    """
    if table_exists(db, "steam_games"):
        return ("steam_games", "steam_app_id")
    if table_exists(db, "games"):
        # games использует source_id (VARCHAR), но для Steam это steam_app_id
        return ("games", "source_id")
    return ("", "")


def get_db_seed_app_ids(
    db: Session,
    limit_seed: int = 500,
    min_reviews: Optional[int] = None,
    max_reviews: Optional[int] = None,
) -> List[int]:
    """
    Собирает seed app_ids из БД (steam_games или games).
    Основной источник для market_scan.
    
    Фильтры:
    - Исключает уже существующие в relaunch_apps
    - Опционально фильтрует по reviews (если колонка есть)
    - Возвращает список int app_ids
    """
    seed_app_ids: List[int] = []
    
    table_name, id_column = _pick_source_table(db)
    if not table_name:
        logger.warning("Нет доступных таблиц для DB seed (steam_games или games)")
        return []
    
    try:
        # Проверяем структуру таблицы для фильтров
        has_reviews = False
        has_release_date = False
        reviews_column = None
        
        # КРИТИЧНО: начинаем с чистого состояния транзакции
        try:
            db.rollback()
        except Exception:
            pass
        
        if table_name == "steam_games":
            # Проверяем наличие колонки review_count
            try:
                db.rollback()  # КРИТИЧНО: сбрасываем транзакцию перед проверкой
                db.execute(text(f"SELECT review_count FROM {table_name} LIMIT 1"))
                has_reviews = True
                reviews_column = "review_count"
            except Exception as e:
                logger.debug(f"steam_games review_count check failed: {e}")
                db.rollback()
                pass
        elif table_name == "games":
            # В games может быть review_count или другая структура
            try:
                db.rollback()  # КРИТИЧНО: сбрасываем транзакцию перед проверкой
                db.execute(text(f"SELECT review_count FROM {table_name} WHERE source='steam' LIMIT 1"))
                has_reviews = True
                reviews_column = "review_count"
            except Exception as e:
                logger.debug(f"games review_count check failed: {e}")
                db.rollback()
                pass
        
        # Строим SQL запрос
        # КРИТИЧНО: исключаем уже существующие в relaunch_apps
        # КРИТИЧНО: для games используем source_id как VARCHAR, конвертируем в int
        
        if table_name == "steam_games":
            # steam_games: steam_app_id может быть BIGINT или VARCHAR
            where_clauses = [
                f"{id_column} NOT IN (SELECT steam_app_id FROM relaunch_apps WHERE steam_app_id IS NOT NULL)",
            ]
            
            if has_reviews and min_reviews is not None:
                where_clauses.append(f"COALESCE({reviews_column}, 0) >= :min_reviews")
            if has_reviews and max_reviews is not None:
                where_clauses.append(f"COALESCE({reviews_column}, 0) <= :max_reviews")
            
            # КРИТИЧНО: ORDER BY зависит от наличия reviews-колонки
            if has_reviews and reviews_column:
                order_by_clause = f"ORDER BY COALESCE({reviews_column}, 0) DESC, {id_column} DESC"
            else:
                order_by_clause = f"ORDER BY {id_column}::bigint DESC"
            
            sql = f"""
                SELECT DISTINCT {id_column}::bigint as app_id
                FROM {table_name}
                WHERE {' AND '.join(where_clauses)}
                {order_by_clause}
                LIMIT :limit
            """
            
            params = {"limit": limit_seed}
            if has_reviews and min_reviews is not None:
                params["min_reviews"] = min_reviews
            if has_reviews and max_reviews is not None:
                params["max_reviews"] = max_reviews
            
            rows = db.execute(text(sql), params).mappings().all()
            
        else:  # games table
            # games: source_id = VARCHAR (строка steam_app_id), source='steam'
            # КРИТИЧНО: фильтруем только числовые source_id
            where_clauses = [
                "source = 'steam'",
                f"{id_column} ~ '^[0-9]+$'",  # Только числовые ID
                f"{id_column}::bigint NOT IN (SELECT steam_app_id FROM relaunch_apps WHERE steam_app_id IS NOT NULL)",
            ]
            
            if has_reviews and min_reviews is not None:
                where_clauses.append(f"COALESCE({reviews_column}, 0) >= :min_reviews")
            if has_reviews and max_reviews is not None:
                where_clauses.append(f"COALESCE({reviews_column}, 0) <= :max_reviews")
            
            # КРИТИЧНО: ORDER BY зависит от наличия reviews-колонки
            if has_reviews and reviews_column:
                order_by_clause = f"ORDER BY COALESCE({reviews_column}, 0) DESC, {id_column} DESC"
            else:
                order_by_clause = f"ORDER BY {id_column}::bigint DESC"
            
            sql = f"""
                SELECT DISTINCT {id_column}::bigint as app_id
                FROM {table_name}
                WHERE {' AND '.join(where_clauses)}
                {order_by_clause}
                LIMIT :limit
            """
            
            params = {"limit": limit_seed}
            if has_reviews and min_reviews is not None:
                params["min_reviews"] = min_reviews
            if has_reviews and max_reviews is not None:
                params["max_reviews"] = max_reviews
            
            rows = db.execute(text(sql), params).mappings().all()
        
        for row in rows:
            try:
                app_id = int(row["app_id"])
                if app_id > 0:
                    seed_app_ids.append(app_id)
            except (ValueError, TypeError):
                continue
        
        # Логирование статистики (info)
        try:
            if table_name == "games":
                total_steam = db.execute(text("SELECT COUNT(*) FROM games WHERE source='steam'")).scalar() or 0
                numeric_ids = db.execute(text("SELECT COUNT(*) FROM games WHERE source='steam' AND source_id ~ '^[0-9]+$'")).scalar() or 0
                already_tracked = db.execute(text("SELECT COUNT(*) FROM relaunch_apps WHERE steam_app_id IS NOT NULL")).scalar() or 0
                returned = len(seed_app_ids)
                logger.info(f"DB seed stats: total_steam={total_steam}, numeric_ids={numeric_ids}, already_tracked={already_tracked}, returned={returned}")
            else:
                total_count = db.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar() or 0
                already_tracked = db.execute(text("SELECT COUNT(*) FROM relaunch_apps WHERE steam_app_id IS NOT NULL")).scalar() or 0
                returned = len(seed_app_ids)
                logger.info(f"DB seed stats: total={total_count}, already_tracked={already_tracked}, returned={returned}")
        except Exception as log_error:
            logger.warning(f"DB seed: не удалось получить статистику: {log_error}")
        
        logger.info(f"DB seed: собрано {len(seed_app_ids)} app_ids из таблицы {table_name}")
        
    except Exception as e:
        logger.warning(f"DB seed error: {e}")
        # Не падаем, просто возвращаем пустой список
    
    return seed_app_ids


def _parse_release_date(release_date_str: Optional[str]) -> Optional[datetime]:
    """
    Парсит release_date из Steam API.
    Форматы: "1 Jan, 2024", "Jan 1, 2024", "Coming soon", "TBD"
    """
    if not release_date_str:
        return None
    
    release_date_str = release_date_str.strip()
    
    # Игнорируем будущие релизы и неопределенные (но НЕ 2024, так как это может быть валидная дата)
    if any(x in release_date_str.lower() for x in ["coming soon", "tbd", "q1 2025", "q2 2025", "q3 2025", "q4 2025", "q1 2026", "q2 2026", "q3 2026", "q4 2026"]):
        return None
    # НЕ исключаем просто "2025" или "2026" в строке, так как это может быть частью валидной даты "Jan 1, 2025"
    
    # Пробуем разные форматы
    formats = [
        "%d %b, %Y",  # "1 Jan, 2024"
        "%b %d, %Y",  # "Jan 1, 2024"
        "%d %B, %Y",  # "1 January, 2024"
        "%B %d, %Y",  # "January 1, 2024"
        "%Y-%m-%d",   # "2024-01-01"
        "%d/%m/%Y",   # "01/01/2024"
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(release_date_str, fmt)
        except ValueError:
            continue
    
    return None


def _is_in_rebound_window(release_date: Optional[datetime]) -> bool:
    """
    Проверяет, находится ли игра в Rebound Window (6-24 месяца после релиза).
    """
    if not release_date:
        return False
    
    now = datetime.now()
    age_months = (now.year - release_date.year) * 12 + (now.month - release_date.month)
    
    # Rebound Window: 6-24 месяца
    return 6 <= age_months <= 24


class MarketScanRequest(BaseModel):
    """
    Rebound Window Market Scan: ищет недореализованные игры в окне 6-36 месяца после релиза.
    НЕ ищет новые игры или тренды - только кандидатов для релонча.
    """
    min_months: int = Field(6, ge=1, le=60, description="Минимум месяцев после релиза")
    max_months: int = Field(36, ge=1, le=60, description="Максимум месяцев после релиза (MVP: 36 для гарантии результатов)")
    min_reviews: int = Field(30, ge=30, le=5000, description="Минимум отзывов (MVP: 30 для большего покрытия)")
    max_reviews: int = Field(20000, ge=50, le=100000, description="Максимум отзывов (MVP: 20000 для большего покрытия)")
    mega_hit_reviews: int = Field(50000, ge=10000, le=1000000, description="Порог мега-хита (исключение)")
    exclude_f2p: bool = Field(True, description="Исключать F2P игры")
    limit_seed: int = Field(500, ge=100, le=2000, description="Сколько seed app_id собрать (quick: 150, full: 500)")
    limit_add: int = Field(50, ge=1, le=500, description="Сколько игр добавить в трекинг")
    tracking_priority: int = Field(50, ge=0, le=100, description="Приоритет трекинга")
    page_start: int = Field(1, ge=1, le=50, description="Начальная страница пагинации")
    page_end: int = Field(10, ge=1, le=50, description="Конечная страница пагинации (quick: 5, full: 10)")
    strict_window: bool = Field(False, description="Строгая проверка Rebound Window (MVP: false для большего покрытия)")
    # Новые поля v3
    seed_source: str = Field("db_games", description="Источник seed: cache|db_games|steam_search|mixed")
    cache_refresh: bool = Field(True, description="Обновить cache перед seed выборкой")
    cache_refresh_limit: int = Field(300, ge=1, le=1000, description="Сколько app_ids обновить из games")
    min_positive_ratio: float = Field(0.78, ge=0.0, le=1.0, description="Минимальный positive_ratio для отбора")
    require_release_date: bool = Field(True, description="Требовать release_date для eligibility")
    # Режим работы с seed
    seed_mode: str = Field("add_new", description="Режим seed: add_new (только новые) или refresh_tracked (обновление tracked)")
    refresh_days: int = Field(30, ge=0, le=365, description="Через сколько дней считать tracked игры устаревшими (для refresh_tracked)")


def get_cache_seed_app_ids(
    db: Session,
    min_months: int = 6,
    max_months: int = 36,
    min_reviews: int = 30,
    max_reviews: int = 20000,
    exclude_f2p: bool = True,
    mega_hit_reviews: int = 50000,
    min_positive_ratio: float = 0.78,
    require_release_date: bool = True,
    limit_seed: int = 500,
    seed_mode: str = "add_new",
    refresh_days: int = 30,
) -> List[int]:
    """
    Получает seed app_ids из steam_app_cache (SQL-отбор).
    
    Критерии:
    - release_date в окне min_months..max_months
    - reviews_total в диапазоне
    - positive_ratio >= min_positive_ratio (если есть)
    - is_free = false (если exclude_f2p)
    - type = 'game'
    - seed_mode="add_new": исключает уже добавленные в relaunch_apps
    - seed_mode="refresh_tracked": включает только tracked, которые устарели (по refresh_days)
    """
    from apps.api.routers.relaunch_config import EXCLUDE_APP_IDS
    
    if not table_exists(db, "steam_app_cache"):
        logger.warning("steam_app_cache не найдена, возвращаем пустой список")
        return []
    
    try:
        from datetime import date, timedelta
        
        today = date.today()
        # КРИТИЧНО: правильный расчет дат для Rebound Window (6-36 месяцев назад)
        # min_date = самая старая дата (36 месяцев назад)
        # max_date = самая новая дата (6 месяцев назад)
        min_date = today - timedelta(days=max_months * 30)  # Максимальный возраст (36 месяцев назад)
        max_date = today - timedelta(days=min_months * 30)  # Минимальный возраст (6 месяцев назад)
        
        logger.debug(f"Cache seed: date range: {min_date} to {max_date} (min_months={min_months}, max_months={max_months})")
        
        where_clauses = [
            "type = 'game'",
        ]
        
        # КРИТИЧНО: release_date фильтр только если require_release_date=True
        if require_release_date:
            where_clauses.append("release_date IS NOT NULL")
            where_clauses.append(f"release_date BETWEEN '{min_date}' AND '{max_date}'")
        # Если require_release_date=False, не фильтруем по дате (но все равно исключаем unreleased через фильтры)
        
        where_clauses.extend([
            f"reviews_total BETWEEN {min_reviews} AND {max_reviews}",
            f"reviews_total < {mega_hit_reviews}",
        ])
        
        if exclude_f2p:
            where_clauses.append("is_free = false")
        
        if min_positive_ratio > 0:
            where_clauses.append(f"(positive_ratio IS NULL OR positive_ratio >= {min_positive_ratio})")
        
        # Исключаем blacklist
        if EXCLUDE_APP_IDS:
            exclude_ids_str = ",".join(str(aid) for aid in EXCLUDE_APP_IDS)
            where_clauses.append(f"steam_app_id NOT IN ({exclude_ids_str})")
        
        # КРИТИЧНО: логика seed_mode
        if seed_mode == "add_new":
            # Исключаем уже добавленные
            where_clauses.append(
                "steam_app_id NOT IN (SELECT steam_app_id FROM relaunch_apps WHERE steam_app_id IS NOT NULL)"
            )
        elif seed_mode == "refresh_tracked":
            # Включаем только tracked, которые устарели
            # Проверяем: last_snapshot_at, last_reviews_at, last_score_at или отсутствие в relaunch_failure_analysis
            from datetime import datetime, timedelta
            refresh_threshold = datetime.now() - timedelta(days=refresh_days)
            refresh_threshold_str = refresh_threshold.strftime("%Y-%m-%d %H:%M:%S")
            
            # Условие: steam_app_id ДОЛЖЕН быть в relaunch_apps И (устарел по любому критерию)
            where_clauses.append(
                f"""steam_app_id IN (
                    SELECT ra.steam_app_id
                    FROM relaunch_apps ra
                    WHERE ra.steam_app_id IS NOT NULL
                      AND (
                          ra.last_snapshot_at IS NULL 
                          OR ra.last_snapshot_at < '{refresh_threshold_str}'
                          OR ra.last_reviews_at IS NULL 
                          OR ra.last_reviews_at < '{refresh_threshold_str}'
                          OR ra.last_score_at IS NULL 
                          OR ra.last_score_at < '{refresh_threshold_str}'
                          OR NOT EXISTS (
                              SELECT 1 FROM relaunch_failure_analysis rfa 
                              WHERE rfa.app_id = ra.id
                          )
                      )
                )"""
            )
        
        # Сортировка: приоритет "маркетинг провалился"
        # positive_ratio DESC (высокое качество), reviews_total ASC (недореализация), release_date DESC (ближе к 6-18 мес)
        # КРИТИЧНО: для ORDER BY с DISTINCT нужно включить поля в SELECT
        order_by_clause = "ORDER BY positive_ratio DESC NULLS LAST, reviews_total ASC, release_date DESC NULLS LAST"
        
        sql = f"""
            SELECT steam_app_id as app_id
            FROM steam_app_cache
            WHERE {' AND '.join(where_clauses)}
            {order_by_clause}
            LIMIT :limit
        """
        
        rows = db.execute(text(sql), {"limit": limit_seed}).mappings().all()
        
        app_ids = []
        for row in rows:
            try:
                app_id = int(row["app_id"])
                if app_id > 0:
                    app_ids.append(app_id)
            except (ValueError, TypeError):
                continue
        
        # Логирование статистики (info) - цепочка фильтров
        try:
            total_cache = db.execute(text("SELECT COUNT(*) FROM steam_app_cache")).scalar() or 0
            games_only = db.execute(text("SELECT COUNT(*) FROM steam_app_cache WHERE type='game'")).scalar() or 0
            with_release_date = db.execute(text("SELECT COUNT(*) FROM steam_app_cache WHERE type='game' AND release_date IS NOT NULL")).scalar() or 0
            in_window = db.execute(
                text(f"SELECT COUNT(*) FROM steam_app_cache WHERE type='game' AND release_date IS NOT NULL AND release_date BETWEEN '{min_date}' AND '{max_date}'")
            ).scalar() or 0 if require_release_date else games_only
            not_f2p = db.execute(
                text(f"SELECT COUNT(*) FROM steam_app_cache WHERE type='game' AND is_free=false")
            ).scalar() or 0 if exclude_f2p else games_only
            reviews_in_range = db.execute(
                text(f"SELECT COUNT(*) FROM steam_app_cache WHERE type='game' AND reviews_total BETWEEN {min_reviews} AND {max_reviews}")
            ).scalar() or 0
            positive_ratio_ok = db.execute(
                text(f"SELECT COUNT(*) FROM steam_app_cache WHERE type='game' AND (positive_ratio IS NULL OR positive_ratio >= {min_positive_ratio})")
            ).scalar() or 0 if min_positive_ratio > 0 else games_only
            
            if seed_mode == "add_new":
                already_tracked = db.execute(text("SELECT COUNT(*) FROM relaunch_apps WHERE steam_app_id IS NOT NULL")).scalar() or 0
            else:  # refresh_tracked
                from datetime import datetime, timedelta
                refresh_threshold = datetime.now() - timedelta(days=refresh_days)
                refresh_threshold_str = refresh_threshold.strftime("%Y-%m-%d %H:%M:%S")
                already_tracked = db.execute(
                    text(f"""
                        SELECT COUNT(*) FROM relaunch_apps ra
                        WHERE ra.steam_app_id IS NOT NULL
                          AND (
                              ra.last_snapshot_at IS NULL 
                              OR ra.last_snapshot_at < '{refresh_threshold_str}'
                              OR ra.last_reviews_at IS NULL 
                              OR ra.last_reviews_at < '{refresh_threshold_str}'
                              OR ra.last_score_at IS NULL 
                              OR ra.last_score_at < '{refresh_threshold_str}'
                          )
                    """)
                ).scalar() or 0
            
            returned = len(app_ids)
            logger.info(
                f"Cache seed stats: total={total_cache}, games={games_only}, with_release_date={with_release_date}, "
                f"in_window={in_window}, not_f2p={not_f2p}, reviews_in_range={reviews_in_range}, "
                f"positive_ratio_ok={positive_ratio_ok}, already_tracked={already_tracked}, returned={returned}, "
                f"seed_mode={seed_mode}, refresh_days={refresh_days}"
            )
        except Exception as log_error:
            logger.warning(f"Cache seed: не удалось получить статистику: {log_error}")
        
        logger.info(f"Cache seed: собрано {len(app_ids)} app_ids из steam_app_cache (seed_mode={seed_mode})")
        
        return app_ids
        
    except Exception as e:
        logger.warning(f"Cache seed error: {e}")
        return []


def _finalize_scan_response(
    response: Dict[str, Any],
    request: MarketScanRequest,
    cache_seed_found: int = 0,
    refreshed: int = 0,
) -> Dict[str, Any]:
    """
    Нормализует ответ market_scan: гарантирует, что все поля не None.
    """
    # Устанавливаем дефолты для обязательных полей
    response.setdefault("seed_mode", request.seed_mode if hasattr(request, 'seed_mode') else "add_new")
    response.setdefault("refresh_days", request.refresh_days if hasattr(request, 'refresh_days') else 30)
    response.setdefault("cache_seed_found", cache_seed_found)
    response.setdefault("refreshed", refreshed)
    
    # Гарантируем, что числовые поля не None
    numeric_fields = [
        "seed_total", "seed_unique", "db_seed_found", "steam_seed_found",
        "cache_seed_found", "details_fetched", "eligible", "upserted", "refreshed"
    ]
    for field in numeric_fields:
        if field in response and response[field] is None:
            response[field] = 0
    
    # Гарантируем, что строковые поля не None
    string_fields = ["seed_mode", "status", "scan_batch_id", "scanner_version", "note"]
    for field in string_fields:
        if field in response and response[field] is None:
            response[field] = "" if field != "status" else "ok"
    
    return response


def _run_market_scan(request: MarketScanRequest, scan_batch_id: str, db: Session) -> Dict[str, Any]:
    """
    Внутренняя функция выполнения скана (синхронная, для BackgroundTasks или sync).
    Возвращает результат скана со статистикой.
    """
    import time
    from datetime import datetime
    from apps.api.routers.steam_research_engine import steam_research_engine
    from apps.api.routers.relaunch_filters import filter_game_details
    from apps.api.routers.relaunch_config import SCANNER_VERSION
    
    if not table_exists(db, "relaunch_apps"):
        raise HTTPException(500, "Таблица relaunch_apps не найдена")

    # scan_batch_id уже передан, started_at уже известен из внешнего контекста
    started_at = datetime.now()
    start_time_ms = time.time() * 1000
    
    # Статистика
    seed_total = 0  # Всего собрано (до дедупликации)
    seed_unique = 0  # Уникальных после дедупликации
    db_seed_found = 0  # Из БД
    steam_seed_found = 0  # Из Steam Search (optional)
    details_fetched = 0
    eligible = 0
    upserted = 0
    refreshed = 0  # КРИТИЧНО: для refresh_tracked режима
    excluded = {
        "blacklist_app_id": 0,
        "blacklist_name": 0,
        "mega_hit": 0,
        "f2p": 0,
        "too_new": 0,
        "too_old": 0,
        "reviews_too_low": 0,
        "reviews_too_high": 0,
        "not_a_game": 0,
        "no_release_date": 0,
        "steam_fetch_failed": 0,
        "steam_search_empty": 0,  # Steam Search вернул 0
        "db_seed_empty": 0,  # БД seed пустой
        "bad_type": 0,
        "other": 0,
    }
    
    # Timings
    timings_ms = {
        "seed_ms": 0,
        "details_ms": 0,
        "filter_ms": 0,
        "db_ms": 0,
        "total_ms": 0,
    }
    
    sample_added = []
    excluded_examples: Dict[str, List[Dict[str, Any]]] = {
        "blacklist_app_id": [],
        "blacklist_name": [],
        "mega_hit": [],
        "f2p": [],
        "too_new": [],
        "too_old": [],
        "reviews_too_low": [],
        "reviews_too_high": [],
        "not_a_game": [],
        "no_release_date": [],
        "steam_fetch_failed": [],
        "other": [],
    }

    try:
        # 1) Seed Collection: собираем app_ids в зависимости от seed_source
        seed_start_ms = time.time() * 1000
        logger.info(f"Market Scan: Starting seed collection (seed_source={request.seed_source})")
        
        seed_app_ids_set: Set[int] = set()
        cache_seed_found = 0  # КРИТИЧНО: инициализируем всегда, даже если seed_source не cache
        
        # Cache refresh (если включен и seed_source включает cache)
        if request.cache_refresh and ("cache" in request.seed_source or request.seed_source == "mixed"):
            try:
                from apps.api.routers.steam_cache import seed_cache_from_games_table, refresh_cache_for_app_ids
                
                logger.info(f"Cache refresh: обновляем cache из games (limit={request.cache_refresh_limit})")
                refresh_app_ids = seed_cache_from_games_table(db, limit=request.cache_refresh_limit)
                
                if refresh_app_ids:
                    refresh_stats = refresh_cache_for_app_ids(
                        refresh_app_ids,
                        db,
                        steam_research_engine,
                        rate_limit_delay=steam_research_engine.rate_limit_delay,
                    )
                    logger.info(f"Cache refresh: processed={refresh_stats['processed']}, ok={refresh_stats['ok']}, failed={refresh_stats['failed']}")
            except Exception as e:
                logger.warning(f"Cache refresh error (non-critical): {e}")
        
        # Source selection по seed_source
        if request.seed_source == "cache" or request.seed_source == "mixed":
            # Cache seed (основной для v3)
            cache_seed = get_cache_seed_app_ids(
                db=db,
                min_months=request.min_months,
                max_months=request.max_months,
                min_reviews=request.min_reviews,
                max_reviews=request.max_reviews,
                exclude_f2p=request.exclude_f2p,
                mega_hit_reviews=request.mega_hit_reviews,
                min_positive_ratio=request.min_positive_ratio,
                require_release_date=request.require_release_date,
                limit_seed=request.limit_seed,
                seed_mode=request.seed_mode,
                refresh_days=request.refresh_days,
            )
            cache_seed_found = len(cache_seed)
            seed_app_ids_set.update(cache_seed)
            logger.info(f"Cache seed: найдено {cache_seed_found} app_ids")
        
        if request.seed_source == "db_games" or request.seed_source == "mixed":
            # DB seed (fallback или mixed)
            db_seed = get_db_seed_app_ids(
                db=db,
                limit_seed=request.limit_seed,
                min_reviews=request.min_reviews if request.min_reviews > 0 else None,
                max_reviews=request.max_reviews if request.max_reviews < 1000000 else None,
            )
            db_seed_found = len(db_seed)
            seed_app_ids_set.update(db_seed)
            if db_seed_found == 0:
                excluded["db_seed_empty"] = 1
        
        if request.seed_source == "steam_search" or request.seed_source == "mixed":
            # Steam Search (optional)
            steam_seed_set: Set[int] = set()
            try:
                steam_page_end = min(request.page_end, 2) if request.page_end <= 5 else request.page_end
                steam_seed = steam_research_engine.collect_seed_app_ids(
                    page_start=request.page_start,
                    page_end=steam_page_end,
                    limit_seed=min(request.limit_seed // 2, 200),
                )
                steam_seed_found = len(steam_seed)
                steam_seed_set.update(steam_seed)
                if steam_seed_found == 0:
                    excluded["steam_search_empty"] = 1
            except Exception as e:
                excluded["steam_search_empty"] = 1
                logger.warning(f"Steam Search error (non-critical): {e}")
            seed_app_ids_set.update(steam_seed_set)
        else:
            steam_seed_found = 0
        
        # Объединяем и дедуплицируем
        seed_app_ids = list(seed_app_ids_set)
        seed_unique = len(seed_app_ids)
        seed_total = seed_unique
        
        # Если итоговый seed пустой - возвращаем понятный ответ (не 500)
        if seed_unique == 0:
            timings_ms["seed_ms"] = int((time.time() * 1000) - seed_start_ms)
            timings_ms["total_ms"] = int((time.time() * 1000) - start_time_ms)
            return _finalize_scan_response({
                "status": "ok",  # Не error, а ok с понятным note
                "scan_batch_id": scan_batch_id,
                "scanner_version": SCANNER_VERSION,
                "seed_total": 0,
                "seed_unique": 0,
                "cache_seed_found": cache_seed_found,  # КРИТИЧНО: всегда включаем cache_seed_found
                "db_seed_found": db_seed_found,
                "steam_seed_found": steam_seed_found,
                "details_fetched": 0,
                "eligible": 0,
                "upserted": 0,
                "refreshed": 0,
                "excluded": excluded,
                "timings_ms": timings_ms,
                "note": f"Seed empty: cache_seed={cache_seed_found}, db_seed={db_seed_found}, steam_seed={steam_seed_found}. Проверьте наличие данных или ослабьте фильтры." + (
                    " Candidates exist but all are already tracked; use seed_mode=refresh_tracked" 
                    if request.seed_source == "cache" and request.seed_mode == "add_new" and cache_seed_found == 0 
                    else ""
                ),
            }, request, cache_seed_found, refreshed=0)
        timings_ms["seed_ms"] = int((time.time() * 1000) - seed_start_ms)
        
        if seed_unique == 0:
            timings_ms["total_ms"] = int((time.time() * 1000) - start_time_ms)
            return _finalize_scan_response({
                "status": "warning",
                "scan_batch_id": scan_batch_id,
                "scanner_version": SCANNER_VERSION,
                "seed_total": 0,
                "seed_unique": 0,
                "cache_seed_found": cache_seed_found,  # КРИТИЧНО: всегда включаем cache_seed_found
                "db_seed_found": db_seed_found,
                "steam_seed_found": steam_seed_found,
                "details_fetched": 0,
                "eligible": 0,
                "upserted": 0,
                "refreshed": 0,
                "excluded": excluded,
                "timings_ms": timings_ms,
                "note": f"Seed empty: cache_seed={cache_seed_found}, db_seed={db_seed_found}, steam_seed={steam_seed_found}. Проверьте наличие данных или ослабьте фильтры." + (
                    " Candidates exist but all are already tracked; use seed_mode=refresh_tracked" 
                    if request.seed_source == "cache" and request.seed_mode == "add_new" and cache_seed_found == 0 
                    else ""
                ),
            }, request, cache_seed_found, refreshed=0)
        
        # 2) Deep Fetch: получаем детали для каждого app_id
        details_start_ms = time.time() * 1000
        logger.info(f"Steam Research: Fetching details for {seed_unique} apps")
        eligible_apps = []
        
        from apps.api.routers.relaunch_config import EXCLUDE_APP_IDS
        
        for app_id in list(seed_app_ids)[:request.limit_seed]:
            time.sleep(steam_research_engine.rate_limit_delay)  # Rate limiting (250ms между запросами по умолчанию)
            
            # КРИТИЧНО: проверяем blacklist ДО запроса к Steam (экономия времени)
            if app_id in EXCLUDE_APP_IDS:
                excluded["blacklist_app_id"] += 1
                logger.debug(f"Skipping blacklisted app_id: {app_id}")
                continue
            
            # Получаем details из Steam (с retry)
            app_details = None
            for retry in range(3):  # 3 попытки для надёжности
                try:
                    app_details = steam_research_engine.fetch_app_details(app_id)
                    if app_details:
                        break
                except Exception as e:
                    logger.warning(f"Failed to fetch details for {app_id} (attempt {retry+1}/3): {e}")
                    if retry < 2:
                        time.sleep(0.5 * (retry + 1))  # Увеличивающаяся задержка
            
            if not app_details:
                excluded["steam_fetch_failed"] += 1
                logger.debug(f"Failed to get details for app_id: {app_id}")
                continue

            details_fetched += 1
            
            # КРИТИЧНО: name уже проверен в fetch_app_details (возвращает None если не получен)
            name = app_details.get("name", "")
            if not name or name.startswith("App ") or name == f"App {app_id}":
                excluded["steam_fetch_failed"] += 1
                logger.warning(f"Invalid name for app_id {app_id}: '{name}'")
                continue
            
            # 3) Filtering: применяем все фильтры (ТОЛЬКО после получения details)
            filter_start_ms = time.time() * 1000
            is_eligible, exclude_reason, breakdown = filter_game_details(
                app_details,
                min_months=request.min_months,
                max_months=request.max_months,
                min_reviews=request.min_reviews,
                max_reviews=request.max_reviews,
                exclude_f2p=request.exclude_f2p,
                mega_hit_reviews=request.mega_hit_reviews,
                strict_window=request.strict_window,
            )
            timings_ms["filter_ms"] += int((time.time() * 1000) - filter_start_ms)
            
            # Логируем первые несколько исключений для диагностики
            if not is_eligible and details_fetched <= 10:
                logger.info(f"Excluded app_id {app_id} ({name[:50]}): reason={exclude_reason}, reviews={app_details.get('reviews_total', 0)}, release_date={app_details.get('release_date', 'N/A')}, type={app_details.get('type', 'N/A')}, is_free={app_details.get('is_free', False)}")
            
            if is_eligible:
                eligible_apps.append(app_details)
                eligible += 1
                
                if len(eligible_apps) >= request.limit_add:
                    break
            else:
                # Увеличиваем счётчик исключений с правильной категоризацией и собираем примеры
                exclude_reason_key = exclude_reason or "other"
                
                if exclude_reason == "blacklist_app_id":
                    excluded["blacklist_app_id"] += 1
                    if len(excluded_examples["blacklist_app_id"]) < 5:
                        excluded_examples["blacklist_app_id"].append({
                            "app_id": app_id,
                            "name": name[:100],
                            "reviews_total": app_details.get("reviews_total", 0),
                        })
                elif exclude_reason == "blacklist_name":
                    excluded["blacklist_name"] += 1
                    if len(excluded_examples["blacklist_name"]) < 5:
                        excluded_examples["blacklist_name"].append({
                            "app_id": app_id,
                            "name": name[:100],
                            "reviews_total": app_details.get("reviews_total", 0),
                        })
                elif exclude_reason == "mega_hit":
                    excluded["mega_hit"] += 1
                    if len(excluded_examples["mega_hit"]) < 5:
                        excluded_examples["mega_hit"].append({
                            "app_id": app_id,
                            "name": name[:100],
                            "reviews_total": app_details.get("reviews_total", 0),
                        })
                elif exclude_reason == "f2p":
                    excluded["f2p"] += 1
                    if len(excluded_examples["f2p"]) < 5:
                        excluded_examples["f2p"].append({
                            "app_id": app_id,
                            "name": name[:100],
                            "is_free": app_details.get("is_free", False),
                        })
                elif exclude_reason == "too_new":
                    excluded["too_new"] += 1
                    if len(excluded_examples["too_new"]) < 5:
                        excluded_examples["too_new"].append({
                            "app_id": app_id,
                            "name": name[:100],
                            "release_date": app_details.get("release_date", "N/A"),
                        })
                elif exclude_reason == "too_old":
                    excluded["too_old"] += 1
                    if len(excluded_examples["too_old"]) < 5:
                        excluded_examples["too_old"].append({
                            "app_id": app_id,
                            "name": name[:100],
                            "release_date": app_details.get("release_date", "N/A"),
                        })
                elif exclude_reason == "reviews_too_low":
                    excluded["reviews_too_low"] += 1
                    if len(excluded_examples["reviews_too_low"]) < 5:
                        excluded_examples["reviews_too_low"].append({
                            "app_id": app_id,
                            "name": name[:100],
                            "reviews_total": app_details.get("reviews_total", 0),
                        })
                elif exclude_reason == "reviews_too_high":
                    excluded["reviews_too_high"] += 1
                    if len(excluded_examples["reviews_too_high"]) < 5:
                        excluded_examples["reviews_too_high"].append({
                            "app_id": app_id,
                            "name": name[:100],
                            "reviews_total": app_details.get("reviews_total", 0),
                        })
                elif exclude_reason == "not_a_game":
                    excluded["not_a_game"] += 1
                    excluded["bad_type"] += 1  # Дублируем для ясности
                    if len(excluded_examples["not_a_game"]) < 5:
                        excluded_examples["not_a_game"].append({
                            "app_id": app_id,
                            "name": name[:100],
                            "type": app_details.get("type", "N/A"),
                        })
                elif exclude_reason == "no_release_date":
                    excluded["no_release_date"] += 1
                    if len(excluded_examples["no_release_date"]) < 5:
                        excluded_examples["no_release_date"].append({
                            "app_id": app_id,
                            "name": name[:100],
                            "release_date": app_details.get("release_date", "N/A"),
                        })
                elif exclude_reason == "steam_fetch_failed":
                    excluded["steam_fetch_failed"] += 1
                    if len(excluded_examples["steam_fetch_failed"]) < 5:
                        excluded_examples["steam_fetch_failed"].append({
                            "app_id": app_id,
                            "name": f"App {app_id}" if not name else name[:100],
                        })
                else:
                    excluded["other"] += 1
                    if len(excluded_examples["other"]) < 5:
                        excluded_examples["other"].append({
                            "app_id": app_id,
                            "name": name[:100] if name else f"App {app_id}",
                            "reason": exclude_reason or "unknown",
                        })
        
        timings_ms["details_ms"] = int((time.time() * 1000) - details_start_ms)
        
        # 4) Upsert в relaunch_apps (КРИТИЧНО: всегда обновляем name если получили из Steam)
        db_start_ms = time.time() * 1000
        logger.info(f"Steam Research: Adding {len(eligible_apps)} eligible games")
        
        # КРИТИЧНО: проверяем состояние транзакции перед upsert
        try:
            # Пробный запрос для проверки транзакции
            db.execute(text("SELECT 1")).scalar()
        except Exception as trans_check_error:
            logger.warning(f"Transaction check failed, rolling back: {trans_check_error}")
            db.rollback()
        
        for app in eligible_apps:
            try:
                app_id = app["app_id"]
                name = app["name"]
                steam_url = app["steam_url"]
                
                # КРИТИЧНО: после миграции БД steam_app_id = BIGINT, используем int
                steam_app_id_int = int(app_id)
                
                # КРИТИЧНО: проверяем существующую запись
                existing = db.execute(
                    text("SELECT id, name FROM relaunch_apps WHERE steam_app_id = :sid"),
                    {"sid": steam_app_id_int},
                ).mappings().first()
                
                existing_name = existing["name"] if existing else None
                existing_id = existing["id"] if existing else None
                
                # КРИТИЧНО: также деактивируем мегахиты если они уже есть в БД
                # (двойная защита на случай если они попали раньше)
                from apps.api.routers.relaunch_config import EXCLUDE_APP_IDS
                if app_id in EXCLUDE_APP_IDS:
                    db.execute(
                        text("UPDATE relaunch_apps SET is_active = false WHERE steam_app_id = :sid"),
                        {"sid": steam_app_id_int},
                    )
                    logger.warning(f"Deactivated blacklisted app_id: {app_id}")
                    continue
                
                # КРИТИЧНО: логика в зависимости от seed_mode
                if request.seed_mode == "refresh_tracked":
                    # Режим refresh: обновляем только существующие записи
                    if existing_id:
                        # Обновляем name (если пустое или "Steam #id"), last_snapshot_at
                        update_name = name
                        if existing_name and not (existing_name.startswith("Steam #") or existing_name == f"App {app_id}"):
                            # Если имя уже нормальное - не перезаписываем
                            update_name = existing_name
                        
                        db.execute(
                            text("""
                                UPDATE relaunch_apps
                                SET name = :name,
                                    last_snapshot_at = NOW()
                                WHERE steam_app_id = :steam_app_id
                            """),
                            {
                                "steam_app_id": steam_app_id_int,
                                "name": update_name,
                            },
                        )
                        refreshed += 1
                        
                        if len(sample_added) < 5:
                            sample_added.append({
                                "steam_app_id": app_id,
                                "name": update_name,
                                "steam_url": steam_url,
                                "action": "refreshed",
                            })
                    else:
                        # В refresh режиме не добавляем новые
                        logger.debug(f"Skipping new app_id {app_id} in refresh_tracked mode")
                else:
                    # Режим add_new: добавляем новые или обновляем существующие
                    # КРИТИЧНО: если существующее имя выглядит как "Steam #id" и у нас есть нормальное имя - заменяем
                    if existing_name and (existing_name.startswith("Steam #") or existing_name == f"App {app_id}"):
                        if name and name != existing_name:
                            logger.info(f"Enriching name for {app_id}: '{existing_name}' -> '{name}'")
                    
                    db.execute(
                        text("""
                            INSERT INTO relaunch_apps (steam_app_id, name, tracking_priority, is_active)
                            VALUES (:steam_app_id, :name, :priority, true)
                            ON CONFLICT (steam_app_id)
                            DO UPDATE SET
                                name = EXCLUDED.name,  -- ВСЕГДА обновляем name если получили из Steam
                                tracking_priority = EXCLUDED.tracking_priority,
                                is_active = true
                        """),
                        {
                            "steam_app_id": steam_app_id_int,  # КРИТИЧНО: int (БД BIGINT после миграции)
                            "name": name,  # Гарантированно нормальное имя (проверено выше)
                            "priority": int(request.tracking_priority),
                        },
                    )
                    upserted += 1
                    
                    if len(sample_added) < 5:
                        sample_added.append({
                            "steam_app_id": app_id,
                            "name": name,
                            "steam_url": steam_url,
                            "action": "added",
                        })
            except Exception as upsert_error:
                logger.error(f"Upsert error for app_id {app_id}: {upsert_error}")
                try:
                    db.rollback()
                except Exception:
                    pass
                # Продолжаем с остальными играми
                continue
        
        db.commit()
        timings_ms["db_ms"] = int((time.time() * 1000) - db_start_ms)
        
        finished_at = datetime.now()
        timings_ms["total_ms"] = int((time.time() * 1000) - start_time_ms)
        
        # Определяем статус
        if seed_unique == 0 or details_fetched == 0:
            status = "warning"
            if request.seed_source == "cache" and request.seed_mode == "add_new":
                note = f"Warning: seed_unique={seed_unique}, details_fetched={details_fetched}. Candidates exist but all are already tracked; use seed_mode=refresh_tracked"
            else:
                note = f"Warning: seed_unique={seed_unique}, details_fetched={details_fetched}. Check Steam API availability."
        elif eligible == 0:
            status = "warning"
            note = f"Warning: No eligible games found. Excluded breakdown: {sum(excluded.values())} total exclusions."
        elif eligible < 5:
            status = "warning"
            note = f"Found only {eligible} eligible games (expected 10+). Consider relaxing filters."
        else:
            status = "ok"
            if request.seed_mode == "refresh_tracked":
                note = f"Market scan completed. seed_unique={seed_unique}, details_fetched={details_fetched}, eligible={eligible}, refreshed={refreshed}."
            else:
                note = f"Market scan completed. seed_unique={seed_unique}, details_fetched={details_fetched}, eligible={eligible}, upserted={upserted}."
        
        # Сохраняем scan run (если таблица существует)
        if table_exists(db, "relaunch_scan_runs"):
            try:
                db.execute(
                    text("""
                        INSERT INTO relaunch_scan_runs
                            (id, started_at, finished_at, params, seed_found, details_fetched,
                             eligible, added, excluded, status, scanner_version, note)
                        VALUES
                            (:id, :started_at, :finished_at, :params, :seed_found, :details_fetched,
                             :eligible, :added, :excluded, :status, :scanner_version, :note)
                    """),
                    {
                        "id": scan_batch_id,
                        "started_at": started_at,
                        "finished_at": finished_at,
                        "params": {
                            "min_months": request.min_months,
                            "max_months": request.max_months,
                            "min_reviews": request.min_reviews,
                            "max_reviews": request.max_reviews,
                            "exclude_f2p": request.exclude_f2p,
                            "strict_window": request.strict_window,
                            "page_start": request.page_start,
                            "page_end": request.page_end,
                            "limit_seed": request.limit_seed,
                            "limit_add": request.limit_add,
                        },
                        "seed_found": seed_unique,
                        "details_fetched": details_fetched,
                        "eligible": eligible,
                        "added": upserted,
                        "excluded": excluded,
                        "status": status,
                        "scanner_version": SCANNER_VERSION,
                        "note": note,
                    },
                )
                db.commit()
            except Exception as e:
                logger.warning(f"Failed to save scan run: {e}")
        
        # Формируем top_excluded_reasons для UI (топ-3 причины)
        excluded_total = sum(excluded.values())
        top_excluded_reasons = []
        if excluded_total > 0:
            sorted_reasons = sorted(
                [(k, v) for k, v in excluded.items() if v > 0],
                key=lambda x: x[1],
                reverse=True
            )[:3]
            top_excluded_reasons = [{"reason": k, "count": v} for k, v in sorted_reasons]
        
        # Автоматически запускаем compute_scores после сканирования (если upserted > 0 или refreshed > 0, независимо от status)
        if upserted > 0 or (request.seed_mode == "refresh_tracked" and refreshed > 0):
            score_count = upserted if request.seed_mode == "add_new" else refreshed
            logger.info(f"Автоматически запускаем compute_scores для {score_count} игр (mode={request.seed_mode})...")
            try:
                from apps.worker.relaunch_scorer import compute_relaunch_score
                from datetime import datetime, timezone, timedelta
                
                # Получаем игры для scoring (добавленные или обновленные)
                if request.seed_mode == "refresh_tracked":
                    # В refresh режиме берем обновленные игры
                    apps_to_score = db.execute(
                        text("""
                            SELECT id, steam_app_id, name
                            FROM relaunch_apps
                            WHERE is_active = true
                              AND last_snapshot_at >= :threshold
                            ORDER BY last_snapshot_at DESC
                            LIMIT :limit
                        """),
                        {
                            "limit": min(refreshed, 100),
                            "threshold": datetime.now() - timedelta(minutes=5),  # Обновленные за последние 5 минут
                        },
                    ).mappings().all()
                else:
                    # В add_new режиме берем недавно добавленные
                    apps_to_score = db.execute(
                        text("""
                            SELECT id, steam_app_id, name
                            FROM relaunch_apps
                            WHERE is_active = true
                            ORDER BY id DESC
                            LIMIT :limit
                        """),
                        {"limit": min(upserted, 100)},  # Ограничиваем до 100 для быстрого ответа
                    ).mappings().all()
                
                now_score = datetime.now(timezone.utc)
                auto_scored = 0
                
                for app in apps_to_score:
                    try:
                        app_id = app["id"]
                        steam_app_id_int = int(app["steam_app_id"])
                        name = app["name"] or ""
                        
                        result = compute_relaunch_score(
                            steam_app_id=steam_app_id_int,
                            name=name,
                            reviews_total=None,
                            recent_reviews=None,
                            rating_pct=None,
                            price_eur=None,
                            tags=[],
                        )
                        
                        db.execute(
                            text("""
                                INSERT INTO relaunch_scores
                                    (app_id, computed_at, relaunch_score, classification,
                                     failure_reasons, relaunch_angles, reasoning_text)
                                VALUES
                                    (:app_id, :computed_at, :score, :classification,
                                     :failure_reasons, :relaunch_angles, :reasoning_text)
                            """),
                            {
                                "app_id": app_id,
                                "computed_at": now_score,
                                "score": float(result.relaunch_score),
                                "classification": str(result.classification),
                                "failure_reasons": result.failure_reasons if hasattr(result, 'failure_reasons') else [],
                                "relaunch_angles": result.relaunch_angles if hasattr(result, 'relaunch_angles') else [],
                                "reasoning_text": str(result.reasoning_text) if hasattr(result, 'reasoning_text') else "",
                            },
                        )
                        auto_scored += 1
                    except Exception as e:
                        logger.warning(f"Auto-score error for {app.get('steam_app_id')}: {e}")
                
                db.commit()
                logger.info(f"Автоматический compute_scores завершён: scored={auto_scored} из {len(apps_to_score)} (mode={request.seed_mode})")
            except Exception as auto_score_error:
                logger.warning(f"Ошибка автоматического compute_scores после market_scan: {auto_score_error}")
                try:
                    db.rollback()
                except Exception:
                    pass
        
        return _finalize_scan_response({
            "status": status,
            "scan_batch_id": scan_batch_id,
            "scanner_version": SCANNER_VERSION,
            "seed_total": seed_total,
            "seed_unique": seed_unique,
            "cache_seed_found": cache_seed_found,  # v3: cache seed
            "db_seed_found": db_seed_found,
            "steam_seed_found": steam_seed_found,
            "details_fetched": details_fetched,
            "eligible": eligible,
            "upserted": upserted,
            "refreshed": refreshed,  # v3: для refresh_tracked режима
            "seed_mode": request.seed_mode,  # v3: режим работы
            "refresh_days": request.refresh_days,  # v3: параметр refresh
            "excluded": excluded,
            "excluded_examples": {k: v for k, v in excluded_examples.items() if len(v) > 0},  # Только непустые
            "top_excluded_reasons": top_excluded_reasons,
            "timings_ms": timings_ms,
            "sample_added": sample_added[:5],  # Только первые 5
            "note": note,
        }, request, cache_seed_found, refreshed)
        
    except Exception as e:
        import traceback
        logger.error(f"Market scan error: {e}\n{traceback.format_exc()}")
        
        # КРИТИЧНО: rollback транзакции при ошибке
        try:
            db.rollback()
        except Exception as rollback_error:
            logger.warning(f"Rollback failed: {rollback_error}")
        
        # Сохраняем ошибку в scan run (НОВЫЙ контекст, после rollback)
        if table_exists(db, "relaunch_scan_runs"):
            try:
                # Используем новый контекст для записи ошибки
                db.execute(
                    text("""
                        INSERT INTO relaunch_scan_runs
                            (id, started_at, finished_at, status, error_text, scanner_version)
                        VALUES
                            (:id, :started_at, :finished_at, 'error', :error_text, :scanner_version)
                    """),
                    {
                        "id": scan_batch_id,
                        "started_at": started_at,
                        "finished_at": datetime.now(),
                        "error_text": str(e),
                        "scanner_version": SCANNER_VERSION,
                    },
                )
                db.commit()
            except Exception as save_error:
                logger.warning(f"Failed to save scan run error: {save_error}")
        
        timings_ms["total_ms"] = int((time.time() * 1000) - start_time_ms)
        
        # КРИТИЧНО: используем безопасные значения для переменных, которые могли не быть инициализированы
        safe_seed_total = seed_total if 'seed_total' in locals() else 0
        safe_seed_unique = seed_unique if 'seed_unique' in locals() else 0
        safe_cache_seed_found = cache_seed_found if 'cache_seed_found' in locals() else 0
        safe_db_seed_found = db_seed_found if 'db_seed_found' in locals() else 0
        safe_steam_seed_found = steam_seed_found if 'steam_seed_found' in locals() else 0
        safe_details_fetched = details_fetched if 'details_fetched' in locals() else 0
        safe_eligible = eligible if 'eligible' in locals() else 0
        safe_upserted = upserted if 'upserted' in locals() else 0
        safe_refreshed = refreshed if 'refreshed' in locals() else 0
        safe_excluded = excluded if 'excluded' in locals() else {}
        safe_timings_ms = timings_ms if 'timings_ms' in locals() else {}
        
        return _finalize_scan_response({
            "status": "error",
            "scan_batch_id": scan_batch_id,
            "scanner_version": SCANNER_VERSION,
            "seed_total": safe_seed_total,
            "seed_unique": safe_seed_unique,
            "cache_seed_found": safe_cache_seed_found,
            "db_seed_found": safe_db_seed_found,
            "steam_seed_found": safe_steam_seed_found,
            "details_fetched": safe_details_fetched,
            "eligible": safe_eligible,
            "upserted": safe_upserted,
            "refreshed": safe_refreshed,
            "excluded": safe_excluded,
            "timings_ms": safe_timings_ms,
            "note": f"Error during scan: {str(e)}",
            "debug": traceback.format_exc()[:500] if __debug__ else None,
        }, request, safe_cache_seed_found, safe_refreshed)


@router.post("/admin/market_scan")
async def relaunch_market_scan(
    request: MarketScanRequest,
    mode: str = Query("quick", description="Режим скана: quick (sync, до 25 сек) или full (async, в фоне)"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Rebound Window Market Scan v2.1: с поддержкой режимов quick/full.
    
    Режимы:
    - quick: синхронный скан (до 25 сек), небольшие лимиты (limit_seed=150, page_end=5)
    - full: асинхронный скан (в фоне), полные лимиты (limit_seed=500, page_end=10)
    
    Для full режима:
    - Возвращает {status: "accepted", scan_batch_id: "..."} немедленно
    - Реальный скан выполняется в фоне
    - Используйте GET /admin/scan_status?scan_batch_id=... для проверки прогресса
    
    НЕ ищет: Cyberpunk, CS2, Dota, PUBG, Apex и другие мега-хиты.
    """
    import uuid
    
    # Адаптируем параметры для quick режима
    if mode == "quick":
        # Быстрый режим: меньшие лимиты для гарантии ответа до 25 сек
        if request.limit_seed > 150:
            request.limit_seed = 150
        if request.page_end > 5:
            request.page_end = 5
        if request.limit_add > 30:
            request.limit_add = 30
    
    scan_batch_id = str(uuid.uuid4())
    
    # Для quick режима - синхронный вызов
    if mode == "quick":
        result = _run_market_scan(request, scan_batch_id, db)
        return result
    
    # Для full режима - запускаем в фоне
    # Сначала создаём запись в БД со статусом "running"
    if table_exists(db, "relaunch_scan_runs"):
        from apps.api.routers.relaunch_config import SCANNER_VERSION
        try:
            db.execute(
                text("""
                    INSERT INTO relaunch_scan_runs
                        (id, started_at, status, params, scanner_version, note)
                    VALUES
                        (:id, :started_at, 'running', :params, :scanner_version, :note)
                """),
                {
                    "id": scan_batch_id,
                    "started_at": datetime.now(),
                    "params": {
                        "min_months": request.min_months,
                        "max_months": request.max_months,
                        "min_reviews": request.min_reviews,
                        "max_reviews": request.max_reviews,
                        "exclude_f2p": request.exclude_f2p,
                        "strict_window": request.strict_window,
                        "page_start": request.page_start,
                        "page_end": request.page_end,
                        "limit_seed": request.limit_seed,
                        "limit_add": request.limit_add,
                    },
                    "scanner_version": SCANNER_VERSION,
                    "note": "Full scan started (async)",
                },
            )
            db.commit()
        except Exception as e:
            logger.warning(f"Failed to create scan run record: {e}")
    
    # Запускаем скан в фоне
    def run_scan_background():
        # Получаем новую сессию БД для background task
        from apps.api.deps import get_db_session as _get_db
        bg_db = next(_get_db())
        try:
            result = _run_market_scan(request, scan_batch_id, bg_db)
            # Обновляем запись в БД со статусом
            if table_exists(bg_db, "relaunch_scan_runs"):
                status = result.get("status", "error")
                bg_db.execute(
                    text("""
                        UPDATE relaunch_scan_runs
                        SET status = :status,
                            finished_at = :finished_at,
                            seed_found = :seed_found,
                            details_fetched = :details_fetched,
                            eligible = :eligible,
                            added = :added,
                            excluded = :excluded,
                            note = :note
                        WHERE id = :id
                    """),
                    {
                        "id": scan_batch_id,
                        "status": status,
                        "finished_at": datetime.now(),
                        "seed_found": result.get("seed_unique", 0),
                        "details_fetched": result.get("details_fetched", 0),
                        "eligible": result.get("eligible", 0),
                        "added": result.get("upserted", 0),
                        "excluded": result.get("excluded", {}),
                        "note": result.get("note", ""),
                    },
                )
                bg_db.commit()
        except Exception as e:
            logger.error(f"Background scan error: {e}")
            # Обновляем статус на error
            try:
                bg_db.execute(
                    text("""
                        UPDATE relaunch_scan_runs
                        SET status = 'error',
                            finished_at = :finished_at,
                            error_text = :error_text
                        WHERE id = :id
                    """),
                    {
                        "id": scan_batch_id,
                        "finished_at": datetime.now(),
                        "error_text": str(e),
                    },
                )
                bg_db.commit()
            except Exception:
                pass
        finally:
            bg_db.close()
    
    background_tasks.add_task(run_scan_background)
    
    return {
        "status": "accepted",
        "scan_batch_id": scan_batch_id,
        "mode": "full",
        "note": "Full scan started in background. Use GET /admin/scan_status?scan_batch_id=... to check progress.",
    }


@router.get("/admin/scan_status")
async def get_scan_status(
    scan_batch_id: str = Query(..., description="ID скана (scan_batch_id)"),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Получить статус скана (для async режима).
    """
    if not table_exists(db, "relaunch_scan_runs"):
        raise HTTPException(404, "Таблица relaunch_scan_runs не найдена")
    
    scan_row = db.execute(
        text("""
            SELECT id, started_at, finished_at, status, seed_found, details_fetched,
                   eligible, added, excluded, error_text, note
            FROM relaunch_scan_runs
            WHERE id = :id
        """),
        {"id": scan_batch_id},
    ).mappings().first()
    
    if not scan_row:
        raise HTTPException(404, f"Scan run {scan_batch_id} not found")
    
    return {
        "scan_batch_id": str(scan_row["id"]),
        "status": scan_row["status"],  # running/finished/error
        "started_at": scan_row["started_at"].isoformat() if scan_row["started_at"] else None,
        "finished_at": scan_row["finished_at"].isoformat() if scan_row["finished_at"] else None,
        "seed_found": scan_row["seed_found"] or 0,
        "details_fetched": scan_row["details_fetched"] or 0,
        "eligible": scan_row["eligible"] or 0,
        "added": scan_row["added"] or 0,
        "excluded": scan_row["excluded"] or {},
        "error_text": scan_row["error_text"],
        "note": scan_row["note"],
    }


@router.get("/admin/scan_last")
async def get_last_scan(
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Получить последний скан (для быстрого доступа).
    """
    if not table_exists(db, "relaunch_scan_runs"):
        raise HTTPException(404, "Таблица relaunch_scan_runs не найдена")
    
    scan_row = db.execute(
        text("""
            SELECT id, started_at, finished_at, status, seed_found, details_fetched,
                   eligible, added, excluded, error_text, note
            FROM relaunch_scan_runs
            ORDER BY started_at DESC
            LIMIT 1
        """),
    ).mappings().first()
    
    if not scan_row:
        return {
            "status": "not_found",
            "note": "No scans found",
        }
    
    return {
        "scan_batch_id": str(scan_row["id"]),
        "status": scan_row["status"],
        "started_at": scan_row["started_at"].isoformat() if scan_row["started_at"] else None,
        "finished_at": scan_row["finished_at"].isoformat() if scan_row["finished_at"] else None,
        "seed_found": scan_row["seed_found"] or 0,
        "details_fetched": scan_row["details_fetched"] or 0,
        "eligible": scan_row["eligible"] or 0,
        "added": scan_row["added"] or 0,
        "excluded": scan_row["excluded"] or {},
        "error_text": scan_row["error_text"],
        "note": scan_row["note"],
    }


# ============================================================
# Diagnosis Endpoint
# ============================================================

class DiagnoseRequest(BaseModel):
    """Запрос на диагностику игр."""
    limit: int = Field(200, ge=1, le=1000, description="Сколько игр диагностировать")
    app_ids: Optional[List[int]] = Field(None, description="Конкретные steam_app_id (если указаны, limit игнорируется)")


@router.post("/admin/diagnose")
async def relaunch_diagnose(
    request: DiagnoseRequest,
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Диагностика провала для найденных кандидатов.
    Rule-based анализ (без LLM).
    
    Для каждой игры:
    1) Получает данные из Steam API
    2) Применяет правила диагностики
    3) Сохраняет результат в relaunch_failure_analysis
    """
    from datetime import datetime
    import json
    from apps.api.routers.relaunch_diagnosis import diagnose_game
    from apps.api.routers.steam_research_engine import steam_research_engine
    import time
    
    if not table_exists(db, "relaunch_apps"):
        raise HTTPException(500, "Таблица relaunch_apps не найдена")
    
    # КРИТИЧНО: не падаем если таблицы нет, возвращаем warning (не 500)
    if not table_exists(db, "relaunch_failure_analysis"):
        return {
            "status": "warning",
            "diagnosed": 0,
            "detail": "relaunch_failure_analysis missing, run migration: docker compose exec -T postgres psql -U postgres -d game_scout -f migrations/create_relaunch_failure_analysis.sql",
            "note": "Таблица relaunch_failure_analysis не найдена. Выполните миграцию.",
        }
    
    # Получаем список игр для диагностики
    if request.app_ids:
        # Конкретные app_ids
        rows = db.execute(
            text("""
                SELECT id, steam_app_id, name
                FROM relaunch_apps
                WHERE steam_app_id = ANY(:app_ids) AND is_active = true
            """),
            {"app_ids": [int(aid) for aid in request.app_ids]},  # КРИТИЧНО: массив int (БД BIGINT после миграции)
        ).mappings().all()
    else:
        # Без диагностики (берем активные)
        rows = db.execute(
            text("""
                SELECT id, steam_app_id, name
                FROM relaunch_apps
                WHERE is_active = true
                ORDER BY tracking_priority DESC, id DESC
                LIMIT :limit
            """),
            {"limit": int(request.limit)},
        ).mappings().all()
    
    if not rows:
        return {
            "status": "ok",
            "diagnosed": 0,
            "note": "Нет активных игр для диагностики.",
        }
    
    diagnosed = 0
    errors = []
    
    try:
        for row in rows:
            app_id_uuid = row["id"]
            steam_app_id = int(row["steam_app_id"])  # После миграции БД steam_app_id = BIGINT
            name = row["name"]
            
            try:
                # Получаем детали из Steam
                time.sleep(steam_research_engine.rate_limit_delay)  # Rate limiting
                app_details = steam_research_engine.fetch_app_details(steam_app_id)
            
                if not app_details:
                    errors.append({"steam_app_id": steam_app_id, "error": "Не удалось получить данные из Steam"})
                    continue
                
                # Подготавливаем данные для диагностики
                reviews_total = app_details.get("reviews_total", 0)
                positive_ratio = app_details.get("positive_ratio", 0.7)  # Получаем из fetch_app_details
                
                # Вычисляем цену
                price = 0.0
                price_overview = app_details.get("price_overview", {})
                if price_overview:
                    price = price_overview.get("final", 0) / 100.0
                elif app_details.get("is_free"):
                    price = 0.0
                
                steam_data = {
                    "reviews_total": reviews_total,
                    "positive_ratio": positive_ratio,
                    "recent_reviews_30d": 0,  # TODO: получать из истории (для будущего)
                    "delta_recent_90d": None,
                    "early_negative_ratio": None,
                    "price": price,
                    "age_months": 0,
                    "review_velocity": None,
                }
                
                # Вычисляем age_months из release_date
                release_date_str = app_details.get("release_date")
                if release_date_str:
                    release_date = _parse_release_date(release_date_str)
                    if release_date:
                        now = datetime.now()
                        age_months = (now.year - release_date.year) * 12 + (now.month - release_date.month)
                        steam_data["age_months"] = age_months
                
                # Запускаем диагностику
                diagnosis = diagnose_game(steam_data)
                
                # Сохраняем результат (КРИТИЧНО: json.dumps для dict/list -> jsonb)
                db.execute(
                    text("""
                        INSERT INTO relaunch_failure_analysis
                            (app_id, failure_categories, confidence_map, suggested_angles, signals, computed_at)
                        VALUES
                            (:app_id, :failure_categories::jsonb, :confidence_map::jsonb, :suggested_angles::jsonb, :signals::jsonb, :computed_at)
                        ON CONFLICT (app_id, computed_at)
                        DO UPDATE SET
                            failure_categories = EXCLUDED.failure_categories,
                            confidence_map = EXCLUDED.confidence_map,
                            suggested_angles = EXCLUDED.suggested_angles,
                            signals = EXCLUDED.signals
                    """),
                    {
                        "app_id": app_id_uuid,
                        "failure_categories": json.dumps(diagnosis["failure_categories"]),
                        "confidence_map": json.dumps(diagnosis["confidence_map"]),
                        "suggested_angles": json.dumps(diagnosis["suggested_angles"]),
                        "signals": json.dumps(diagnosis["key_signals"]),
                        "computed_at": datetime.now(),
                    },
                )
                
                diagnosed += 1
                
            except Exception as e:
                logger.error(f"Diagnosis error for {steam_app_id}: {e}")
                errors.append({"steam_app_id": steam_app_id, "error": str(e)})
                # КРИТИЧНО: rollback при ошибке одной игры, чтобы не ломать весь батч
                try:
                    db.rollback()
                except Exception as rollback_error:
                    logger.warning(f"Rollback failed after diagnosis error: {rollback_error}")
                # Продолжаем с следующей игрой
                continue
        
        db.commit()
    except Exception as e:
        import traceback
        logger.error(f"Diagnosis transaction error: {e}\n{traceback.format_exc()}")
        try:
            db.rollback()
        except Exception as rollback_error:
            logger.warning(f"Rollback failed: {rollback_error}")
        raise HTTPException(500, detail=f"Diagnosis failed: {str(e)}")
    
    return {
        "status": "ok",
        "diagnosed": diagnosed,
        "errors": errors[:10] if errors else [],
        "note": f"Диагностика завершена. Обработано {diagnosed} игр.",
    }


# ============================================================
# Cleanup Endpoint (деактивация мегахитов)
# ============================================================

@router.post("/admin/cleanup_blacklist")
def relaunch_cleanup_blacklist(db: Session = Depends(get_db_session)) -> Dict[str, Any]:
    """
    Деактивирует все игры из blacklist (мегахиты).
    Используется для очистки существующих записей.
    """
    from apps.api.routers.relaunch_config import EXCLUDE_APP_IDS, EXCLUDE_NAME_CONTAINS
    
    if not table_exists(db, "relaunch_apps"):
        raise HTTPException(500, "Таблица relaunch_apps не найдена")
    
    # Деактивируем по app_id
    blacklist_app_ids = [int(aid) for aid in EXCLUDE_APP_IDS]  # КРИТИЧНО: массив int (БД BIGINT после миграции)
    deactivated_by_id = 0
    if blacklist_app_ids:
        result = db.execute(
            text("""
                UPDATE relaunch_apps
                SET is_active = false
                WHERE steam_app_id = ANY(:app_ids) AND is_active = true
            """),
            {"app_ids": blacklist_app_ids},
        )
        deactivated_by_id = result.rowcount
        db.commit()
    
    # Деактивируем по имени (case-insensitive)
    deactivated_by_name = 0
    for exclude_name in EXCLUDE_NAME_CONTAINS:
        result = db.execute(
            text("""
                UPDATE relaunch_apps
                SET is_active = false
                WHERE LOWER(name) LIKE :pattern AND is_active = true
            """),
            {"pattern": f"%{exclude_name.lower()}%"},
        )
        deactivated_by_name += result.rowcount

        db.commit()

    return {
        "status": "ok",
        "deactivated_by_app_id": deactivated_by_id,
        "deactivated_by_name": deactivated_by_name,
        "total_deactivated": deactivated_by_id + deactivated_by_name,
        "note": f"Деактивировано {deactivated_by_id + deactivated_by_name} игр из blacklist.",
    }


# ============================================================
# Compute Scores Endpoint
# ============================================================

class ComputeScoresRequest(BaseModel):
    """Запрос на пересчёт scores."""
    limit: int = Field(200, ge=1, le=1000, description="Сколько игр обработать")


@router.post("/admin/compute_scores")
def relaunch_compute_scores(
    request: ComputeScoresRequest = ComputeScoresRequest(),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Пересчёт scores для активных игр.
    Запускает scoring синхронно (для MVP).
    """
    from datetime import datetime, timezone
    
    if not table_exists(db, "relaunch_apps"):
        raise HTTPException(500, "Таблица relaunch_apps не найдена")
    
    # Проверяем/создаём таблицу relaunch_scores
    if not table_exists(db, "relaunch_scores"):
        # Создаём таблицу если её нет
        db.execute(
            text("""
                CREATE TABLE IF NOT EXISTS relaunch_scores (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    app_id UUID NOT NULL REFERENCES relaunch_apps(id) ON DELETE CASCADE,
                    computed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    relaunch_score FLOAT NOT NULL DEFAULT 0.0,
                    classification TEXT NOT NULL DEFAULT 'candidate',
                    failure_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
                    relaunch_angles JSONB NOT NULL DEFAULT '[]'::jsonb,
                    reasoning_text TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
                )
            """)
        )
        db.execute(
            text("""
                CREATE INDEX IF NOT EXISTS idx_relaunch_scores_app_id ON relaunch_scores(app_id);
                CREATE INDEX IF NOT EXISTS idx_relaunch_scores_computed_at ON relaunch_scores(computed_at DESC);
            """)
        )
        db.commit()
    
    # Диагностика: проверяем сколько всего игр в БД (ДО выборки)
    try:
        total_count = db.execute(
            text("SELECT COUNT(*) as cnt FROM relaunch_apps")
        ).scalar() or 0
        active_count = db.execute(
            text("SELECT COUNT(*) as cnt FROM relaunch_apps WHERE is_active = true")
        ).scalar() or 0
        
        # Подсчитываем кандидатов (если есть таблица с scores)
        candidates_count = 0
        if table_exists(db, "relaunch_scores"):
            try:
                candidates_count = db.execute(
                    text("SELECT COUNT(DISTINCT app_id) FROM relaunch_scores")
                ).scalar() or 0
            except Exception:
                pass
    except Exception as diag_error:
        logger.warning(f"Diagnostics error: {diag_error}")
        total_count = 0
        active_count = 0
        candidates_count = 0
    
    # Получаем активные игры
    apps = db.execute(
        text("""
            SELECT id, steam_app_id, name
            FROM relaunch_apps
            WHERE is_active = true
            ORDER BY tracking_priority DESC, id DESC
            LIMIT :limit
        """),
        {"limit": int(request.limit)},
    ).mappings().all()
    
    logger.info(f"Compute scores: total={total_count}, active={active_count}, candidates={candidates_count}, requested={request.limit}, found={len(apps)}")
    
    if not apps:
        return {
            "status": "ok",
            "processed": 0,
            "updated": 0,
            "total_in_db": total_count,
            "total_candidates": candidates_count,
            "total_tracked": active_count,
            "total_requested": 0,
            "errors": [],
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "note": f"Нет активных игр для scoring. Всего: {total_count}, активных: {active_count}, кандидатов: {candidates_count}.",
        }
    
    # Импортируем scorer
    try:
        from apps.worker.relaunch_scorer import compute_relaunch_score
    except ImportError:
        # Fallback: простой scoring без внешних метрик
        logger.warning("relaunch_scorer не найден, используем простой fallback scoring")
        def compute_relaunch_score(*args, **kwargs):
            from typing import NamedTuple
            class Result(NamedTuple):
                relaunch_score: float = 50.0
                classification: str = "candidate"
                failure_reasons: list = []
                relaunch_angles: list = []
                reasoning_text: str = "Scoring не настроен (relaunch_scorer не найден)."
            return Result()
    
    now = datetime.now(timezone.utc)
    processed = 0
    errors = []
    
    for app in apps:
        try:
            app_id = app["id"]
            steam_app_id_str = str(app["steam_app_id"])  # КРИТИЧНО: string
            steam_app_id_int = int(app["steam_app_id"])
            name = app["name"] or ""
            
            # Вычисляем score (без внешних метрик для MVP)
            result = compute_relaunch_score(
                steam_app_id=steam_app_id_int,
                name=name,
                reviews_total=None,
                recent_reviews=None,
                rating_pct=None,
                price_eur=None,
                tags=[],
            )
            
            # Сохраняем в БД (вставляем новую запись, даже если computed_at одинаковый)
            # Используем INSERT без ON CONFLICT, чтобы всегда создавать новую запись
            db.execute(
                text("""
                    INSERT INTO relaunch_scores
                        (app_id, computed_at, relaunch_score, classification,
                         failure_reasons, relaunch_angles, reasoning_text)
                    VALUES
                        (:app_id, :computed_at, :score, :classification,
                         :failure_reasons, :relaunch_angles, :reasoning_text)
                """),
                {
                    "app_id": app_id,
                    "computed_at": now,
                    "score": float(result.relaunch_score),
                    "classification": str(result.classification),
                    "failure_reasons": result.failure_reasons if hasattr(result, 'failure_reasons') else [],
                    "relaunch_angles": result.relaunch_angles if hasattr(result, 'relaunch_angles') else [],
                    "reasoning_text": str(result.reasoning_text) if hasattr(result, 'reasoning_text') else "",
                },
            )
            processed += 1
        except Exception as e:
            errors.append({"steam_app_id": steam_app_id_str, "error": str(e)})
            logger.error(f"Scoring error for {steam_app_id_str}: {e}")
    
    db.commit()
    
    return {
        "status": "ok",
        "processed": processed,
        "updated": processed,  # В текущей реализации processed = updated
        "total_in_db": total_count,
        "total_candidates": candidates_count,
        "total_tracked": active_count,
        "total_requested": len(apps),
        "errors": errors[:10] if errors else [],  # Только первые 10 ошибок
        "computed_at": now.isoformat(),
        "note": f"Обработано {processed} из {len(apps)} запрошенных игр.",
    }


# ============================================================
# Probe Endpoints (диагностика Steam parsing)
# ============================================================

@router.get("/admin/probe/steam_search")
async def probe_steam_search(
    page: int = Query(1, ge=1, le=10, description="Номер страницы"),
    sort_by: str = Query("Released_DESC", description="Сортировка"),
    query: Optional[str] = Query(None, description="Поисковый запрос (опционально)"),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Probe: проверка Steam Search парсинга.
    Возвращает: status_code, final_url, items_found, app_ids_sample, markers, html_sample, elapsed_ms.
    """
    import time
    from apps.api.routers.steam_research_engine import steam_research_engine
    
    start_ms = time.time() * 1000
    
    try:
        params = {"sort_by": sort_by, "page": page, "category1": "998", "ndl": "1"}
        if query:
            params["term"] = query
        
        app_ids, diagnostics = steam_research_engine._fetch_search_page(params=params)
        
        return {
            "status_code": diagnostics.get("status_code", 0),
            "final_url": diagnostics.get("final_url", ""),
            "items_found": len(app_ids),
            "app_ids_sample": list(app_ids)[:5],  # Первые 5 для примера
            "markers": diagnostics.get("markers", {"search_result_row": False, "captcha": False, "agecheck": False}),
            "blocked_suspected": diagnostics.get("blocked_suspected", False),
            "html_sample": diagnostics.get("html_sample", "")[:1000],  # До 1000 символов
            "elapsed_ms": int((time.time() * 1000) - start_ms),
        }
    except Exception as e:
        logger.error(f"Probe steam_search error: {e}")
        return {
            "status_code": 0,
            "final_url": "",
            "items_found": 0,
            "app_ids_sample": [],
            "markers": {"search_result_row": False, "captcha": False, "agecheck": False},
            "html_sample": "",
            "elapsed_ms": int((time.time() * 1000) - start_ms),
            "error": str(e),
        }


@router.get("/admin/probe/steam_appdetails")
async def probe_steam_appdetails(
    app_id: int = Query(..., ge=1, description="Steam App ID"),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Probe: проверка Steam AppDetails API.
    Возвращает: http_status, details_ok, details_fail, fields_found, elapsed_ms, cc, l, errors.
    """
    import time
    from apps.api.routers.steam_research_engine import steam_research_engine
    
    start_ms = time.time() * 1000
    
    result = {
        "app_id": app_id,
        "http_status": 0,
        "details_ok": False,
        "details_fail": False,
        "fields_found": {
            "name": False,
            "type": False,
            "release_date": False,
            "is_free": False,
            "price_overview": False,
            "reviews_total": False,
        },
        "raw_data": {},
        "cc": "us",
        "l": "en",
        "elapsed_ms": 0,
        "errors": {
            "403": 0,
            "429": 0,
            "timeout": 0,
            "json": 0,
            "other": 0,
        },
    }
    
    try:
        app_details = steam_research_engine.fetch_app_details(app_id)
        if app_details:
            result["details_ok"] = True
            result["http_status"] = 200
            result["fields_found"]["name"] = bool(app_details.get("name"))
            result["fields_found"]["type"] = bool(app_details.get("type"))
            result["fields_found"]["release_date"] = bool(app_details.get("release_date"))
            result["fields_found"]["is_free"] = "is_free" in app_details
            result["fields_found"]["price_overview"] = bool(app_details.get("price_overview"))
            result["fields_found"]["reviews_total"] = bool(app_details.get("reviews_total")) and app_details.get("reviews_total", 0) > 0
            result["raw_data"] = {
                "name": app_details.get("name", "N/A")[:100],
                "type": app_details.get("type", "N/A"),
                "release_date": app_details.get("release_date", "N/A"),
                "is_free": app_details.get("is_free", False),
                "reviews_total": app_details.get("reviews_total", 0),
            }
        else:
            result["details_fail"] = True
            result["errors"]["other"] = 1
    except Exception as e:
        result["details_fail"] = True
        error_str = str(e).lower()
        if "403" in error_str or "forbidden" in error_str:
            result["errors"]["403"] = 1
        elif "429" in error_str or "rate limit" in error_str:
            result["errors"]["429"] = 1
        elif "timeout" in error_str:
            result["errors"]["timeout"] = 1
        elif "json" in error_str:
            result["errors"]["json"] = 1
        else:
            result["errors"]["other"] = 1
        logger.error(f"Probe steam_appdetails error for {app_id}: {e}")
    finally:
        result["elapsed_ms"] = int((time.time() * 1000) - start_ms)
    
    return result


@router.get("/admin/probe/reviews")
async def probe_reviews(
    app_id: int = Query(..., ge=1, description="Steam App ID"),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Probe: проверка Steam Reviews API.
    Возвращает: reviews_total, positive, negative, score, elapsed_ms, errors.
    """
    import time
    import requests
    
    start_ms = time.time() * 1000
    
    result = {
        "app_id": app_id,
        "reviews_total": 0,
        "positive": 0,
        "negative": 0,
        "score": 0.0,
        "elapsed_ms": 0,
        "errors": {
            "403": 0,
            "429": 0,
            "timeout": 0,
            "json": 0,
            "other": 0,
        },
    }
    
    try:
        STEAM_APPREVIEWS_URL = "https://store.steampowered.com/appreviews/{app_id}"
        response = requests.get(
            STEAM_APPREVIEWS_URL.format(app_id=app_id),
            params={"json": 1, "filter": "all", "language": "all", "num_per_page": 0},
            timeout=10
        )
        response.raise_for_status()
        
        review_data = response.json().get("query_summary", {})
        total_positive = review_data.get("total_positive", 0)
        total_negative = review_data.get("total_negative", 0)
        reviews_total = review_data.get("total_reviews", 0) or (total_positive + total_negative)
        
        result["reviews_total"] = reviews_total
        result["positive"] = total_positive
        result["negative"] = total_negative
        if reviews_total > 0:
            result["score"] = total_positive / reviews_total
    except Exception as e:
        error_str = str(e).lower()
        if "403" in error_str or "forbidden" in error_str:
            result["errors"]["403"] = 1
        elif "429" in error_str or "rate limit" in error_str:
            result["errors"]["429"] = 1
        elif "timeout" in error_str:
            result["errors"]["timeout"] = 1
        elif "json" in error_str:
            result["errors"]["json"] = 1
        else:
            result["errors"]["other"] = 1
        logger.error(f"Probe reviews error for {app_id}: {e}")
    finally:
        result["elapsed_ms"] = int((time.time() * 1000) - start_ms)
    
    return result


@router.get("/admin/probe/pipeline")
async def probe_pipeline(
    limit: int = Query(5, ge=1, le=20, description="Сколько app_ids проверить"),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Probe: проверка полного pipeline (search → details → filter).
    Возвращает: search_ok, details_ok/details_fail, filter_eligible, breakdown, elapsed_ms.
    """
    import time
    from apps.api.routers.steam_research_engine import steam_research_engine
    from apps.api.routers.relaunch_filters import filter_game_details
    
    start_ms = time.time() * 1000
    
    result = {
        "search_ok": False,
        "seed_app_ids": [],
        "details_ok": 0,
        "details_fail": 0,
        "filter_eligible": 0,
        "filter_excluded": 0,
        "excluded_reasons": {},
        "sample_details": [],
        "elapsed_ms": 0,
        "errors": {
            "403": 0,
            "429": 0,
            "timeout": 0,
            "json": 0,
            "other": 0,
        },
    }
    
    try:
        # 1) Search
        seed_app_ids_list, diagnostics = steam_research_engine._fetch_search_page(
            params={"sort_by": "Released_DESC", "page": 1, "category1": "998", "ndl": "1"}
        )
        result["search_ok"] = len(seed_app_ids_list) > 0
        result["seed_app_ids"] = list(seed_app_ids_list)[:limit]
        
        if not result["search_ok"]:
            return result
        
        # 2) Details fetch
        for app_id in result["seed_app_ids"]:
            # КРИТИЧНО: проверяем тип app_id перед вызовом fetch_app_details
            if not isinstance(app_id, int):
                logger.error(f"probe_pipeline: app_id is not int, got {type(app_id)}: {app_id}")
                result["details_fail"] += 1
                result["errors"]["other"] += 1
                continue
            
            time.sleep(steam_research_engine.rate_limit_delay)  # Rate limiting
            try:
                app_details = steam_research_engine.fetch_app_details(app_id)
                if app_details:
                    result["details_ok"] += 1
                    # 3) Filter
                    is_eligible, exclude_reason, _ = filter_game_details(
                        app_details,
                        min_months=6,
                        max_months=36,
                        min_reviews=50,
                        max_reviews=15000,
                        exclude_f2p=True,
                        strict_window=False,
                    )
                    if is_eligible:
                        result["filter_eligible"] += 1
                    else:
                        result["filter_excluded"] += 1
                        result["excluded_reasons"][exclude_reason or "unknown"] = result["excluded_reasons"].get(exclude_reason or "unknown", 0) + 1
                    
                    # Сохраняем sample
                    if len(result["sample_details"]) < 3:
                        result["sample_details"].append({
                            "app_id": app_id,
                            "name": app_details.get("name", "N/A")[:50],
                            "reviews_total": app_details.get("reviews_total", 0),
                            "release_date": app_details.get("release_date", "N/A"),
                            "is_eligible": is_eligible,
                            "exclude_reason": exclude_reason,
                        })
                else:
                    result["details_fail"] += 1
            except Exception as e:
                result["details_fail"] += 1
                error_str = str(e).lower()
                if "403" in error_str:
                    result["errors"]["403"] += 1
                elif "429" in error_str:
                    result["errors"]["429"] += 1
                elif "timeout" in error_str:
                    result["errors"]["timeout"] += 1
                elif "json" in error_str:
                    result["errors"]["json"] += 1
                else:
                    result["errors"]["other"] += 1
    except Exception as e:
        logger.error(f"Probe pipeline error: {e}")
        result["errors"]["other"] += 1
    finally:
        result["elapsed_ms"] = int((time.time() * 1000) - start_ms)
    
    return result


# ============================================================
# Cache Management Endpoints (v3)
# ============================================================

class BackfillCacheRequest(BaseModel):
    """Запрос на наполнение cache из games."""
    limit: int = Field(500, ge=1, le=2000)
    refresh: bool = Field(True, description="Обновить данные из Steam")


class RefreshCacheRequest(BaseModel):
    """Запрос на обновление cache для конкретных app_ids."""
    app_ids: List[int] = Field(..., min_items=1, max_items=500)


@router.post("/admin/cache/backfill_from_games")
async def cache_backfill_from_games(
    request: BackfillCacheRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Запускает job на наполнение cache из таблицы games.
    """
    import uuid
    from apps.api.routers.steam_cache import seed_cache_from_games_table, refresh_cache_for_app_ids
    from apps.api.routers.steam_research_engine import steam_research_engine
    
    job_id = str(uuid.uuid4())
    
    if table_exists(db, "steam_cache_jobs"):
        try:
            db.execute(
                text("""
                    INSERT INTO steam_cache_jobs (id, job_type, status, params, created_at)
                    VALUES (:id, :job_type, :status, :params, NOW())
                """),
                {
                    "id": job_id,
                    "job_type": "backfill_from_games",
                    "status": "queued",
                    "params": json.dumps({"limit": request.limit, "refresh": request.refresh}),
                },
            )
            db.commit()
        except Exception as e:
            logger.warning(f"Failed to create cache job: {e}")
            db.rollback()
    
    def run_backfill():
        try:
            if table_exists(db, "steam_cache_jobs"):
                db.execute(
                    text("UPDATE steam_cache_jobs SET status='running', started_at=NOW() WHERE id=:id"),
                    {"id": job_id},
                )
                db.commit()
            
            app_ids = seed_cache_from_games_table(db, limit=request.limit)
            
            if request.refresh and app_ids:
                stats = refresh_cache_for_app_ids(
                    app_ids,
                    db,
                    steam_research_engine,
                    rate_limit_delay=steam_research_engine.rate_limit_delay,
                )
                
                if table_exists(db, "steam_cache_jobs"):
                    db.execute(
                        text("""
                            UPDATE steam_cache_jobs
                            SET status='done', finished_at=NOW(), progress=:progress
                            WHERE id=:id
                        """),
                        {
                            "id": job_id,
                            "progress": json.dumps(stats),
                        },
                    )
                    db.commit()
            else:
                if table_exists(db, "steam_cache_jobs"):
                    db.execute(
                        text("""
                            UPDATE steam_cache_jobs
                            SET status='done', finished_at=NOW(), progress=:progress
                            WHERE id=:id
                        """),
                        {
                            "id": job_id,
                            "progress": json.dumps({"processed": len(app_ids), "ok": 0, "failed": 0}),
                        },
                    )
                    db.commit()
        except Exception as e:
            logger.error(f"Backfill job error: {e}")
            if table_exists(db, "steam_cache_jobs"):
                try:
                    db.execute(
                        text("""
                            UPDATE steam_cache_jobs
                            SET status='error', finished_at=NOW(), error_text=:error
                            WHERE id=:id
                        """),
                        {"id": job_id, "error": str(e)[:1000]},
                    )
                    db.commit()
                except Exception:
                    pass
    
    background_tasks.add_task(run_backfill)
    
    return {
        "status": "queued",
        "job_id": job_id,
        "job_type": "backfill_from_games",
        "note": f"Backfill job queued. Will process up to {request.limit} app_ids from games table.",
    }


@router.post("/admin/cache/refresh")
async def cache_refresh(
    request: RefreshCacheRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Обновляет cache для конкретных app_ids.
    """
    import uuid
    from apps.api.routers.steam_cache import refresh_cache_for_app_ids
    from apps.api.routers.steam_research_engine import steam_research_engine
    
    job_id = str(uuid.uuid4())
    
    if table_exists(db, "steam_cache_jobs"):
        try:
            db.execute(
                text("""
                    INSERT INTO steam_cache_jobs (id, job_type, status, params, created_at)
                    VALUES (:id, :job_type, :status, :params, NOW())
                """),
                {
                    "id": job_id,
                    "job_type": "manual_ids",
                    "status": "queued",
                    "params": json.dumps({"app_ids": request.app_ids}),
                },
            )
            db.commit()
        except Exception as e:
            logger.warning(f"Failed to create cache job: {e}")
            db.rollback()
    
    def run_refresh():
        try:
            if table_exists(db, "steam_cache_jobs"):
                db.execute(
                    text("UPDATE steam_cache_jobs SET status='running', started_at=NOW() WHERE id=:id"),
                    {"id": job_id},
                )
                db.commit()
            
            stats = refresh_cache_for_app_ids(
                request.app_ids,
                db,
                steam_research_engine,
                rate_limit_delay=steam_research_engine.rate_limit_delay,
            )
            
            if table_exists(db, "steam_cache_jobs"):
                db.execute(
                    text("""
                        UPDATE steam_cache_jobs
                        SET status='done', finished_at=NOW(), progress=:progress
                        WHERE id=:id
                    """),
                    {
                        "id": job_id,
                        "progress": json.dumps(stats),
                    },
                )
                db.commit()
        except Exception as e:
            logger.error(f"Refresh job error: {e}")
            if table_exists(db, "steam_cache_jobs"):
                try:
                    db.execute(
                        text("""
                            UPDATE steam_cache_jobs
                            SET status='error', finished_at=NOW(), error_text=:error
                            WHERE id=:id
                        """),
                        {"id": job_id, "error": str(e)[:1000]},
                    )
                    db.commit()
                except Exception:
                    pass
    
    background_tasks.add_task(run_refresh)
    
    return {
        "status": "queued",
        "job_id": job_id,
        "job_type": "manual_ids",
        "note": f"Refresh job queued for {len(request.app_ids)} app_ids.",
    }


@router.get("/admin/cache/job_status")
async def cache_job_status(
    job_id: str = Query(..., description="Job ID"),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Возвращает статус cache job.
    """
    if not table_exists(db, "steam_cache_jobs"):
        raise HTTPException(404, "steam_cache_jobs table not found")
    
    row = db.execute(
        text("""
            SELECT job_type, status, params, progress, started_at, finished_at, error_text, created_at
            FROM steam_cache_jobs
            WHERE id = :job_id
        """),
        {"job_id": job_id},
    ).mappings().first()
    
    if not row:
        raise HTTPException(404, f"Job {job_id} not found")
    
    # КРИТИЧНО: params и progress могут быть уже dict (JSONB) или строками
    params_data = row["params"]
    if isinstance(params_data, str):
        try:
            params_data = json.loads(params_data)
        except (json.JSONDecodeError, TypeError):
            params_data = {}
    elif params_data is None:
        params_data = {}
    
    progress_data = row["progress"]
    if isinstance(progress_data, str):
        try:
            progress_data = json.loads(progress_data)
        except (json.JSONDecodeError, TypeError):
            progress_data = {}
    elif progress_data is None:
        progress_data = {}
    
    return {
        "job_id": job_id,
        "job_type": row["job_type"],
        "status": row["status"],
        "params": params_data,
        "progress": progress_data,
        "started_at": row["started_at"].isoformat() if row["started_at"] else None,
        "finished_at": row["finished_at"].isoformat() if row["finished_at"] else None,
        "error_text": row["error_text"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


@router.get("/admin/cache/stats")
async def cache_stats(
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Возвращает статистику steam_app_cache.
    """
    if not table_exists(db, "steam_app_cache"):
        raise HTTPException(404, "steam_app_cache table not found")
    
    from datetime import date, timedelta
    
    today = date.today()
    min_date = today - timedelta(days=36 * 30)
    max_date = today - timedelta(days=6 * 30)
    
    rows_total = db.execute(text("SELECT COUNT(*) FROM steam_app_cache")).scalar() or 0
    rows_with_release_date = db.execute(
        text("SELECT COUNT(*) FROM steam_app_cache WHERE release_date IS NOT NULL")
    ).scalar() or 0
    rows_in_window = db.execute(
        text(f"""
            SELECT COUNT(*) FROM steam_app_cache
            WHERE release_date BETWEEN '{min_date}' AND '{max_date}'
        """)
    ).scalar() or 0
    rows_eligible_estimate = db.execute(
        text(f"""
            SELECT COUNT(*) FROM steam_app_cache
            WHERE release_date BETWEEN '{min_date}' AND '{max_date}'
              AND reviews_total BETWEEN 30 AND 20000
              AND is_free = false
              AND type = 'game'
        """)
    ).scalar() or 0
    last_updated_at = db.execute(
        text("SELECT MAX(updated_at) FROM steam_app_cache")
    ).scalar()
    
    return {
        "rows_total": rows_total,
        "rows_with_release_date": rows_with_release_date,
        "rows_in_window_6_36": rows_in_window,
        "rows_eligible_estimate": rows_eligible_estimate,
        "last_updated_at": last_updated_at.isoformat() if last_updated_at else None,
    }
