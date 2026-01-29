"""
YouTube Collector for Deal Intent Signals v3.2
Использует существующие ExternalVideo и ExternalCommentSample для матчинга keywords.
"""
import re
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
    extract_links,
    detect_language,
    match_keywords
)

logger = logging.getLogger(__name__)


@celery_app.task(name="apps.worker.tasks.collect_deal_intent_signals_youtube.collect_deal_intent_signals_youtube_task")
def collect_deal_intent_signals_youtube_task(days: int = 30) -> Dict[str, Any]:
    """
    Собирает Deal Intent Signals из существующих YouTube данных.
    Анализирует ExternalVideo (title, description) и ExternalCommentSample (comments).
    
    Args:
        days: Количество дней назад для поиска видео (по умолчанию 30)
    
    Returns:
        {
            "status": "ok",
            "videos_processed": int,
            "signals_saved": int,
            "signals_with_app_id": int,
            "errors": List[str]
        }
    """
    db = get_db_session()
    results = {
        "status": "ok",
        "videos_processed": 0,
        "signals_saved": 0,
        "signals_with_app_id": 0,
        "signals_skipped": 0,
        "errors": []
    }
    
    try:
        # Получаем YouTube видео за последние N дней
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        stmt = select(ExternalVideo).where(
            ExternalVideo.platform == 'youtube',
            ExternalVideo.published_at >= cutoff_date
        ).order_by(ExternalVideo.published_at.desc()).limit(200)  # Ограничиваем для MVP
        
        videos = db.execute(stmt).scalars().all()
        results["videos_processed"] = len(videos)
        
        logger.info(f"Processing {len(videos)} YouTube videos for Deal Intent Signals")
        
        for video in videos:
            try:
                # Объединяем title и description для анализа
                video_text = f"{video.title or ''} {getattr(video, 'description', '') or ''}"
                
                # Получаем комментарии для этого видео
                comments_stmt = select(ExternalCommentSample).where(
                    ExternalCommentSample.video_id == video.id
                ).limit(50)  # Берем первые 50 комментариев
                
                comments = db.execute(comments_stmt).scalars().all()
                comments_text = " ".join([c.comment_text or '' for c in comments[:20]])  # Первые 20 комментариев
                
                # Объединяем текст видео и комментариев
                full_text = f"{video_text} {comments_text}"
                
                if not full_text.strip():
                    continue
                
                # Матчим keywords
                keyword_result = match_keywords(full_text)
                matched_keywords = keyword_result["matched_keywords"]
                intent_strength = keyword_result["intent_strength"]
                
                # Если нет keywords - пропускаем
                if not matched_keywords or intent_strength == 0:
                    results["signals_skipped"] += 1
                    continue
                
                # Извлекаем Steam app_id из video URL, title, description, комментариев
                extracted_app_ids = extract_steam_app_ids(full_text, video.url or '')
                
                # Извлекаем ссылки
                extracted_links = extract_links(full_text, video.url or '')
                
                # Определяем язык
                lang = detect_language(full_text)
                
                # Определяем app_id (если нашли один) или title_guess
                app_id = extracted_app_ids[0] if extracted_app_ids else None
                title_guess = video.title[:200] if not app_id else None
                
                # Проверяем, не существует ли уже такой сигнал (по source + url)
                existing_check = db.execute(
                    text("SELECT id FROM deal_intent_signal WHERE source = 'youtube' AND url = :url"),
                    {"url": video.url or ''}
                ).scalar()
                
                if existing_check:
                    results["signals_skipped"] += 1
                    continue
                
                # Используем published_at как ts
                ts = video.published_at or datetime.utcnow()
                
                # Сохраняем сигнал
                db.execute(
                    text("""
                        INSERT INTO deal_intent_signal (
                            app_id, source, url, text, author, ts,
                            matched_keywords, intent_strength, extracted_steam_app_ids,
                            extracted_links, lang, title_guess, published_at, created_at
                        ) VALUES (
                            :app_id, 'youtube', :url, :text, :author, :ts,
                            CAST(:matched_keywords AS jsonb), :intent_strength, 
                            CAST(:extracted_app_ids AS integer[]),
                            CAST(:extracted_links AS jsonb), :lang, :title_guess, :ts, NOW()
                        )
                    """),
                    {
                        "app_id": app_id,
                        "url": video.url or '',
                        "text": full_text[:5000],  # Ограничиваем длину
                        "author": getattr(video, 'channel_name', None) or 'youtube',
                        "ts": ts,
                        "matched_keywords": matched_keywords,
                        "intent_strength": intent_strength,
                        "extracted_app_ids": extracted_app_ids,
                        "extracted_links": extracted_links,
                        "lang": lang,
                        "title_guess": title_guess
                    }
                )
                
                db.commit()
                
                results["signals_saved"] += 1
                if app_id:
                    results["signals_with_app_id"] += 1
                
                logger.debug(f"Saved YouTube signal: {video.url}, app_id={app_id}, keywords={len(matched_keywords)}")
                
            except Exception as e:
                error_msg = f"Error processing video {video.url or 'unknown'}: {str(e)}"
                logger.error(error_msg, exc_info=True)
                results["errors"].append(error_msg)
                db.rollback()
                continue
        
        logger.info(
            f"YouTube Deal Intent Signals: processed={results['videos_processed']}, "
            f"saved={results['signals_saved']}, with_app_id={results['signals_with_app_id']}, "
            f"skipped={results['signals_skipped']}"
        )
        
        return results
        
    except Exception as e:
        logger.error(f"YouTube Deal Intent Signals collection failed: {e}", exc_info=True)
        results["status"] = "error"
        results["errors"].append(str(e))
        return results
        
    finally:
        db.close()
