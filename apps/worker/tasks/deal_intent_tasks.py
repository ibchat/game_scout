"""
Deal Intent Worker Tasks
Периодические задачи для обновления deal intent данных.
"""
from apps.worker.celery_app import celery_app
from apps.db.session import get_db_session
from apps.worker.analysis.db_introspection import detect_steam_review_app_id_column
from apps.worker.analysis.deal_intent_scorer import analyze_deal_intent
from sqlalchemy import text
from datetime import datetime, date, timedelta
import logging
import json

logger = logging.getLogger(__name__)


@celery_app.task(name="deal_intent_snapshot_job")
def deal_intent_snapshot_task(limit: int = 100):
    """
    Периодическая задача: создаёт/обновляет snapshots в deal_intent_game.
    Периодичность: 6 часов.
    
    ВАЖНО: Записывает ВСЕ игры, даже с intent_score=0 и quality_score=0.
    Фильтры применяются только на уровне API/UI.
    """
    logger.info("deal_intent_snapshot: started, limit=%s", limit)
    db = get_db_session()
    try:
        # Определяем реальное имя колонки app_id в steam_review_daily
        try:
            app_id_col = detect_steam_review_app_id_column(db)
            logger.info("deal_intent_snapshot: detected app_id_col=%s", app_id_col)
        except Exception as e:
            logger.error(f"Failed to detect app_id column: {e}", exc_info=True)
            db.close()
            return {
                "status": "error",
                "error": f"Failed to detect app_id column: {e}"
            }
        
        # Проверяем seed apps
        seed_count_query = text("""
            SELECT COUNT(*) as cnt
            FROM trends_seed_apps
            WHERE is_active = true
        """)
        seed_count = db.execute(seed_count_query).scalar() or 0
        
        # Проверяем steam_app_cache coverage
        steam_count_query = text(f"""
            SELECT COUNT(DISTINCT c.steam_app_id) as cnt
            FROM trends_seed_apps s
            INNER JOIN steam_app_cache c ON c.steam_app_id = s.steam_app_id::bigint
            WHERE s.is_active = true
        """)
        steam_count = db.execute(steam_count_query).scalar() or 0
        
        logger.info(
            "deal_intent_snapshot: seed_apps=%s steam_apps=%s",
            seed_count,
            steam_count
        )
        
        # Получаем seed apps
        seed_query = text("""
            SELECT steam_app_id
            FROM trends_seed_apps
            WHERE is_active = true
            ORDER BY steam_app_id
            LIMIT :limit
        """)
        
        seed_apps = db.execute(seed_query, {"limit": limit}).scalars().all()
        
        processed = 0
        inserted = 0
        updated = 0
        skipped = 0
        errors = 0
        
        for app_id in seed_apps:
            logger.debug(f"Processing app_id: {app_id}")
            try:
                # Получаем данные игры
                # ВАЖНО: developers и publishers - это JSONB массивы, не отдельные колонки
                # early_access и coming_soon - проверяем через release_date или другие поля
                query = text(f"""
                    SELECT 
                        seed.steam_app_id,
                        COALESCE(NULLIF(c.name, ''), f.name, 'App #' || seed.steam_app_id::text) as steam_name,
                        COALESCE(NULLIF(c.steam_url, ''), 'https://store.steampowered.com/app/' || seed.steam_app_id::text || '/') as steam_url,
                        -- Developer: извлекаем первый элемент из JSONB массива
                        CASE 
                            WHEN c.developers IS NOT NULL AND jsonb_array_length(c.developers) > 0 THEN
                                c.developers->>0
                            WHEN f.developers IS NOT NULL AND jsonb_array_length(f.developers) > 0 THEN
                                f.developers->>0
                            ELSE NULL
                        END as developer_name,
                        -- Publisher: извлекаем первый элемент из JSONB массива
                        CASE 
                            WHEN c.publishers IS NOT NULL AND jsonb_array_length(c.publishers) > 0 THEN
                                c.publishers->>0
                            WHEN f.publishers IS NOT NULL AND jsonb_array_length(f.publishers) > 0 THEN
                                f.publishers->>0
                            ELSE NULL
                        END as publisher_name,
                        COALESCE(c.release_date, f.release_date) as release_date,
                        -- Stage: определяем по release_date и другим признакам
                        CASE 
                            WHEN c.release_date IS NULL AND f.release_date IS NULL THEN 'coming_soon'
                            WHEN c.release_date > CURRENT_DATE THEN 'coming_soon'
                            WHEN c.release_date IS NOT NULL AND c.release_date <= CURRENT_DATE THEN 'released'
                            WHEN f.release_date IS NOT NULL AND f.release_date <= CURRENT_DATE THEN 'released'
                            ELSE 'released'
                        END as stage,
                        false as has_demo,  -- TODO: определить через tags или другие поля
                        c.price_eur,
                        c.tags,
                        srd.all_reviews_count,
                        srd.recent_reviews_count_30d,
                        srd.all_positive_percent,
                        srd.all_positive_percent / 100.0 as positive_ratio
                    FROM trends_seed_apps seed
                    LEFT JOIN steam_app_cache c ON c.steam_app_id = seed.steam_app_id::bigint
                    LEFT JOIN steam_app_facts f ON f.steam_app_id = seed.steam_app_id
                    LEFT JOIN steam_review_daily srd ON srd.{app_id_col} = seed.steam_app_id
                        AND srd.day = (SELECT MAX(day) FROM steam_review_daily WHERE {app_id_col} = seed.steam_app_id)
                    WHERE seed.steam_app_id = :app_id
                      AND seed.is_active = true
                """)
                
                try:
                    row = db.execute(query, {"app_id": app_id}).mappings().first()
                except Exception as sql_err:
                    logger.error(f"SQL error for app {app_id}: {type(sql_err).__name__}: {sql_err}", exc_info=True)
                    # Rollback транзакции при ошибке SQL
                    try:
                        db.rollback()
                    except:
                        pass
                    errors += 1
                    continue
                
                if not row:
                    logger.debug(f"No data found for app {app_id}, skipping")
                    skipped += 1
                    continue
                
                # Получаем сигналы для этой игры
                signals = []
                try:
                    signals_query = text("""
                        SELECT source, url, text, signal_type, confidence
                        FROM deal_intent_signal
                        WHERE app_id = :app_id
                    """)
                    signals_rows = db.execute(signals_query, {"app_id": app_id}).mappings().all()
                    signals = [dict(s) for s in signals_rows]
                except Exception as sig_err:
                    # Если таблицы нет или ошибка - просто пустой список
                    logger.debug(f"Could not fetch signals for app {app_id}: {sig_err}")
                    signals = []
                
                # Анализируем
                app_data = dict(row)
                try:
                    result = analyze_deal_intent(app_data, signals)
                except Exception as analyze_err:
                    logger.error(f"Failed to analyze_deal_intent for app {app_id}: {type(analyze_err).__name__}: {analyze_err}", exc_info=True)
                    db.rollback()
                    errors += 1
                    continue
                
                # Проверяем, существует ли уже запись
                try:
                    exists_query = text("SELECT app_id FROM deal_intent_game WHERE app_id = :app_id")
                    exists = db.execute(exists_query, {"app_id": app_id}).scalar()
                except Exception as check_err:
                    logger.error(f"Failed to check existence for app {app_id}: {type(check_err).__name__}: {check_err}", exc_info=True)
                    db.rollback()
                    errors += 1
                    continue
                
                # Upsert в deal_intent_game
                # ВАЖНО: Записываем ВСЕ игры, даже с score=0
                upsert_query = text("""
                    INSERT INTO deal_intent_game (
                        app_id, steam_name, steam_url, developer_name, publisher_name,
                        release_date, stage, has_demo, price_eur, tags,
                        intent_score, quality_score, intent_reasons, quality_reasons, updated_at
                    )
                    VALUES (
                        :app_id, :steam_name, :steam_url, :developer_name, :publisher_name,
                        :release_date, :stage, :has_demo, :price_eur, CAST(:tags AS jsonb),
                        :intent_score, :quality_score, CAST(:intent_reasons AS jsonb), CAST(:quality_reasons AS jsonb), now()
                    )
                    ON CONFLICT (app_id) DO UPDATE SET
                        steam_name = EXCLUDED.steam_name,
                        steam_url = EXCLUDED.steam_url,
                        developer_name = EXCLUDED.developer_name,
                        publisher_name = EXCLUDED.publisher_name,
                        release_date = EXCLUDED.release_date,
                        stage = EXCLUDED.stage,
                        has_demo = EXCLUDED.has_demo,
                        price_eur = EXCLUDED.price_eur,
                        tags = EXCLUDED.tags,
                        intent_score = EXCLUDED.intent_score,
                        quality_score = EXCLUDED.quality_score,
                        intent_reasons = EXCLUDED.intent_reasons,
                        quality_reasons = EXCLUDED.quality_reasons,
                        updated_at = now()
                """)
                
                try:
                    # Преобразуем JSONB поля в JSON строки
                    tags_value = app_data.get("tags")
                    if tags_value is None:
                        tags_json = "[]"
                    elif isinstance(tags_value, (dict, list)):
                        tags_json = json.dumps(tags_value)
                    else:
                        tags_json = str(tags_value)
                    
                    intent_reasons_value = result.get("intent_reasons", [])
                    if isinstance(intent_reasons_value, (dict, list)):
                        intent_reasons_json = json.dumps(intent_reasons_value)
                    else:
                        intent_reasons_json = json.dumps([])
                    
                    quality_reasons_value = result.get("quality_reasons", [])
                    if isinstance(quality_reasons_value, (dict, list)):
                        quality_reasons_json = json.dumps(quality_reasons_value)
                    else:
                        quality_reasons_json = json.dumps([])
                    
                    db.execute(
                        upsert_query,
                        {
                            "app_id": app_id,
                            "steam_name": app_data.get("steam_name"),
                            "steam_url": app_data.get("steam_url"),
                            "developer_name": app_data.get("developer_name"),
                            "publisher_name": app_data.get("publisher_name"),
                            "release_date": app_data.get("release_date"),
                            "stage": app_data.get("stage"),
                            "has_demo": app_data.get("has_demo", False),
                            "price_eur": app_data.get("price_eur"),
                            "tags": tags_json,
                            "intent_score": result.get("intent_score", 0),
                            "quality_score": result.get("quality_score", 0),
                            "intent_reasons": intent_reasons_json,
                            "quality_reasons": quality_reasons_json
                        }
                    )
                    db.commit()  # Commit после каждого успешного upsert
                except Exception as upsert_err:
                    logger.error(f"Failed to upsert app {app_id}: {type(upsert_err).__name__}: {upsert_err}", exc_info=True)
                    db.rollback()
                    errors += 1
                    continue
                
                if exists:
                    updated += 1
                else:
                    inserted += 1
                processed += 1
                
            except Exception as e:
                logger.error(f"Failed to process app {app_id} in deal_intent_snapshot: {type(e).__name__}: {e}", exc_info=True)
                db.rollback()
                errors += 1
                continue
        
        # Финальный commit не нужен, так как мы коммитим после каждого upsert
        # db.commit()
        
        logger.info(
            "deal_intent_snapshot: inserted=%s updated=%s skipped=%s errors=%s",
            inserted,
            updated,
            skipped,
            errors
        )
        
        return {
            "status": "ok",
            "processed": processed,
            "inserted": inserted,
            "updated": updated,
            "skipped": skipped,
            "errors": errors,
            "total_seed_apps": len(seed_apps)
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"deal_intent_snapshot_task failed: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e)
        }
    finally:
        db.close()


