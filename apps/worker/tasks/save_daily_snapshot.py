"""
ЛОГИКА ИСТОЧНИКОВ:
YouTube — ранний индикатор интереса
Reddit — подтверждение органического спроса
Itch.io — поиск ранних и недооценённых проектов
Steam — валидация и масштабирование
"""

from apps.worker.celery_app import celery_app
from apps.db.session import get_db_session
from sqlalchemy import text
from datetime import date
import logging

logger = logging.getLogger(__name__)

@celery_app.task(name="save_daily_snapshot")
def save_daily_snapshot_task():
    """Сохранить ежедневный снимок трендов"""
    db = get_db_session()
    try:
        today = date.today()
        
        # Получить топ механики из YouTube
        youtube_data = db.execute(text("""
            SELECT 
                unnest(top_mechanics) as mechanic,
                COUNT(*) as mentions,
                AVG(confidence) as avg_confidence
            FROM youtube_trend_snapshots
            WHERE date = :today
            GROUP BY mechanic
            ORDER BY mentions DESC
            LIMIT 10
        """), {'today': today}).fetchall()
        
        for row in youtube_data:
            mechanic, mentions, confidence = row
            
            db.execute(text("""
                INSERT INTO trend_daily_snapshot 
                (date, source, trend_name, trend_type, trend_score, confidence, video_count, keywords)
                VALUES (:date, 'youtube', :name, 'механика', :score, :conf, :count, '{}')
                ON CONFLICT (date, source, trend_name) DO UPDATE
                SET trend_score = EXCLUDED.trend_score, confidence = EXCLUDED.confidence
            """), {
                'date': today,
                'name': mechanic,
                'score': int(mentions * 10),
                'conf': float(confidence) if confidence else 0.5,
                'count': int(mentions)
            })
        
        # Получить топ темы из Reddit
        reddit_data = db.execute(text("""
            SELECT 
                query,
                COUNT(*) as post_count,
                SUM(score) as total_score,
                SUM(num_comments) as total_comments
            FROM reddit_trend_posts
            WHERE collected_at::date = :today
            GROUP BY query
            ORDER BY total_score DESC
            LIMIT 10
        """), {'today': today}).fetchall()
        
        for row in reddit_data:
            query, post_count, total_score, total_comments = row
            
            db.execute(text("""
                INSERT INTO trend_daily_snapshot 
                (date, source, trend_name, trend_type, trend_score, confidence, post_count, comment_count, keywords)
                VALUES (:date, 'reddit', :name, 'тема', :score, :conf, :posts, :comments, '{}')
                ON CONFLICT (date, source, trend_name) DO UPDATE
                SET trend_score = EXCLUDED.trend_score, post_count = EXCLUDED.post_count
            """), {
                'date': today,
                'name': query,
                'score': int(total_score or 0),
                'conf': 0.7 if post_count > 5 else 0.5,
                'posts': int(post_count),
                'comments': int(total_comments or 0)
            })
        
        db.commit()
        logger.info(f"✅ Сохранён дневной snapshot: {len(youtube_data)} YouTube + {len(reddit_data)} Reddit")
        return {"status": "success", "youtube": len(youtube_data), "reddit": len(reddit_data)}
        
    except Exception as e:
        logger.error(f"Snapshot save error: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}
    finally:
        db.close()
