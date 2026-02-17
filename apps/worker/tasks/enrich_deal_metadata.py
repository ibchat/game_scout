"""
Enrich Deal Metadata Task - Ensure game metadata for deal_intent_game app_ids
Автоматическое обогащение метаданных для новых app_id из ingestion.
"""
from apps.worker.celery_app import celery_app
from sqlalchemy import create_engine, text
import requests
import logging
import time
from typing import Dict, Any, Optional, List
import json
import os

logger = logging.getLogger(__name__)

STEAM_APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@postgres:5432/game_scout")


def ensure_game_metadata(app_id: int, db=None) -> Dict[str, Any]:
    """
    Гарантирует наличие метаданных для app_id в games и steam_app_cache.
    
    Returns:
        {
            "status": "ok" | "error" | "skipped",
            "app_id": app_id,
            "enriched": bool,
            "error": str (если status="error")
        }
    """
    from sqlalchemy import create_engine
    
    if db is None:
        engine = create_engine(DATABASE_URL, future=True)
        db = engine.connect()
        should_close = True
    else:
        should_close = False
    
    try:
        # Проверяем, есть ли уже метаданные (используем UNION вместо FULL OUTER JOIN)
        check_query = text("""
            SELECT 
                c.name, c.steam_url, c.developers, c.publishers,
                NULL as title, NULL as url
            FROM steam_app_cache c
            WHERE c.steam_app_id = CAST(:app_id AS BIGINT)
            UNION ALL
            SELECT 
                NULL as name, NULL as steam_url, NULL::jsonb as developers, NULL::jsonb as publishers,
                g.title, g.url
            FROM games g
            WHERE g.source = 'steam' AND g.source_id = CAST(:app_id AS TEXT)
            LIMIT 1
        """)
        existing = db.execute(check_query, {"app_id": str(app_id)}).mappings().first()
        
        # Если есть и title и steam_url - пропускаем
        if existing:
            has_name = (existing.get("name") or existing.get("title")) and (existing.get("name") or existing.get("title")).strip()
            has_url = (existing.get("steam_url") or existing.get("url")) and (existing.get("steam_url") or existing.get("url")).strip()
            if has_name and has_url:
                return {
                    "status": "skipped",
                    "app_id": app_id,
                    "enriched": False,
                    "reason": "metadata_already_exists"
                }
        
        # Получаем данные из Steam API
        try:
            params = {"appids": str(app_id), "l": "english"}
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            response = requests.get(STEAM_APPDETAILS_URL, params=params, headers=headers, timeout=15)
            
            # Обработка HTTP ошибок
            if response.status_code != 200:
                return {
                    "status": "error",
                    "app_id": app_id,
                    "enriched": False,
                    "error": f"http_status_{response.status_code}",
                    "exception_type": "HTTPError",
                    "http_status": response.status_code,
                    "url": response.url
                }
            
            try:
                payload = response.json()
            except ValueError as e:
                return {
                    "status": "error",
                    "app_id": app_id,
                    "enriched": False,
                    "error": "json_parse_error",
                    "exception_type": "JSONDecodeError",
                    "url": response.url
                }
            
            node = payload.get(str(app_id))
            if not node or not node.get("success"):
                return {
                    "status": "error",
                    "app_id": app_id,
                    "enriched": False,
                    "error": "appdetails_success_false",
                    "exception_type": "SteamAPIError",
                    "url": response.url
                }
            
            data = node.get("data")
            if not data:
                return {
                    "status": "error",
                    "app_id": app_id,
                    "enriched": False,
                    "error": "steam_api_empty_data",
                    "exception_type": "SteamAPIError",
                    "url": response.url
                }
            
            # Извлекаем поля
            name = data.get("name") or ""
            steam_url = f"https://store.steampowered.com/app/{app_id}/"
            developers = data.get("developers") or []
            publishers = data.get("publishers") or []
            release_date_str = (data.get("release_date") or {}).get("date", "")
            
            # Обновляем steam_app_cache
            upsert_cache_query = text("""
                INSERT INTO steam_app_cache (
                    steam_app_id, name, steam_url, developers, publishers, release_date, updated_at
                ) VALUES (
                    CAST(:app_id AS BIGINT), :name, :steam_url, 
                    CAST(:developers AS JSONB), CAST(:publishers AS JSONB), 
                    CASE WHEN :release_date_str != '' THEN CAST(:release_date_str AS DATE) ELSE NULL END,
                    NOW()
                )
                ON CONFLICT (steam_app_id) DO UPDATE SET
                    name = COALESCE(EXCLUDED.name, steam_app_cache.name),
                    steam_url = COALESCE(EXCLUDED.steam_url, steam_app_cache.steam_url),
                    developers = COALESCE(EXCLUDED.developers, steam_app_cache.developers),
                    publishers = COALESCE(EXCLUDED.publishers, steam_app_cache.publishers),
                    release_date = COALESCE(EXCLUDED.release_date, steam_app_cache.release_date),
                    updated_at = NOW()
            """)
            
            db.execute(upsert_cache_query, {
                "app_id": str(app_id),
                "name": name,
                "steam_url": steam_url,
                "developers": json.dumps(developers),
                "publishers": json.dumps(publishers),
                "release_date_str": release_date_str
            })
            
            # Обновляем games (id генерируется автоматически как UUID, tags обязателен)
            upsert_games_query = text("""
                INSERT INTO games (
                    id, source, source_id, title, url, tags, updated_at
                ) VALUES (
                    gen_random_uuid(), 'steam', CAST(:app_id AS TEXT), :title, :url, '[]'::jsonb, NOW()
                )
                ON CONFLICT (source, source_id) DO UPDATE SET
                    title = COALESCE(EXCLUDED.title, games.title),
                    url = COALESCE(EXCLUDED.url, games.url),
                    updated_at = NOW()
            """)
            
            db.execute(upsert_games_query, {
                "app_id": str(app_id),
                "title": name,
                "url": steam_url
            })
            
            db.commit()
            
            return {
                "status": "ok",
                "app_id": app_id,
                "enriched": True,
                "name": name,
                "steam_url": steam_url
            }
            
        except requests.RequestException as e:
            logger.warning(f"ENRICH_FAIL app_id={app_id} reason=request_exception exception={type(e).__name__}")
            return {
                "status": "error",
                "app_id": app_id,
                "enriched": False,
                "error": f"request_exception: {str(e)}",
                "exception_type": type(e).__name__,
                "reason": "http_request_failed"
            }
        except Exception as e:
            logger.error(f"ENRICH_FAIL app_id={app_id} reason=unexpected_error exception={type(e).__name__} error={str(e)}")
            db.rollback()
            return {
                "status": "error",
                "app_id": app_id,
                "enriched": False,
                "error": str(e),
                "exception_type": type(e).__name__,
                "reason": "unexpected_error"
            }
    
    finally:
        if should_close and db:
            db.close()


