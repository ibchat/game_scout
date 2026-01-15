from apps.worker.celery_app import celery_app
from apps.db.session import get_db_session
from apps.db.models_investor import YouTubeTrendSnapshot, ExternalCommentSample
from apps.db.models_youtube import YouTubeTrendVideo
from datetime import date
import logging

logger = logging.getLogger(__name__)

@celery_app.task(name="analyze_youtube_trends")
def analyze_youtube_trends_task(query_set='indie_radar'):
    db = get_db_session()
    try:
        today = date.today()
        
        # Собрать данные
        videos = db.query(YouTubeTrendVideo).filter(
            YouTubeTrendVideo.query_set == query_set
        ).all()
        
        # Mock анализ (в реале - LLM)
        snapshot = YouTubeTrendSnapshot(
            date=today,
            query_set=query_set,
            top_terms=['roguelike', 'cozy', 'survival', 'indie'],
            top_patterns=['chaos_to_order', 'weak_to_strong'],
            top_mechanics=['deckbuilder', 'automation', 'extraction'],
            top_games_mentions=['Hollow Knight Silksong', 'Dispatch'],
            signals={
                'intent_ratio': 0.65,
                'confusion_ratio': 0.15,
                'emotions': {'satisfying': 0.4, 'cozy': 0.3, 'challenging': 0.3}
            },
            confidence=0.75,
            video_count=len(videos)
        )
        db.add(snapshot)
        db.commit()
        
        logger.info(f"Created trend snapshot for {query_set}")
        return {"status": "success", "snapshot_id": str(snapshot.id)}
    finally:
        db.close()
