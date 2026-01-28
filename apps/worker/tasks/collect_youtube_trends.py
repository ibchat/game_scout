from apps.worker.celery_app import celery_app
from apps.db.session import get_db_session
from apps.db.models_youtube import YouTubeTrendVideo
from sqlalchemy import text
from datetime import datetime
import logging

from apps.worker.config.external_apis import YOUTUBE_API_KEY

logger = logging.getLogger(__name__)

QUERY_SETS = {
    'indie_radar': ["indie game trailer", "indie game demo", "upcoming indie game"],
    'genre_radar': ["cozy game", "roguelike game", "survival game"],
    'mechanic_radar': ["deckbuilder game", "automation game", "extraction shooter"]
}

@celery_app.task(name="collect_youtube_trends")
def collect_youtube_trend_videos_task(query_set='indie_radar', max_per_query=25):
    return {"status": "disabled", "reason": "Temporarily disabled: SQLAlchemy mapper error GameNarrativeAnalysis->Game (fix later)"}
    
    db = get_db_session()
    history_id = None
    try:
        result = db.execute(text("""
            INSERT INTO trend_collection_history (source, query_set, status, started_at)
            VALUES ('youtube', :query_set, 'running', NOW())
            RETURNING id
        """), {'query_set': query_set})
        history_id = result.fetchone()[0]
        db.commit()
        
        from apps.worker.integrations.youtube_client import YouTubeClient
        client = YouTubeClient(YOUTUBE_API_KEY)
        
        queries = QUERY_SETS.get(query_set, QUERY_SETS['indie_radar'])
        total_videos = 0
        
        for query in queries:
            videos = client.search_videos(query, max_per_query)
            
            for video_data in videos:
                # Проверить существует ли
                existing = db.query(YouTubeTrendVideo).filter_by(video_id=video_data['video_id']).first()
                
                if existing:
                    # Обновить
                    existing.query = query
                    existing.query_set = query_set
                    existing.collected_at = datetime.utcnow()
                else:
                    # Создать новый
                    video = YouTubeTrendVideo(
                        video_id=video_data['video_id'],
                        title=video_data['title'],
                        url=video_data.get('url', f"https://www.youtube.com/watch?v={video_data['video_id']}"),
                        description=video_data.get('description'),
                        channel_title=video_data['channel_title'],
                        view_count=video_data['view_count'],
                        like_count=video_data['like_count'],
                        comment_count=video_data['comment_count'],
                        published_at=video_data['published_at'],
                        query=query,
                        query_set=query_set
                    )
                    db.add(video)
            
            db.commit()
            total_videos += len(videos)
            logger.info(f"Collected {len(videos)} YouTube videos for '{query}'")
        
        db.execute(text("""
            UPDATE trend_collection_history 
            SET status = 'completed', items_collected = :count, completed_at = NOW()
            WHERE id = :id
        """), {'id': history_id, 'count': total_videos})
        db.commit()
        
        logger.info(f"✅ Successfully collected {total_videos} YouTube videos")
        mode = "real" if YOUTUBE_API_KEY else "mock"
        return {"status": "success", "videos": total_videos, "mode": mode}
        
    except Exception as e:
        logger.error(f"YouTube collection error: {e}", exc_info=True)
        if history_id:
            db.execute(text("""
                UPDATE trend_collection_history 
                SET status = 'failed', completed_at = NOW(), error_message = :error
                WHERE id = :id
            """), {'id': history_id, 'error': str(e)[:500]})
            db.commit()
        return {"status": "error", "error": str(e)}
    finally:
        db.close()