@celery_app.task(name="apps.worker.tasks.enrich_deal_metadata.enrich_missing_metadata_task")
def enrich_missing_metadata_task(limit: int = 200) -> Dict[str, Any]:
    """
    Находит app_id без метаданных и обогащает их.
    """
    logger.info(f"Enriching missing metadata for up to {limit} app_ids...")
    
    engine = create_engine(DATABASE_URL, future=True)
    db = engine.connect()
    try:
        # Находим app_id из deal_intent_game или deal_intent_signal без метаданных
        # Исключаем синтетические app_id (> 1000000) для более реалистичного обогащения
        missing_query = text("""
            SELECT DISTINCT d.app_id
            FROM (
                SELECT app_id FROM deal_intent_game
                UNION
                SELECT app_id FROM deal_intent_signal WHERE app_id IS NOT NULL
            ) d
            LEFT JOIN steam_app_cache c ON c.steam_app_id = d.app_id::bigint
            LEFT JOIN games g ON g.source = 'steam' AND g.source_id = d.app_id::text
            WHERE 
                d.app_id BETWEEN 1 AND 1000000
                AND (
                    (c.name IS NULL OR c.name = '' OR c.steam_url IS NULL OR c.steam_url = '')
                    AND (g.title IS NULL OR g.title = '' OR g.url IS NULL OR g.url = '')
                )
            ORDER BY d.app_id
            LIMIT :limit
        """)
        
        missing_rows = db.execute(missing_query, {"limit": limit}).mappings().all()
        app_ids = [row["app_id"] for row in missing_rows if row["app_id"]]
        
        logger.info(f"Found {len(app_ids)} app_ids without metadata")
        
        results = {
            "checked": len(app_ids),
            "enriched_ok": 0,
            "failed": 0,
            "skipped": 0,
            "sample_failures": []
        }
        
        for app_id in app_ids:
            try:
                result = ensure_game_metadata(app_id, db)
                if result["status"] == "ok" and result.get("enriched"):
                    results["enriched_ok"] += 1
                elif result["status"] == "skipped":
                    results["skipped"] += 1
                else:
                    results["failed"] += 1
                    if len(results["sample_failures"]) < 5:
                        failure_info = {
                            "app_id": app_id,
                            "error": result.get("error", "unknown"),
                            "reason": result.get("reason", "unknown"),
                            "exception_type": result.get("exception_type", "Unknown")
                        }
                        if "http_status" in result:
                            failure_info["http_status"] = result["http_status"]
                        if "url" in result:
                            failure_info["url"] = result["url"]
                        results["sample_failures"].append(failure_info)
                    logger.warning(f"ENRICH_FAIL app_id={app_id} reason={result.get('reason', 'unknown')} error={result.get('error', 'unknown')}")
                
                time.sleep(0.5)  # Rate limiting
                
            except Exception as e:
                logger.error(f"ENRICH_FAIL app_id={app_id} reason=exception_in_loop exception={type(e).__name__} error={str(e)}")
                results["failed"] += 1
                if len(results["sample_failures"]) < 5:
                    results["sample_failures"].append({
                        "app_id": app_id,
                        "error": str(e),
                        "reason": "exception_in_loop",
                        "exception_type": type(e).__name__
                    })
        
        logger.info(f"Enrichment complete: {results['enriched_ok']} enriched, {results['failed']} failed, {results['skipped']} skipped")
        
        return {
            "status": "ok",
            "result": results
        }
        
    except Exception as e:
        logger.error(f"Enrichment task failed: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e)
        }
    finally:
        if db:
            db.close()


