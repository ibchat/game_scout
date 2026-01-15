"""
TikTok Collector Task
Сбор видео из TikTok для игр
"""
from apps.worker.celery_app import celery_app
from apps.worker.integrations.tiktok_client import TikTokClient
from apps.db.session import get_db_session
from apps.db.models import Game
from apps.db.models_investor import ExternalVideo
from sqlalchemy import select
from datetime import datetime
import logging
import os

logger = logging.getLogger(__name__)


@celery_app.task(name="apps.worker.tasks.collect_tiktok.collect_tiktok_task")
def collect_tiktok_task(game_id: str, max_videos: int = 10):
    """
    Собрать TikTok видео для игры
    
    Args:
        game_id: UUID игры
        max_videos: Сколько видео собрать (default: 10)
    """
    logger.info(f"📱 Starting TikTok collection for game {game_id}")
    
    results = {
        "videos_found": 0,
        "videos_saved": 0,
        "mode": "unknown",
        "errors": []
    }
    
    try:
        db = get_db_session()
        
        try:
            # 1. Получить игру
            stmt = select(Game).where(Game.id == game_id)
            game = db.execute(stmt).scalar_one_or_none()
            
            if not game:
                return {"status": "error", "error": f"Game {game_id} not found"}
            
            logger.info(f"Collecting TikTok data for: {game.title}")
            
            # 2. Инициализировать TikTok client
            mode = os.getenv("TIKTOK_MODE", "scrape")
            tiktok = TikTokClient(mode=mode)
            results["mode"] = tiktok.mode
            
            # 3. Поиск видео
            search_query = f"{game.title} game gameplay"
            videos = tiktok.search_videos(search_query, max_results=max_videos)
            
            results["videos_found"] = len(videos)
            
            if not videos:
                logger.info(f"No TikTok videos found for {game.title}")
                return {"status": "success", "results": results}
            
            # 4. Сохранить видео
            for video_data in videos:
                try:
                    # Проверить не сохранено ли уже
                    stmt = select(ExternalVideo).where(
                        ExternalVideo.video_id == video_data['video_id']
                    )
                    existing = db.execute(stmt).scalar_one_or_none()
                    
                    if existing:
                        logger.debug(f"TikTok video {video_data['video_id']} already exists")
                        continue
                    
                    # Создать ExternalVideo
                    video = ExternalVideo(
                        game_id=game.id,
                        platform='tiktok',
                        video_id=video_data['video_id'],
                        title=video_data.get('title'),
                        url=video_data['url'],
                        views=video_data.get('views', 0),
                        likes=video_data.get('likes', 0),
                        comments_count=video_data.get('comments_count', 0),
                        published_at=datetime.fromisoformat(
                            video_data['published_at'].replace('Z', '+00:00')
                        ) if video_data.get('published_at') else None,
                        collected_at=datetime.utcnow()
                    )
                    
                    db.add(video)
                    results["videos_saved"] += 1
                    
                    logger.info(
                        f"Saved TikTok video: {video_data['video_id']} "
                        f"({video_data.get('views', 0)} views)"
                    )
                
                except Exception as e:
                    logger.error(f"Error saving TikTok video {video_data.get('video_id')}: {e}")
                    results["errors"].append(str(e))
                    continue
            
            db.commit()
            
            logger.info(f"✅ TikTok collection complete for {game.title}: {results}")
            return {"status": "success", "results": results}
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"❌ TikTok collection failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}
