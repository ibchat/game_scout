"""
Steam Reviews Collector for Deal Intent Signals (Vector A EXEC v1 A3)
Собирает сигналы из steam_review_daily на основе review velocity spikes.
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
from sqlalchemy import text

from apps.worker.celery_app import celery_app
from apps.db.session import get_db_session

logger = logging.getLogger(__name__)


@celery_app.task(name="apps.worker.tasks.collect_deal_intent_signals_steam_reviews.collect_deal_intent_signals_steam_reviews_task")
def collect_deal_intent_signals_steam_reviews_task(days: int = 180) -> Dict[str, Any]:
    """
    Собирает Deal Intent Signals из Steam Reviews (Vector A EXEC v1 A3).
    
    Идея: игры с аномалией review velocity или ростом review volume могут
    сигнализировать о поиске издателя/маркетинга.
    
    Args:
        days: Количество дней назад для анализа (Vector A: минимум 180)
    
    Returns:
        {
            "status": "ok",
            "signals_saved": int,
            "signals_with_app_id": int,
            "signals_skipped": int,
            "errors": List[str]
        }
    """
    db = get_db_session()
    results = {
        "status": "ok",
        "signals_saved": 0,
        "signals_with_app_id": 0,
        "signals_skipped": 0,
        "errors": []
    }
    
    try:
        # Определяем реальное имя колонки app_id в steam_review_daily
        # Используем introspection для совместимости
        app_id_col_result = db.execute(
            text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'steam_review_daily' 
                AND column_name IN ('app_id', 'steam_app_id')
                LIMIT 1
            """)
        ).scalar()
        
        app_id_col = app_id_col_result or 'steam_app_id'  # Fallback
        
        # Находим игры с review velocity spike за последние N дней
        # Критерии для spike:
        # - recent_reviews_count_30d > 10 (минимум активности)
        # - recent_reviews_count_30d значительно больше среднего за период
        # - или резкий рост по сравнению с предыдущим периодом
        
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # Запрос для поиска игр с review velocity spikes
        # Используем только существующие колонки steam_review_daily
        spike_query = text(f"""
            WITH daily_reviews AS (
                SELECT 
                    {app_id_col} as app_id,
                    day,
                    recent_reviews_count_30d,
                    all_reviews_count,
                    all_positive_percent
                FROM steam_review_daily
                WHERE day >= :cutoff_date
                AND {app_id_col} IS NOT NULL
                AND recent_reviews_count_30d IS NOT NULL
            ),
            app_stats AS (
                SELECT 
                    app_id,
                    MAX(day) as latest_day,
                    MAX(recent_reviews_count_30d) as max_recent_30d,
                    AVG(recent_reviews_count_30d) as avg_recent_30d,
                    COUNT(*) as days_with_data
                FROM daily_reviews
                GROUP BY app_id
            ),
            spike_candidates AS (
                SELECT 
                    a.app_id,
                    a.latest_day,
                    a.max_recent_30d,
                    a.avg_recent_30d,
                    CASE 
                        WHEN a.avg_recent_30d > 0 THEN (a.max_recent_30d::float / NULLIF(a.avg_recent_30d, 0))
                        ELSE 0
                    END as velocity_ratio
                FROM app_stats a
                WHERE a.max_recent_30d >= 10  -- Минимум активности
                AND a.days_with_data >= 7  -- Минимум 7 дней данных
                AND (
                    -- Критерий 1: velocity_ratio > 1.5 (резкий рост)
                    (a.max_recent_30d::float / NULLIF(a.avg_recent_30d, 0)) > 1.5
                    OR
                    -- Критерий 2: абсолютный рост > 20 reviews за 30 дней
                    a.max_recent_30d >= 20
                )
            )
            SELECT DISTINCT
                sc.app_id,
                sc.latest_day,
                sc.max_recent_30d,
                sc.velocity_ratio
            FROM spike_candidates sc
            WHERE sc.app_id NOT IN (
                -- Исключаем игры, которые уже имеют behavioral_intent сигналы
                SELECT DISTINCT app_id 
                FROM deal_intent_signal 
                WHERE app_id IS NOT NULL 
                AND signal_type = 'behavioral_intent'
                AND published_at >= :cutoff_date
            )
            ORDER BY sc.velocity_ratio DESC, sc.max_recent_30d DESC
            LIMIT 100  -- Ограничиваем количество для безопасности
        """)
        
        spike_games = db.execute(
            spike_query,
            {"cutoff_date": cutoff_date}
        ).mappings().all()
        
        logger.info(f"Found {len(spike_games)} games with review velocity spikes")
        
        for game in spike_games:
            try:
                app_id = game['app_id']
                latest_day = game['latest_day']
                max_recent_30d = game['max_recent_30d']
                velocity_ratio = game.get('velocity_ratio', 0)
                
                # Создаём сигнал типа behavioral_intent
                # Согласно TZ_SIGNAL_INGESTION_VECTOR_A_EXEC_V1.md п.3.A3
                signal_text = f"review velocity spike detected: {max_recent_30d} reviews in last 30 days (ratio: {velocity_ratio:.2f})"
                signal_url = f"steam_reviews://app/{app_id}/spike/{latest_day.strftime('%Y-%m-%d')}"
                
                # Вставляем сигнал с идемпотентностью
                try:
                    db.execute(
                        text("""
                            INSERT INTO deal_intent_signal (
                                app_id, source, url, text, signal_type, published_at, created_at
                            ) VALUES (
                                :app_id, 'steam_reviews', :url, :text, 'behavioral_intent', :published_at, NOW()
                            )
                            ON CONFLICT (source, url) DO NOTHING
                        """),
                        {
                            "app_id": app_id,
                            "url": signal_url,
                            "text": signal_text[:5000],  # Ограничиваем длину
                            "published_at": latest_day
                        }
                    )
                    
                    # Проверяем, был ли вставлен сигнал
                    inserted_check = db.execute(
                        text("SELECT id FROM deal_intent_signal WHERE source = 'steam_reviews' AND url = :url"),
                        {"url": signal_url}
                    ).scalar()
                    
                    if inserted_check:
                        results["signals_saved"] += 1
                        results["signals_with_app_id"] += 1
                        logger.debug(f"Saved Steam Reviews signal: app_id={app_id}, velocity_ratio={velocity_ratio:.2f}")
                    else:
                        results["signals_skipped"] += 1
                    
                    db.commit()
                    
                except Exception as insert_error:
                    if "unique constraint" in str(insert_error).lower() or "duplicate key" in str(insert_error).lower():
                        results["signals_skipped"] += 1
                        db.rollback()
                        continue
                    else:
                        raise
                
            except Exception as e:
                error_msg = f"Error processing app_id {game.get('app_id', 'unknown')}: {str(e)}"
                logger.error(error_msg, exc_info=True)
                results["errors"].append(error_msg)
                db.rollback()
                continue
        
        logger.info(
            f"Steam Reviews Deal Intent Signals (Vector A A3): saved={results['signals_saved']}, "
            f"with_app_id={results['signals_with_app_id']}, skipped={results['signals_skipped']}"
        )
        
        return results
        
    except Exception as e:
        logger.error(f"Steam Reviews Deal Intent Signals collection failed: {e}", exc_info=True)
        results["status"] = "error"
        results["errors"].append(str(e))
        return results
        
    finally:
        db.close()
