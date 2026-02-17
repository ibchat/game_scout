"""
YouTube Collector for Deal Intent Signals Vector B EXEC v1
Использует существующие ExternalVideo и ExternalCommentSample для матчинга keywords.
Согласно TZ_SIGNAL_INGESTION_VECTOR_B_EXEC_V1.md
"""
import re
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
from sqlalchemy import text, select

from apps.worker.celery_app import celery_app
from apps.db.session import get_db_session
from apps.db.models_investor import ExternalVideo, ExternalCommentSample
from apps.worker.config.behavioral_intent_keywords import BEHAVIORAL_KEYWORDS
from apps.worker.tasks.collect_deal_intent_signals_reddit import (
    extract_steam_app_ids,
    match_keywords
)

logger = logging.getLogger(__name__)


@celery_app.task(name="apps.worker.tasks.collect_deal_intent_signals_youtube.collect_deal_intent_signals_youtube_task")
def collect_deal_intent_signals_youtube_task(days: int = 365) -> Dict[str, Any]:
    """
    Собирает Deal Intent Signals из существующих YouTube данных (Vector B EXEC v1).
    Анализирует ExternalVideo (title) и ExternalCommentSample (comments).
    
    Согласно TZ_SIGNAL_INGESTION_VECTOR_B_EXEC_V1.md:
    - Только существующие таблицы (external_videos, external_comment_samples)
    - Строгая фильтрация app_id (только Steam links)
    - Идемпотентность через ON CONFLICT (source, url)
    - Только существующие колонки в deal_intent_signal
    
    Args:
        days: Количество дней назад для поиска видео (по умолчанию 365 для максимального покрытия)
    
    Returns:
        {
            "status": "ok",
            "videos_processed": int,
            "comments_processed": int,
            "signals_saved": int,
            "signals_with_app_id": int,
            "signals_skipped": int,
            "errors": List[str]
        }
    """
    db = get_db_session()
    results = {
        "status": "ok",
        "videos_processed": 0,
        "comments_processed": 0,
        "signals_saved": 0,
        "signals_with_app_id": 0,
        "signals_skipped": 0,
        "errors": []
    }
    
    try:
        # Получаем ВСЕ YouTube видео (без ограничения по дате для максимального покрытия)
        # Согласно ТЗ: использовать все существующие данные
        stmt = select(ExternalVideo).where(
            ExternalVideo.platform == 'youtube'
        ).order_by(ExternalVideo.published_at.desc() if ExternalVideo.published_at else ExternalVideo.collected_at.desc())
        
        videos = db.execute(stmt).scalars().all()
        results["videos_processed"] = len(videos)
        
        logger.info(f"Processing {len(videos)} YouTube videos for Deal Intent Signals (Vector B)")
        
        # Обрабатываем видео-level сигналы
        for video in videos:
            try:
                # Video-level: анализируем title
                video_text = video.title or ''
                
                if not video_text.strip():
                    continue
                
                # Матчим keywords в title
                keyword_result = match_keywords(video_text)
                matched_keywords = keyword_result["matched_keywords"]
                intent_strength = keyword_result["intent_strength"]
                
                # Если нет keywords - пропускаем
                if not matched_keywords or intent_strength == 0:
                    continue
                
                # Извлекаем Steam app_id СТРОГО (только из Steam links)
                # Ищем в title и url
                search_text = f"{video_text} {video.url or ''}"
                extracted_app_ids = extract_steam_app_ids(search_text, video.url or '')
                
                # Согласно ТЗ п.4: нет app_id → нет сигнала
                if not extracted_app_ids:
                    results["signals_skipped"] += 1
                    continue
                
                # Берем первый app_id
                app_id = extracted_app_ids[0]
                
                # Определяем signal_type
                signal_type = "behavioral_intent" if intent_strength >= 4 else "intent_keyword"
                
                # Создаем snippet (≤ 280 символов согласно ТЗ п.7)
                snippet = video_text[:280]
                
                # Используем published_at или collected_at
                published_at = video.published_at or video.collected_at or datetime.utcnow()
                
                # Проверяем существование сигнала (идемпотентность)
                existing_check = db.execute(
                    text("SELECT id FROM deal_intent_signal WHERE source = 'youtube' AND url = :url"),
                    {"url": video.url or ''}
                ).scalar()
                
                if existing_check:
                    results["signals_skipped"] += 1
                    continue
                
                # Вставляем сигнал
                db.execute(
                    text("""
                        INSERT INTO deal_intent_signal (
                            app_id, source, url, text, signal_type, published_at, created_at
                        ) VALUES (
                            :app_id, 'youtube', :url, :text, :signal_type, :published_at, NOW()
                        )
                    """),
                    {
                        "app_id": app_id,
                        "url": video.url or '',
                        "text": snippet,
                        "signal_type": signal_type,
                        "published_at": published_at
                    }
                )
                
                db.commit()
                
                results["signals_saved"] += 1
                results["signals_with_app_id"] += 1
                
                logger.debug(f"Saved YouTube video signal: {video.url}, app_id={app_id}")
                
            except Exception as e:
                error_msg = f"Error processing video {video.url or 'unknown'}: {str(e)}"
                logger.error(error_msg, exc_info=True)
                results["errors"].append(error_msg)
                db.rollback()
                continue
        
        # Обрабатываем comment-level сигналы
        comments_stmt = select(ExternalCommentSample)
        comments = db.execute(comments_stmt).scalars().all()
        results["comments_processed"] = len(comments)
        
        logger.info(f"Processing {len(comments)} YouTube comments for Deal Intent Signals")
        
        for comment in comments:
            try:
                comment_text = comment.comment_text or ''
                
                if not comment_text.strip():
                    continue
                
                # Матчим keywords в комментарии
                keyword_result = match_keywords(comment_text)
                matched_keywords = keyword_result["matched_keywords"]
                intent_strength = keyword_result["intent_strength"]
                
                # Если нет keywords - пропускаем
                if not matched_keywords or intent_strength == 0:
                    continue
                
                # Получаем связанное видео для извлечения app_id
                video_stmt = select(ExternalVideo).where(ExternalVideo.id == comment.video_id)
                video = db.execute(video_stmt).scalar_one_or_none()
                
                if not video:
                    continue
                
                # Извлекаем Steam app_id из комментария и связанного видео
                search_text = f"{comment_text} {video.title or ''} {video.url or ''}"
                extracted_app_ids = extract_steam_app_ids(search_text, video.url or '')
                
                # Согласно ТЗ п.4: нет app_id → нет сигнала
                if not extracted_app_ids:
                    results["signals_skipped"] += 1
                    continue
                
                app_id = extracted_app_ids[0]
                
                # Определяем signal_type
                signal_type = "behavioral_intent" if intent_strength >= 4 else "intent_keyword"
                
                # Создаем snippet (≤ 280 символов)
                snippet = comment_text[:280]
                
                # Используем published_at комментария или видео
                published_at = comment.published_at or video.published_at or video.collected_at or datetime.utcnow()
                
                # URL для комментария: используем URL видео (комментарии не имеют отдельного URL)
                comment_url = f"{video.url}#comment-{comment.id}"
                
                # Проверяем существование сигнала (идемпотентность)
                existing_check = db.execute(
                    text("SELECT id FROM deal_intent_signal WHERE source = 'youtube' AND url = :url"),
                    {"url": comment_url}
                ).scalar()
                
                if existing_check:
                    results["signals_skipped"] += 1
                    continue
                
                # Вставляем сигнал
                db.execute(
                    text("""
                        INSERT INTO deal_intent_signal (
                            app_id, source, url, text, signal_type, published_at, created_at
                        ) VALUES (
                            :app_id, 'youtube', :url, :text, :signal_type, :published_at, NOW()
                        )
                    """),
                    {
                        "app_id": app_id,
                        "url": comment_url,
                        "text": snippet,
                        "signal_type": signal_type,
                        "published_at": published_at
                    }
                )
                
                db.commit()
                
                results["signals_saved"] += 1
                results["signals_with_app_id"] += 1
                
                logger.debug(f"Saved YouTube comment signal: app_id={app_id}")
                
            except Exception as e:
                error_msg = f"Error processing comment {comment.id}: {str(e)}"
                logger.error(error_msg, exc_info=True)
                results["errors"].append(error_msg)
                db.rollback()
                continue
        
        logger.info(
            f"YouTube Deal Intent Signals (Vector B): videos={results['videos_processed']}, "
            f"comments={results['comments_processed']}, saved={results['signals_saved']}, "
            f"with_app_id={results['signals_with_app_id']}, skipped={results['signals_skipped']}"
        )
        
        return results
        
    except Exception as e:
        logger.error(f"YouTube Deal Intent Signals collection failed: {e}", exc_info=True)
        results["status"] = "error"
        results["errors"].append(str(e))
        return results
        
    finally:
        db.close()
