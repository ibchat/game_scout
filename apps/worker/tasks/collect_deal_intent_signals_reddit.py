"""
Reddit Collector for Deal Intent Signals v3.2
Собирает посты из сабреддитов, матчит keywords, извлекает Steam app_id.
"""
import re
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Set
from sqlalchemy import text

from apps.worker.celery_app import celery_app
from apps.db.session import get_db_session
from apps.worker.integrations.reddit_scraper import RedditScraper
from apps.worker.config.behavioral_intent_keywords import BEHAVIORAL_KEYWORDS

logger = logging.getLogger(__name__)

# Сабреддиты для Deal Intent
DEAL_INTENT_SUBREDDITS = [
    'gamedev',
    'IndieDev',
    'playmygame',
    'DestroyMyGame',
    'INATeam',
    'IndieGaming',
    'GameDevClassifieds'
]


def extract_steam_app_ids(text_content: str, url: str = None) -> List[int]:
    """
    Извлекает Steam app_id из текста и URL.
    Ищет паттерны:
    - store.steampowered.com/app/<id>
    - steampowered.com/app/<id>
    - /app/<id>/
    """
    app_ids = set()
    
    # Объединяем текст и URL для поиска
    search_text = f"{text_content} {url or ''}"
    
    # Паттерн 1: store.steampowered.com/app/123456
    pattern1 = r'store\.steampowered\.com/app/(\d+)'
    matches = re.findall(pattern1, search_text, re.IGNORECASE)
    for match in matches:
        try:
            app_ids.add(int(match))
        except ValueError:
            pass
    
    # Паттерн 2: steampowered.com/app/123456
    pattern2 = r'steampowered\.com/app/(\d+)'
    matches = re.findall(pattern2, search_text, re.IGNORECASE)
    for match in matches:
        try:
            app_ids.add(int(match))
        except ValueError:
            pass
    
    # Паттерн 3: /app/123456/ (в URL или тексте)
    pattern3 = r'/app/(\d+)/?'
    matches = re.findall(pattern3, search_text, re.IGNORECASE)
    for match in matches:
        try:
            app_ids.add(int(match))
        except ValueError:
            pass
    
    return list(app_ids)


def match_keywords(text_content: str) -> Dict[str, Any]:
    """
    Матчит keywords в тексте и возвращает найденные ключи с их intent_strength.
    """
    text_lower = text_content.lower()
    matched = {}
    max_strength = 0
    
    for keyword, strength in BEHAVIORAL_KEYWORDS.items():
        if keyword.lower() in text_lower:
            matched[keyword] = strength
            max_strength = max(max_strength, strength)
    
    return {
        "matched_keywords": list(matched.keys()),
        "intent_strength": max_strength if matched else 0,
        "keyword_strengths": matched
    }


def detect_language(text_content: str) -> str:
    """
    Простое определение языка (en/ru).
    MVP: считаем русским если есть кириллица.
    """
    if re.search(r'[А-Яа-яЁё]', text_content):
        return 'ru'
    return 'en'


def extract_links(text_content: str, url: str = None) -> Dict[str, Any]:
    """
    Извлекает ссылки из текста (steam, discord, website, pitch deck).
    """
    links = {
        "steam": [],
        "discord": [],
        "website": [],
        "pitch": []
    }
    
    search_text = f"{text_content} {url or ''}"
    
    # Steam links
    steam_pattern = r'https?://(?:store\.)?steampowered\.com/app/(\d+)/?'
    steam_matches = re.findall(steam_pattern, search_text, re.IGNORECASE)
    links["steam"] = [f"https://store.steampowered.com/app/{m}/" for m in steam_matches]
    
    # Discord links
    discord_pattern = r'https?://(?:discord\.(?:gg|com|io)/[a-zA-Z0-9]+)'
    discord_matches = re.findall(discord_pattern, search_text, re.IGNORECASE)
    links["discord"] = list(set(discord_matches))
    
    # Website links (не steam, не discord)
    website_pattern = r'https?://(?!store\.steampowered|steampowered|discord\.)[^\s<>"\'\)]+'
    website_matches = re.findall(website_pattern, search_text, re.IGNORECASE)
    # Фильтруем известные домены
    excluded_domains = ['reddit.com', 'youtube.com', 'twitter.com', 'x.com']
    links["website"] = [
        m for m in website_matches 
        if not any(domain in m.lower() for domain in excluded_domains)
    ][:5]  # Максимум 5 ссылок
    
    # Pitch deck links (google drive, dropbox, notion и т.п.)
    pitch_pattern = r'https?://(?:drive\.google\.com|dropbox\.com|notion\.so|docs\.google\.com)[^\s<>"\'\)]+'
    pitch_matches = re.findall(pitch_pattern, search_text, re.IGNORECASE)
    links["pitch"] = list(set(pitch_matches))
    
    return links


