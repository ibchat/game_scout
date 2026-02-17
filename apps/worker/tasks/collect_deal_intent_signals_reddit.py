"""
Reddit Collector for Deal Intent Signals v3.2
Собирает посты из сабреддитов, матчит keywords, извлекает Steam app_id.
"""
import re
import json
import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Set
from sqlalchemy import text

from apps.worker.celery_app import celery_app
from apps.db.session import get_db_session
from apps.worker.integrations.reddit_scraper import RedditScraper
from apps.worker.config.behavioral_intent_keywords import BEHAVIORAL_KEYWORDS

logger = logging.getLogger(__name__)

# Сабреддиты для Deal Intent (Vector A EXEC v1)
# Расширенный список согласно TZ_SIGNAL_INGESTION_VECTOR_A_EXEC_V1.md п.3.A1
DEAL_INTENT_SUBREDDITS = [
    'Steam',           # Новый
    'pcgaming',        # Новый
    'SteamDeck',       # Уже был
    'Games',           # Новый
    'IndieGaming',     # Уже был
    'IndieDev',        # Уже был
    'GameDeals',       # Новый
    'Gaming',          # Новый
    'gamedev',         # Уже был
    'GameDevClassifieds',  # Уже был
    'playmygame',      # Уже был
    'INATrade'         # Уже был
]