@celery_app.task(name="deal_intent_alert_job")
def deal_intent_alert_task():
    """
    Периодическая задача: проверяет триггеры для alerts.
    Периодичность: 1 час.
    
    Триггеры:
    - demo появился
    - reviews_30d x2
    - publisher изменился
    - появились external links
    """
    db = get_db_session()
    try:
        # Определяем реальное имя колонки app_id в steam_review_daily
        app_id_col = detect_steam_review_app_id_column(db)
        
        alerts = []
        
        # 1. Проверяем появление demo
        demo_query = text(f"""
            SELECT 
                d.app_id,
                d.steam_name,
                'demo_appeared' as alert_type
            FROM deal_intent_game d
            INNER JOIN steam_app_cache c ON c.steam_app_id = d.app_id::bigint
            WHERE d.has_demo = false
              AND COALESCE(c.has_demo, false) = true
              AND d.updated_at < now() - interval '1 hour'
        """)
        
        demo_alerts = db.execute(demo_query).mappings().all()
        alerts.extend([dict(a) for a in demo_alerts])
        
        # 2. Проверяем рост reviews_30d x2
        reviews_query = text(f"""
            SELECT 
                d.app_id,
                d.steam_name,
                'reviews_growth' as alert_type,
                srd.recent_reviews_count_30d as current_reviews,
                d.updated_at
            FROM deal_intent_game d
            INNER JOIN steam_review_daily srd ON srd.{app_id_col} = d.app_id
                AND srd.day = (SELECT MAX(day) FROM steam_review_daily WHERE {app_id_col} = d.app_id)
            WHERE srd.recent_reviews_count_30d IS NOT NULL
              AND srd.recent_reviews_count_30d >= 20
              AND d.updated_at < now() - interval '1 hour'
        """)
        
        # TODO: Сравнить с предыдущим значением (нужна история)
        # Пока просто логируем игры с ростом
        
        # 3. Проверяем изменение publisher
        publisher_query = text("""
            SELECT 
                d.app_id,
                d.steam_name,
                'publisher_changed' as alert_type,
                d.publisher_name as old_publisher,
                c.publisher_name as new_publisher
            FROM deal_intent_game d
            INNER JOIN steam_app_cache c ON c.steam_app_id = d.app_id::bigint
            WHERE d.publisher_name IS DISTINCT FROM c.publisher_name
              AND d.updated_at < now() - interval '1 hour'
        """)
        
        publisher_alerts = db.execute(publisher_query).mappings().all()
        alerts.extend([dict(a) for a in publisher_alerts])
        
        # 4. Проверяем появление external links (если есть в сигналах)
        links_query = text("""
            SELECT DISTINCT
                s.app_id,
                d.steam_name,
                'external_links' as alert_type
            FROM deal_intent_signal s
            INNER JOIN deal_intent_game d ON d.app_id = s.app_id
            WHERE s.created_at >= now() - interval '1 hour'
              AND s.source != 'steam'
        """)
        
        links_alerts = db.execute(links_query).mappings().all()
        alerts.extend([dict(a) for a in links_alerts])
        
        # Логируем alerts (можно расширить для отправки уведомлений)
        for alert in alerts:
            logger.info(f"Deal intent alert: {alert}")
        
        return {
            "status": "ok",
            "alerts_count": len(alerts),
            "alerts": alerts[:20]  # Топ-20
        }
        
    except Exception as e:
        logger.error(f"deal_intent_alert_task failed: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e)
        }
    finally:
        db.close()
