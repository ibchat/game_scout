"""
YouTube Collector Task
Сбор видео и комментариев из YouTube для игр
"""
from apps.worker.celery_app import celery_app
from apps.worker.integrations.youtube_client import YouTubeClient
from apps.db.session import get_db_session
from apps.db.models import Game
from apps.db.models_investor import ExternalVideo, ExternalCommentSample
from sqlalchemy import select
from datetime import datetime
import logging
import os

logger = logging.getLogger(__name__)


@celery_app.task(name="apps.worker.tasks.collect_youtube.collect_youtube_task")
def collect_youtube_task(game_id: str, max_videos: int = 10, comment_limit: int = 200):
    """
    Собрать YouTube видео и комментарии для игры
    
    Args:
        game_id: UUID игры
        max_videos: Сколько видео собрать (default: 10)
        comment_limit: Сколько комментариев на видео (default: 200)
    """
    logger.info(f"🎬 Starting YouTube collection for game {game_id}")
    
    results = {
        "videos_found": 0,
        "videos_saved": 0,
        "comments_saved": 0,
        "errors": []
    }
    
    try:
        # Проверить наличие API key
        api_key = os.getenv("YOUTUBE_API_KEY")
        use_mock = os.getenv("YOUTUBE_MOCK_MODE", "false").lower() == "true"
        
        if not api_key or api_key == "your_youtube_api_key_here":
            if not use_mock:
                logger.warning("YouTube API key not configured, skipping collection")
                return {
                    "status": "skipped",
                    "reason": "YouTube API key not configured"
                }
            else:
                logger.info("Using YouTube MOCK mode for testing")
        
        db = get_db_session()
        
        try:
            # 1. Получить игру
            stmt = select(Game).where(Game.id == game_id)
            game = db.execute(stmt).scalar_one_or_none()
            
            if not game:
                return {"status": "error", "error": f"Game {game_id} not found"}
            
            logger.info(f"Collecting YouTube data for: {game.title}")
            
            # 2. Инициализировать YouTube client
            youtube = YouTubeClient(api_key=api_key)
            
            # 3. Поиск видео
            search_query = f"{game.title} game trailer gameplay"
            
            if use_mock:
                # Mock данные для тестирования
                videos = [
                    {
                        'video_id': f'mock_{game.id}_1',
                        'title': f'{game.title} - Official Trailer',
                        'channel': 'GameDev Studio',
                        'published_at': '2024-01-01T00:00:00Z',
                        'view_count': 50000,
                        'like_count': 1500,
                        'comment_count': 120,
                        'url': f'https://youtube.com/watch?v=mock_{game.id}_1'
                    },
                    {
                        'video_id': f'mock_{game.id}_2',
                        'title': f'{game.title} - Gameplay',
                        'channel': 'Pro Gamer',
                        'published_at': '2024-01-05T00:00:00Z',
                        'view_count': 30000,
                        'like_count': 800,
                        'comment_count': 85,
                        'url': f'https://youtube.com/watch?v=mock_{game.id}_2'
                    }
                ]
                logger.info(f"Generated {len(videos)} mock videos")
            else:
                videos = youtube.search_videos(search_query, max_results=max_videos)
            
            results["videos_found"] = len(videos)
            
            if not videos:
                logger.info(f"No videos found for {game.title}")
                return {"status": "success", "results": results}
            
            # 4. Сохранить видео и комментарии
            for video_data in videos:
                try:
                    # Проверить не сохранено ли уже
                    stmt = select(ExternalVideo).where(
                        ExternalVideo.video_id == video_data['video_id']
                    )
                    existing = db.execute(stmt).scalar_one_or_none()
                    
                    if existing:
                        logger.debug(f"Video {video_data['video_id']} already exists")
                        continue
                    
                    # Создать ExternalVideo
                    video = ExternalVideo(
                        game_id=game.id,
                        platform='youtube',
                        video_id=video_data['video_id'],
                        title=video_data['title'],
                        url=video_data['url'],
                        views=video_data['view_count'],
                        likes=video_data['like_count'],
                        comments_count=video_data['comment_count'],
                        published_at=datetime.fromisoformat(
                            video_data['published_at'].replace('Z', '+00:00')
                        ) if video_data.get('published_at') else None,
                        collected_at=datetime.utcnow()
                    )
                    
                    db.add(video)
                    db.flush()  # Получить video.id
                    
                    results["videos_saved"] += 1
                    
                    # 5. Получить комментарии
                    if video_data['comment_count'] > 0:
                        if use_mock:
                            # Mock комментарии
                            comments = [
                                {
                                    'comment_id': f"mock_comment_{i}",
                                    'text': f"This game looks amazing! Can't wait to play it. Comment {i}",
                                    'author': f'User{i}',
                                    'like_count': i * 2,
                                    'published_at': '2024-01-10T00:00:00Z'
                                }
                                for i in range(min(10, comment_limit))
                            ]
                            logger.info(f"Generated {len(comments)} mock comments")
                        else:
                            comments = youtube.fetch_comments(
                                video_data['video_id'],
                                max_results=comment_limit
                            )
                        
                        for comment_data in comments:
                            comment = ExternalCommentSample(
                                video_id=video.id,
                                comment_text=comment_data['text'],
                                author=comment_data.get('author'),
                                likes=comment_data.get('like_count', 0),
                                published_at=datetime.fromisoformat(
                                    comment_data['published_at'].replace('Z', '+00:00')
                                ) if comment_data.get('published_at') else None,
                                collected_at=datetime.utcnow()
                            )
                            
                            db.add(comment)
                            results["comments_saved"] += 1
                        
                        logger.info(
                            f"Saved {len(comments)} comments for video {video_data['video_id']}"
                        )
                
                except Exception as e:
                    logger.error(f"Error saving video {video_data.get('video_id')}: {e}")
                    results["errors"].append(str(e))
                    continue
            
            db.commit()
            
            logger.info(f"✅ YouTube collection complete for {game.title}: {results}")
            return {"status": "success", "results": results}
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"❌ YouTube collection failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}