@celery_app.task(name="apps.worker.tasks.collect_deal_intent_signals_reddit.collect_deal_intent_signals_reddit_task")
def collect_deal_intent_signals_reddit_task(days: int = 14, limit_per_sub: int = 25) -> Dict[str, Any]:
    """
    Собирает Deal Intent Signals из Reddit.
    
    Args:
        days: Количество дней назад для поиска постов (по умолчанию 14)
        limit_per_sub: Максимум постов на сабреддит (по умолчанию 25)
    
    Returns:
        {
            "status": "ok",
            "posts_fetched": int,
            "signals_saved": int,
            "signals_with_app_id": int,
            "errors": List[str]
        }
    """
    db = get_db_session()
    results = {
        "status": "ok",
        "posts_fetched": 0,
        "signals_saved": 0,
        "signals_with_app_id": 0,
        "signals_skipped": 0,
        "errors": []
    }
    
    try:
        scraper = RedditScraper()
        
        # Получаем новые посты из сабреддитов
        posts = scraper.get_new_posts(DEAL_INTENT_SUBREDDITS, days=days, limit_per_sub=limit_per_sub)
        results["posts_fetched"] = len(posts)
        
        logger.info(f"Fetched {len(posts)} Reddit posts for Deal Intent Signals")
        
        for post in posts:
            try:
                # Объединяем title и text для анализа
                full_text = f"{post.get('title', '')} {post.get('text', '')}"
                post_url = post.get('url', '')
                
                # Матчим keywords
                keyword_result = match_keywords(full_text)
                matched_keywords = keyword_result["matched_keywords"]
                intent_strength = keyword_result["intent_strength"]
                
                # Если нет keywords - пропускаем
                if not matched_keywords or intent_strength == 0:
                    results["signals_skipped"] += 1
                    continue
                
                # Извлекаем Steam app_id
                extracted_app_ids = extract_steam_app_ids(full_text, post_url)
                
                # Извлекаем ссылки
                extracted_links = extract_links(full_text, post_url)
                
                # Определяем язык
                lang = detect_language(full_text)
                
                # Парсим дату
                created_at_str = post.get('created_at', '')
                ts = None
                if created_at_str:
                    try:
                        ts = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                    except:
                        ts = datetime.utcnow()
                else:
                    ts = datetime.utcnow()
                
                # Проверяем, не существует ли уже такой сигнал (по source + url)
                existing_check = db.execute(
                    text("SELECT id FROM deal_intent_signal WHERE source = 'reddit' AND url = :url"),
                    {"url": post_url}
                ).scalar()
                
                if existing_check:
                    results["signals_skipped"] += 1
                    continue
                
                # Определяем app_id (если нашли один) или title_guess
                app_id = extracted_app_ids[0] if extracted_app_ids else None
                title_guess = post.get('title', '')[:200] if not app_id else None
                
                # Сохраняем сигнал
                db.execute(
                    text("""
                        INSERT INTO deal_intent_signal (
                            app_id, source, url, text, author, ts,
                            matched_keywords, intent_strength, extracted_steam_app_ids,
                            extracted_links, lang, title_guess, published_at, created_at
                        ) VALUES (
                            :app_id, 'reddit', :url, :text, :author, :ts,
                            CAST(:matched_keywords AS jsonb), :intent_strength, 
                            CAST(:extracted_app_ids AS integer[]),
                            CAST(:extracted_links AS jsonb), :lang, :title_guess, :ts, NOW()
                        )
                    """),
                    {
                        "app_id": app_id,
                        "url": post_url,
                        "text": full_text[:5000],  # Ограничиваем длину
                        "author": post.get('author', '')[:200],
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
                
                logger.debug(f"Saved Reddit signal: {post_url}, app_id={app_id}, keywords={len(matched_keywords)}")
                
            except Exception as e:
                error_msg = f"Error processing post {post.get('url', 'unknown')}: {str(e)}"
                logger.error(error_msg, exc_info=True)
                results["errors"].append(error_msg)
                db.rollback()
                continue
        
        logger.info(
            f"Reddit Deal Intent Signals: fetched={results['posts_fetched']}, "
            f"saved={results['signals_saved']}, with_app_id={results['signals_with_app_id']}, "
            f"skipped={results['signals_skipped']}"
        )
        
        return results
        
    except Exception as e:
        logger.error(f"Reddit Deal Intent Signals collection failed: {e}", exc_info=True)
        results["status"] = "error"
        results["errors"].append(str(e))
        return results
        
    finally:
        db.close()
