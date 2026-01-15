"""
ЛОГИКА: Расчёт недельных агрегатов для выявления стабильных/растущих трендов
"""

from apps.worker.celery_app import celery_app
from apps.db.session import get_db_session
from sqlalchemy import text
from datetime import date, timedelta
import logging

logger = logging.getLogger(__name__)

@celery_app.task(name="calculate_weekly_aggregates")
def calculate_weekly_aggregates_task():
    """Рассчитать недельные агрегаты трендов"""
    db = get_db_session()
    try:
        today = date.today()
        week_start = today - timedelta(days=7)
        
        # Получить тренды за неделю
        trends = db.execute(text("""
            SELECT 
                trend_name,
                AVG(trend_score) as avg_score,
                SUM(video_count + post_count) as total_mentions,
                COUNT(DISTINCT date) as days_present,
                STDDEV(trend_score) as score_stddev
            FROM trend_daily_snapshot
            WHERE date >= :week_start AND date <= :today
            GROUP BY trend_name
            HAVING COUNT(*) >= 3
            ORDER BY avg_score DESC
        """), {'week_start': week_start, 'today': today}).fetchall()
        
        for row in trends:
            name, avg_score, mentions, days, stddev = row
            
            # Рассчитать индекс стабильности (чем меньше отклонение, тем стабильнее)
            stability = 1.0 - min(float(stddev or 0) / float(avg_score or 1), 1.0) if avg_score else 0
            
            # Получить прошлонедельный score для расчёта роста
            prev_week = db.execute(text("""
                SELECT AVG(trend_score) 
                FROM trend_daily_snapshot
                WHERE trend_name = :name 
                AND date >= :prev_start AND date < :week_start
            """), {
                'name': name,
                'prev_start': week_start - timedelta(days=7),
                'week_start': week_start
            }).fetchone()
            
            prev_avg = prev_week[0] if prev_week and prev_week[0] else avg_score
            growth_rate = ((avg_score - prev_avg) / prev_avg * 100) if prev_avg > 0 else 0
            
            # Сохранить агрегат
            db.execute(text("""
                INSERT INTO trend_weekly_aggregate 
                (week_start, week_end, trend_name, avg_score, growth_rate, stability_index, total_mentions)
                VALUES (:start, :end, :name, :avg, :growth, :stability, :mentions)
                ON CONFLICT (week_start, trend_name) DO UPDATE
                SET avg_score = EXCLUDED.avg_score,
                    growth_rate = EXCLUDED.growth_rate,
                    stability_index = EXCLUDED.stability_index,
                    total_mentions = EXCLUDED.total_mentions
            """), {
                'start': week_start,
                'end': today,
                'name': name,
                'avg': float(avg_score),
                'growth': float(growth_rate),
                'stability': float(stability),
                'mentions': int(mentions)
            })
        
        db.commit()
        logger.info(f"✅ Calculated {len(trends)} weekly aggregates")
        return {"status": "success", "trends": len(trends)}
        
    except Exception as e:
        logger.error(f"Weekly aggregate error: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}
    finally:
        db.close()