def extract_steam_app_ids(text_content: str, url: str = None) -> List[int]:
    """
    Извлекает Steam app_id из текста и URL.
    Согласно TZ_SIGNAL_INGESTION_VECTOR_A_EXEC_V1.md п.3.A1.4.
    
    Разрешённые паттерны:
    - store.steampowered.com/app/<id>
    - steamcommunity.com/app/<id>
    - "steam app id" из текста, только если рядом есть "steam" (защита от мусора)
    
    Если app_id не найден → возвращает пустой список (сигнал отбрасывается).
    """
    app_ids = set()
    
    # Объединяем текст и URL для поиска
    search_text = f"{text_content} {url or ''}"
    
    # Паттерн 1: store.steampowered.com/app/123456 (разрешён)
    pattern1 = r'store\.steampowered\.com/app/(\d+)'
    matches = re.findall(pattern1, search_text, re.IGNORECASE)
    for match in matches:
        try:
            app_ids.add(int(match))
        except ValueError:
            pass
    
    # Паттерн 2: steamcommunity.com/app/123456 (разрешён)
    pattern2 = r'steamcommunity\.com/app/(\d+)'
    matches = re.findall(pattern2, search_text, re.IGNORECASE)
    for match in matches:
        try:
            app_ids.add(int(match))
        except ValueError:
            pass
    
    # Паттерн 3: "steam app id" из текста, только если рядом есть "steam" (Vector A EXEC v1)
    # Ищем паттерн типа "steam app id 123456" или "app id 123456 steam"
    # Защита от мусора: должно быть слово "steam" в пределах 50 символов от числа
    text_lower = search_text.lower()
    # Ищем числа, которые могут быть app_id (обычно 6-7 цифр)
    potential_ids = re.findall(r'\b(\d{5,8})\b', search_text)
    for potential_id in potential_ids:
        # Проверяем, есть ли "steam" рядом (в пределах 50 символов)
        idx = text_lower.find(potential_id)
        if idx >= 0:
            context_start = max(0, idx - 50)
            context_end = min(len(text_lower), idx + len(potential_id) + 50)
            context = text_lower[context_start:context_end]
            if 'steam' in context:
                try:
                    app_ids.add(int(potential_id))
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
def collect_deal_intent_signals_reddit_task(days: int = 90, limit_per_sub: int = 500, include_comments: bool = False, max_comments_per_post: int = None) -> Dict[str, Any]:
    """
    Собирает Deal Intent Signals из Reddit (Vector A EXEC v1).
    
    Args:
        days: Количество дней назад для поиска постов (Vector A: минимум 90, лучше 180)
        limit_per_sub: Максимум постов на сабреддит (Vector A: минимум 500, лучше 1000)
        include_comments: Собирать ли комментарии из постов (Vector A A2)
    
    Returns:
        {
            "status": "ok",
            "posts_fetched": int,
            "comments_fetched": int,
            "signals_saved": int,
            "signals_with_app_id": int,
            "signals_skipped": int,
            "errors": List[str]
        }
    """
    db = get_db_session()
    results = {
        "status": "ok",
        "signals_fetched": 0,  # A1: Общее количество сигналов (посты + комментарии) до фильтрации
        "signals_saved": 0,  # Количество сохраненных сигналов
        "apps_discovered": 0,  # A1: Количество уникальных app_id, обнаруженных в сигналах
        "posts_fetched": 0,
        "comments_fetched": 0,
        "comments_scraped": 0,  # Total comments from scraper (before filters)
        "comments_kept": 0,  # Comments that passed filters and were saved
        "signals_with_app_id": 0,
        "signals_skipped": 0,
        "rate_limited": False,  # B3: Флаг rate limiting
        "errors": [],
        # Tracing metrics
        "tracing": {
            "posts_processed": 0,
            "posts_with_app_id": 0,
            "posts_called_get_comments": 0,
            "comments_total_from_scraper": 0,
            "comments_filtered_no_keywords": 0,
            "comments_filtered_no_app_id": 0,
            "comments_insert_attempted": 0,
            "comments_insert_succeeded": 0
        }
    }
    
    try:
        scraper = RedditScraper()
        
        # Получаем новые посты из сабреддитов
        posts = scraper.get_new_posts(DEAL_INTENT_SUBREDDITS, days=days, limit_per_sub=limit_per_sub)
        results["posts_fetched"] = len(posts)
        results["signals_fetched"] = len(posts)  # A1: Начальное значение (посты)
        
        discovered_app_ids = set()  # A1: Для подсчета уникальных app_id
        
        logger.info(f"Fetched {len(posts)} Reddit posts for Deal Intent Signals")
        
        for post in posts:
            try:
                results["tracing"]["posts_processed"] += 1
                
                # Vector A A2: Если include_comments=True, собираем комментарии ДО фильтрации поста
                # Это позволяет собирать комментарии даже если сам пост не прошел фильтры
                if include_comments:
                    post_permalink = post.get('url', '')
                    if not post_permalink:
                        # Fallback: construct from post_id and subreddit
                        if post.get('post_id') and post.get('subreddit'):
                            post_permalink = post.get('post_id', '')
                        else:
                            post_permalink = None
                    
                    if post_permalink:
                        try:
                            results["tracing"]["posts_called_get_comments"] += 1
                            
                            # B1: Ограничить комментарии в daily режиме
                            comments_limit = max_comments_per_post if max_comments_per_post else 20
                            comments = scraper.get_post_comments(
                                post_permalink,
                                post.get('subreddit', ''),
                                limit=comments_limit
                            )
                            
                            comments_count = len(comments)
                            results["comments_fetched"] += comments_count
                            results["comments_scraped"] += comments_count
                            results["signals_fetched"] += comments_count  # A1: Добавляем комментарии к общему счету
                            results["tracing"]["comments_total_from_scraper"] += comments_count
                            
                            logger.debug(f"Fetched {comments_count} comments for post {post.get('post_id', 'unknown')}")
                            
                            # Обрабатываем комментарии аналогично постам
                            for comment in comments:
                                comment_text = comment.get('text', '') or comment.get('body', '')
                                comment_url = comment.get('url', '') or comment.get('permalink', '')
                                
                                # Матчим keywords в комментарии
                                comment_keyword_result = match_keywords(comment_text)
                                comment_matched_keywords = comment_keyword_result["matched_keywords"]
                                comment_intent_strength = comment_keyword_result["intent_strength"]
                                
                                # Если нет keywords - пропускаем
                                if not comment_matched_keywords or comment_intent_strength == 0:
                                    results["tracing"]["comments_filtered_no_keywords"] += 1
                                    continue
                                
                                # Извлекаем Steam app_id из комментария
                                comment_app_ids = extract_steam_app_ids(comment_text, comment_url)
                                
                                # Если app_id не найден - пропускаем
                                if not comment_app_ids:
                                    results["tracing"]["comments_filtered_no_app_id"] += 1
                                    continue
                                
                                comment_app_id = comment_app_ids[0]
                                comment_signal_type = "behavioral_intent" if comment_intent_strength >= 4 else "intent_keyword"
                                
                                # Парсим дату комментария
                                comment_ts = None
                                if comment.get('created_at'):
                                    try:
                                        comment_ts = datetime.fromisoformat(comment.get('created_at').replace('Z', '+00:00'))
                                    except:
                                        comment_ts = datetime.utcnow()
                                else:
                                    comment_ts = datetime.utcnow()
                                
                                # Вставляем сигнал из комментария
                                results["tracing"]["comments_insert_attempted"] += 1
                                
                                try:
                                    # Ensure comment_url is unique (use full permalink with comment id if available)
                                    if not comment_url or comment_url == post_url:
                                        # Fallback: use comment id to make URL unique
                                        comment_id = comment.get('id', '')
                                        if comment_id:
                                            comment_url = f"{post_url}#comment_{comment_id}"
                                        else:
                                            comment_url = f"{post_url}#comment_{results['tracing']['comments_insert_attempted']}"
                                    
                                    db.execute(
                                        text("""
                                            INSERT INTO deal_intent_signal (
                                                app_id, source, url, text, signal_type, published_at, created_at
                                            ) VALUES (
                                                :app_id, 'reddit', :url, :text, :signal_type, :published_at, NOW()
                                            )
                                            ON CONFLICT (source, url) DO NOTHING
                                        """),
                                        {
                                            "app_id": comment_app_id,
                                            "url": comment_url,
                                            "text": comment_text[:280][:5000],  # Обрезаем до 280, но не более 5000 для БД
                                            "signal_type": comment_signal_type,
                                            "published_at": comment_ts
                                        }
                                    )
                                    
                                    # Проверяем вставку
                                    comment_inserted = db.execute(
                                        text("SELECT id FROM deal_intent_signal WHERE source = 'reddit' AND url = :url"),
                                        {"url": comment_url}
                                    ).scalar()
                                    
                                    if comment_inserted:
                                        results["signals_saved"] += 1
                                        results["signals_with_app_id"] += 1
                                        results["comments_kept"] += 1
                                        discovered_app_ids.add(comment_app_id)  # A1: Добавляем app_id в множество
                                        results["tracing"]["comments_insert_succeeded"] += 1
                                        logger.debug(f"Saved comment signal: {comment_url}, app_id={comment_app_id}")
                                    
                                    db.commit()
                                    time.sleep(0.5)  # Меньшая задержка для комментариев
                                
                                except Exception as comment_error:
                                    if "unique constraint" in str(comment_error).lower() or "duplicate key" in str(comment_error).lower():
                                        db.rollback()
                                        continue
                                    else:
                                        logger.warning(f"Error inserting comment signal: {comment_error}")
                                        db.rollback()
                                        continue
                            
                        except Exception as comment_fetch_error:
                            logger.warning(f"Error fetching comments for post {post.get('post_id')}: {comment_fetch_error}")
                            # Не прерываем обработку поста из-за ошибки комментариев
                
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
                
                # Извлекаем Steam app_id (строго согласно ТЗ п.6)
                extracted_app_ids = extract_steam_app_ids(full_text, post_url)
                
                # Согласно ТЗ п.6: если app_id не найден → сигнал отбрасывается
                if not extracted_app_ids:
                    results["signals_skipped"] += 1
                    continue
                
                app_id = extracted_app_ids[0]
                results["tracing"]["posts_with_app_id"] += 1
                
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
                
                # Определяем signal_type согласно ТЗ п.5
                signal_type = "behavioral_intent" if intent_strength >= 4 else "intent_keyword"
                
                # Вставляем сигнал с идемпотентностью (ON CONFLICT)
                # Согласно TZ_SIGNAL_INGESTION_VECTOR_A_EXEC_V1.md п.3.A1.6
                # Используем только существующие колонки
                # Vector A: обрезаем text до 280 символов (или 5000 для совместимости)
                signal_text = full_text[:280] if len(full_text) > 280 else full_text
                
                try:
                    db.execute(
                        text("""
                            INSERT INTO deal_intent_signal (
                                app_id, source, url, text, signal_type, published_at, created_at
                            ) VALUES (
                                :app_id, 'reddit', :url, :text, :signal_type, :published_at, NOW()
                            )
                            ON CONFLICT (source, url) DO NOTHING
                        """),
                        {
                            "app_id": app_id,
                            "url": post_url,
                            "text": signal_text[:5000],  # Ограничиваем длину для БД
                            "signal_type": signal_type,
                            "published_at": ts
                        }
                    )
                    
                    # Проверяем, был ли вставлен сигнал (для подсчёта)
                    # ON CONFLICT DO NOTHING не возвращает количество вставленных строк
                    # Проверяем через SELECT после попытки вставки
                    inserted_check = db.execute(
                        text("SELECT id FROM deal_intent_signal WHERE source = 'reddit' AND url = :url"),
                        {"url": post_url}
                    ).scalar()
                    
                    if inserted_check:
                        results["signals_saved"] += 1
                        results["signals_with_app_id"] += 1
                        discovered_app_ids.add(app_id)  # A1: Добавляем app_id в множество
                        logger.debug(f"Saved Reddit signal: {post_url}, app_id={app_id}, keywords={len(matched_keywords)}")
                    else:
                        results["signals_skipped"] += 1
                    
                    db.commit()
                    
                    # Rate limiting согласно TZ_SIGNAL_INGESTION_VECTOR_A_EXEC_V1.md п.3.A1
                    time.sleep(1.5)  # Sleep 1-2 сек между постами
                    
                except Exception as insert_error:
                    # Если ON CONFLICT не поддерживается (unique index не применён), используем проверку
                    if "unique constraint" in str(insert_error).lower() or "duplicate key" in str(insert_error).lower():
                        results["signals_skipped"] += 1
                        db.rollback()
                        time.sleep(1.5)
                        continue
                    else:
                        raise
                
            except Exception as e:
                error_msg = f"Error processing post {post.get('url', 'unknown')}: {str(e)}"
                logger.error(error_msg, exc_info=True)
                results["errors"].append(error_msg)
                db.rollback()
                continue
        
        # A1: Подсчитываем уникальные app_id
        results["apps_discovered"] = len(discovered_app_ids)
        
        logger.info(
            f"Reddit Deal Intent Signals (Vector A): fetched={results['posts_fetched']} posts, "
            f"comments_scraped={results['comments_scraped']}, comments_kept={results['comments_kept']}, "
            f"saved={results['signals_saved']} signals, with_app_id={results['signals_with_app_id']}, "
            f"skipped={results['signals_skipped']}, apps_discovered={results['apps_discovered']}"
        )
        logger.info(
            f"Tracing: posts_processed={results['tracing']['posts_processed']}, "
            f"posts_with_app_id={results['tracing']['posts_with_app_id']}, "
            f"posts_called_get_comments={results['tracing']['posts_called_get_comments']}, "
            f"comments_total={results['tracing']['comments_total_from_scraper']}, "
            f"filtered_no_keywords={results['tracing']['comments_filtered_no_keywords']}, "
            f"filtered_no_app_id={results['tracing']['comments_filtered_no_app_id']}, "
            f"insert_attempted={results['tracing']['comments_insert_attempted']}, "
            f"insert_succeeded={results['tracing']['comments_insert_succeeded']}"
        )
        
        # A1: Гарантируем что все поля не null (даже если 0)
        if results.get("signals_fetched") is None:
            results["signals_fetched"] = 0
        if results.get("apps_discovered") is None:
            results["apps_discovered"] = 0
        
        return results
        
    except Exception as e:
        logger.error(f"Reddit Deal Intent Signals collection failed: {e}", exc_info=True)
        results["status"] = "error"
        results["errors"].append(str(e))
        # A2: Гарантируем что все поля не null даже при ошибке
        if results.get("signals_fetched") is None:
            results["signals_fetched"] = 0
        if results.get("apps_discovered") is None:
            results["apps_discovered"] = 0
        return results
        
    finally:
        db.close()
