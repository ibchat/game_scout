"""
Analyze Video Comments Task
LLM-классификация комментариев для извлечения инвестиционных сигналов
"""
from apps.worker.celery_app import celery_app
from apps.worker.llm.client import get_llm_client
from apps.worker.llm.prompts import (
    PROMPT_COMMENT_CLASSIFIER,
    PROMPT_NARRATIVE_ALIGNMENT
)
from apps.db.session import get_db_session
from apps.db.models_investor import (
    ExternalVideo,
    ExternalCommentSample,
    ExternalCommentAnalysis,
    ExternalSignalDaily
)
from sqlalchemy import select
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@celery_app.task(name="apps.worker.tasks.analyze_video_comments.analyze_video_comments_task")
def analyze_video_comments_task(video_id: str):
    """
    Анализировать комментарии к видео через LLM
    
    Args:
        video_id: UUID видео из external_videos
    """
    logger.info(f"🤖 Starting comment analysis for video {video_id}")
    
    try:
        # Проверить LLM client
        llm = get_llm_client()
        if not llm:
            logger.warning("LLM not configured, skipping analysis")
            return {
                "status": "skipped",
                "reason": "LLM API key not configured"
            }
        
        db = get_db_session()
        
        try:
            # 1. Получить видео и комментарии
            stmt = select(ExternalVideo).where(ExternalVideo.id == video_id)
            video = db.execute(stmt).scalar_one_or_none()
            
            if not video:
                return {"status": "error", "error": f"Video {video_id} not found"}
            
            # Получить комментарии
            stmt = select(ExternalCommentSample).where(
                ExternalCommentSample.video_id == video_id
            ).limit(200)
            comments = db.execute(stmt).scalars().all()
            
            if not comments:
                logger.info(f"No comments found for video {video_id}")
                return {
                    "status": "success",
                    "message": "No comments to analyze"
                }
            
            logger.info(f"Analyzing {len(comments)} comments for video: {video.title}")
            
            # 2. Подготовить текст комментариев
            comments_text = "\n\n".join([
                f"Comment {i+1}: {comment.comment_text}"
                for i, comment in enumerate(comments[:100])  # Ограничим до 100 для токенов
            ])
            
            # 3. Классифицировать комментарии
            prompt = PROMPT_COMMENT_CLASSIFIER.format(
                game_title=video.game.title,
                platform=video.platform,
                video_title=video.title,
                comment_count=len(comments),
                comments_text=comments_text
            )
            
            logger.info("Sending comments to LLM for classification...")
            analysis_result = llm.generate_json(prompt, max_tokens=2000, temperature=0.3)
            
            if not analysis_result:
                return {
                    "status": "error",
                    "error": "LLM failed to generate valid response"
                }
            
            logger.info(f"LLM analysis result: {analysis_result}")
            
            # 4. Сохранить результат
            analysis = ExternalCommentAnalysis(
                video_id=video.id,
                intent_ratio=analysis_result.get('intent_ratio', 0.0),
                confusion_ratio=analysis_result.get('confusion_ratio', 0.0),
                emotions=analysis_result.get('emotions', {}),
                summary_bullets=analysis_result.get('insights', []),
                confidence=analysis_result.get('confidence', 0.5),
                llm_model=llm.model,
                analyzed_at=datetime.utcnow()
            )
            
            db.add(analysis)
            db.commit()
            
            logger.info(
                f"✅ Comment analysis saved: intent={analysis.intent_ratio:.2f}, "
                f"confusion={analysis.confusion_ratio:.2f}, confidence={analysis.confidence:.2f}"
            )
            
            # 5. Обновить ExternalSignalDaily (агрегация)
            update_external_signal_daily(db, video.game_id, video.platform)
            
            return {
                "status": "success",
                "analysis": {
                    "intent_ratio": analysis.intent_ratio,
                    "confusion_ratio": analysis.confusion_ratio,
                    "emotions": analysis.emotions,
                    "insights_count": len(analysis.summary_bullets),
                    "confidence": analysis.confidence
                }
            }
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"❌ Comment analysis failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


def update_external_signal_daily(db, game_id: str, platform: str):
    """
    Обновить/создать ExternalSignalDaily для игры
    Агрегирует данные из всех проанализированных видео
    """
    from apps.db.models import Game
    from sqlalchemy import func
    
    logger.info(f"Updating ExternalSignalDaily for game {game_id}, platform {platform}")
    
    try:
        # Получить все видео игры на платформе с анализом
        stmt = select(ExternalVideo).join(
            ExternalCommentAnalysis
        ).where(
            ExternalVideo.game_id == game_id,
            ExternalVideo.platform == platform
        )
        
        videos = db.execute(stmt).scalars().all()
        
        if not videos:
            logger.debug("No analyzed videos found for aggregation")
            return
        
        # Агрегировать метрики
        total_views = sum(v.views or 0 for v in videos)
        total_engagement = sum(
            ((v.likes or 0) + (v.comments_count or 0) * 2) / (v.views or 1)
            for v in videos
        ) / len(videos)
        
        # Средний intent и confusion
        avg_intent = sum(v.comment_analysis.intent_ratio for v in videos) / len(videos)
        avg_confusion = sum(v.comment_analysis.confusion_ratio for v in videos) / len(videos)
        
        # Собрать эмоции
        all_emotions = {}
        for v in videos:
            for emotion, intensity in v.comment_analysis.emotions.items():
                if emotion not in all_emotions:
                    all_emotions[emotion] = []
                all_emotions[emotion].append(intensity)
        
        # Усреднить эмоции
        avg_emotions = {
            emotion: sum(intensities) / len(intensities)
            for emotion, intensities in all_emotions.items()
        }
        
        # Создать signal dict
        signal = {
            'views': total_views,
            'engagement': total_engagement,
            'intent_ratio': avg_intent,
            'confusion_ratio': avg_confusion,
            'videos_count': len(videos)
        }
        
        # Найти или создать ExternalSignalDaily
        today = datetime.utcnow().date()
        stmt = select(ExternalSignalDaily).where(
            ExternalSignalDaily.game_id == game_id,
            func.date(ExternalSignalDaily.date) == today
        )
        
        daily_signal = db.execute(stmt).scalar_one_or_none()
        
        if daily_signal:
            # Обновить существующий
            if platform == 'youtube':
                daily_signal.youtube_signal = signal
            elif platform == 'tiktok':
                daily_signal.tiktok_signal = signal
            
            daily_signal.videos_analyzed = len(videos)
            daily_signal.comments_analyzed = sum(
                v.comment_analysis.video.comments_count or 0 for v in videos
            )
        else:
            # Создать новый
            daily_signal = ExternalSignalDaily(
                game_id=game_id,
                date=datetime.utcnow(),
                youtube_signal=signal if platform == 'youtube' else None,
                tiktok_signal=signal if platform == 'tiktok' else None,
                videos_analyzed=len(videos),
                comments_analyzed=sum(
                    len(v.comment_samples) for v in videos
                )
            )
            db.add(daily_signal)
        
        db.commit()
        
        logger.info(
            f"✅ Updated ExternalSignalDaily: {platform} signal with "
            f"{len(videos)} videos, intent={avg_intent:.2f}"
        )
        
    except Exception as e:
        logger.error(f"Failed to update ExternalSignalDaily: {e}", exc_info=True)
