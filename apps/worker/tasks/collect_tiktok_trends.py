from apps.worker.celery_app import celery_app
from apps.db.session import get_db_session
from apps.db.models_youtube import TikTokTrendVideo
import logging
import os

logger = logging.getLogger(__name__)

QUERY_SETS = {
    'indie_radar': ["indie game", "indie game trailer", "new indie game"],
    'genre_radar': ["cozy game", "roguelike game", "survival game"],
    'mechanic_radar': ["deckbuilder game", "automation game", "extraction shooter"]
}

@celery_app.task(name="collect_tiktok_trends")
def collect_tiktok_trend_videos_task(query_set='indie_radar', max_per_query=25):
    db = get_db_session()
    try:
        api_key = os.getenv('TIKTOK_API_KEY')
        
        from apps.worker.integrations.tiktok_client import TikTokClient
        client = TikTokClient(api_key)
        
        queries = QUERY_SETS.get(query_set, QUERY_SETS['indie_radar'])
        total_videos = 0
        
        for query in queries:
            videos = client.search_videos(query, max_per_query)
            
            for video_data in videos:
                video = TikTokTrendVideo(
                    video_id=video_data['video_id'],
                    title=video_data['title'],
                    url=video_data['url'],
                    username=video_data['username'],
                    view_count=video_data['view_count'],
                    like_count=video_data['like_count'],
                    comment_count=video_data['comment_count'],
                    share_count=video_data['share_count'],
                    query=query,
                    query_set=query_set
                )
                db.merge(video)
            
            db.commit()
            total_videos += len(videos)
            logger.info(f"Collected {len(videos)} TikTok videos for '{query}'")
        
        mode = "real" if api_key else "mock"
        return {"status": "success", "videos": total_videos, "mode": mode}
        
    except Exception as e:
        logger.error(f"TikTok collection error: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}
    finally:
        db.close()
