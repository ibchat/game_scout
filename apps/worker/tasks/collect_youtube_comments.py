from apps.worker.celery_app import celery_app
from apps.db.session import get_db_session
from apps.db.models_youtube import YouTubeTrendVideo
from apps.db.models_investor import ExternalCommentSample
import logging
import os

logger = logging.getLogger(__name__)

@celery_app.task(name="collect_youtube_comments")
def collect_youtube_trend_comments_task(top_n=20, comments_per_video=50):
    db = get_db_session()
    try:
        api_key = os.getenv('YOUTUBE_API_KEY')
        if not api_key:
            return {"status": "skipped", "reason": "no_api_key"}
        
        videos = db.query(YouTubeTrendVideo).order_by(
            YouTubeTrendVideo.view_count.desc()
        ).limit(top_n).all()
        
        from apps.worker.integrations.youtube_client import YouTubeClient
        client = YouTubeClient(api_key)
        
        # Нужно найти соответствующие external_videos
        from apps.db.models_investor import ExternalVideo
        
        total = 0
        for yt_video in videos:
            # Найти ExternalVideo по video_id
            ext_video = db.query(ExternalVideo).filter(
                ExternalVideo.video_id == yt_video.video_id,
                ExternalVideo.platform == 'youtube'
            ).first()
            
            if not ext_video:
                logger.warning(f"No ExternalVideo for {yt_video.video_id}")
                continue
            
            comments = client.get_video_comments(yt_video.video_id, comments_per_video)
            for c in comments:
                comment = ExternalCommentSample(
                    video_id=ext_video.id,
                    comment_text=c.get('text', ''),
                    author=c.get('author'),
                    likes=c.get('like_count', 0)
                )
                db.add(comment)
                total += 1
            
            db.commit()
            logger.info(f"Collected {len(comments)} comments for {yt_video.title}")
        
        return {"status": "success", "comments": total, "videos": len(videos)}
    except Exception as e:
        logger.error(f"Comment collection error: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}
    finally:
        db.close()