@celery_app.task(name="apps.worker.tasks.enrich_deal_metadata.enrich_from_recent_signals_task")
def enrich_from_recent_signals_task(days: int = 7, limit: int = 200) -> Dict[str, Any]:
    """
    C2: Обогащает метаданные ТОЛЬКО для app_id, обнаруженных через свежие сигналы.
    Берет app_id из deal_intent_signal за последние N дней и обогащает через Steam API.
    """
    logger.info(f"Enriching metadata from recent signals (C2), days={days}, limit={limit}...")
    
    engine = create_engine(DATABASE_URL, future=True)
    db = engine.connect()
    try:
        # Находим app_id из deal_intent_signal за последние N дней
        # Исключаем синтетические app_id (> 1000000)
        recent_signals_query = text(f"""
            SELECT DISTINCT app_id, MAX(published_at) as latest_published_at
            FROM deal_intent_signal
            WHERE app_id IS NOT NULL
                AND app_id BETWEEN 1 AND 1000000
                AND published_at >= CURRENT_DATE - INTERVAL '{days} days'
            GROUP BY app_id
            ORDER BY latest_published_at DESC
            LIMIT :limit
        """)
        
        recent_rows = db.execute(recent_signals_query, {"limit": limit}).mappings().all()
        app_ids = [row["app_id"] for row in recent_rows if row["app_id"]]
        
        logger.info(f"Found {len(app_ids)} app_ids from recent signals (last {days} days)")
        
        results = {
            "checked": len(app_ids),
            "enriched_ok": 0,
            "failed": 0,
            "skipped": 0,
            "sample_failures": [],  # B1: До 3 failures с деталями
            "sample_skipped": []  # B1: До 3 skipped с причинами
        }
        
        for app_id in app_ids:
            try:
                result = ensure_game_metadata(app_id, db)
                if result["status"] == "ok" and result.get("enriched"):
                    results["enriched_ok"] += 1
                elif result["status"] == "skipped":
                    results["skipped"] += 1
                    # B1: Добавляем в sample_skipped
                    if len(results["sample_skipped"]) < 3:
                        results["sample_skipped"].append({
                            "app_id": app_id,
                            "reason": result.get("reason", "metadata_already_exists")
                        })
                else:
                    results["failed"] += 1
                    # B1: Добавляем в sample_failures с деталями
                    if len(results["sample_failures"]) < 3:
                        failure_info = {
                            "app_id": app_id,
                            "error": result.get("error", "unknown"),
                            "reason": result.get("reason", "unknown"),
                            "exception_type": result.get("exception_type", "Unknown")
                        }
                        if "http_status" in result:
                            failure_info["http_status"] = result["http_status"]
                        if "url" in result:
                            failure_info["url"] = result["url"]
                        results["sample_failures"].append(failure_info)
                    logger.warning(f"ENRICH_FAIL app_id={app_id} reason={result.get('reason', 'unknown')} error={result.get('error', 'unknown')}")
                
                time.sleep(0.5)  # Rate limiting
                
            except Exception as e:
                logger.error(f"ENRICH_FAIL app_id={app_id} reason=exception_in_loop exception={type(e).__name__} error={str(e)}")
                results["failed"] += 1
                if len(results["sample_failures"]) < 3:
                    results["sample_failures"].append({
                        "app_id": app_id,
                        "error": str(e),
                        "reason": "exception_in_loop",
                        "exception_type": type(e).__name__
                    })
        
        logger.info(f"Enrichment from recent signals complete: {results['enriched_ok']} enriched, {results['failed']} failed, {results['skipped']} skipped")
        
        return {
            "status": "ok",
            "result": results
        }
        
    except Exception as e:
        logger.error(f"Enrichment from recent signals task failed: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e)
        }
    finally:
        if db:
            db.close()
