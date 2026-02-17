"""
Discord Signals Collector for Publisher Hunt v1
Собирает сигналы из Discord серверов для поиска проектов, ищущих издателя.
"""
import os
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Set
from sqlalchemy import text

from apps.worker.celery_app import celery_app
from apps.db.session import get_db_session
from apps.worker.integrations.discord_scraper import DiscordScraper
from apps.worker.config.discord_publisher_hunt_config import (
    DISCORD_SERVERS,
    CHANNEL_TYPE_WEIGHTS,
    AUTHOR_ROLE_WEIGHTS
)

logger = logging.getLogger(__name__)


def get_discord_token() -> str:
    """Получает токен Discord из переменной окружения."""
    return os.getenv("DISCORD_BOT_TOKEN", "").strip()


def is_discord_token_configured(token: str) -> bool:
    """
    Проверяет, что токен реально настроен (не placeholder, не пустой, достаточной длины).
    
    Правила валидации:
    - Токен НЕвалидный, если:
      - пустой
      - содержит (case-insensitive): put_real, paste_real, your_real, token_here
      - длина < 50 символов
    
    Args:
        token: Токен для проверки
        
    Returns:
        True если токен валидный, False если placeholder/пустой/короткий
    """
    if not token or not token.strip():
        return False
    
    token_lower = token.lower().strip()
    
    # Проверка на запрещённые слова (case-insensitive)
    forbidden_patterns = [
        "put_real",
        "paste_real",
        "your_real",
        "token_here"
    ]
    
    for pattern in forbidden_patterns:
        if pattern in token_lower:
            return False
    
    # Минимальная длина реального токена (Discord bot tokens обычно >= 50 символов)
    if len(token) < 50:
        return False
    
    return True


def _selftest_token_validator():
    """Self-check для валидатора токена (не вызывается автоматически)."""
    test_cases = [
        ("", False, "empty"),
        ("   ", False, "whitespace"),
        ("PUT_REAL_TOKEN_HERE", False, "placeholder uppercase"),
        ("put_real_token_here", False, "placeholder lowercase"),
        ("PASTE_REAL_DISCORD_BOT_TOKEN_HERE", False, "paste placeholder"),
        ("paste_your_real_discord_bot_token_here", False, "paste_your placeholder"),
        ("PASTE_YOUR_REAL_DISCORD_BOT_TOKEN_HERE", False, "paste_your uppercase"),
        ("paste_something_token_here", False, "paste_*token pattern"),
        ("REAL_TOKEN", False, "real_token"),
        ("short", False, "too short"),
        ("a" * 49, False, "49 chars (too short)"),
        ("a" * 50, True, "50 chars (minimum)"),
        ("MTIzNDU2Nzg5MGFiY2RlZjEyMzQ1Njc4OTBhYmNkZWYxMjM0NTY3ODkwYWJjZGVm", True, "real token pattern"),
    ]
    
    passed = 0
    failed = 0
    
    for token, expected, description in test_cases:
        result = is_discord_token_configured(token)
        if result == expected:
            passed += 1
            print(f"✅ PASS: {description} -> {result}")
        else:
            failed += 1
            print(f"❌ FAIL: {description} -> expected {expected}, got {result}")
    
    print(f"\nTotal: {passed + failed}, Passed: {passed}, Failed: {failed}")
    return failed == 0


def get_channel_type_weight(channel_name: str) -> float:
    """Определяет вес канала по его названию."""
    channel_lower = channel_name.lower()
    for channel_type, weight in CHANNEL_TYPE_WEIGHTS.items():
        if channel_type in channel_lower:
            return weight
    return 0.5  # Default weight


def get_author_role_weight(author_info: Dict[str, Any]) -> float:
    """Определяет вес автора по его роли."""
    # В V1 упрощённая логика - можно расширить
    if author_info.get("bot", False):
        return 0.3  # Боты имеют низкий вес
    return AUTHOR_ROLE_WEIGHTS.get("member", 0.6)  # Default


@celery_app.task(name="collect_discord_signals_task")
def collect_discord_signals_task(days: int = 1) -> Dict[str, Any]:
    """
    Собирает Deal Intent Signals из Discord (Publisher Hunt v1).
    
    Args:
        days: Количество дней назад для поиска сообщений
        
    Returns:
        {
            "status": "ok",
            "messages_scanned": int,
            "messages_matched": int,
            "signals_saved": int,
            "app_ids_discovered": int,
            "rate_limited": bool
        }
    """
    db = get_db_session()
    results = {
        "status": "ok",
        "messages_scanned": 0,
        "messages_matched": 0,
        "signals_saved": 0,
        "app_ids_discovered": 0,
        "rate_limited": False,
        "errors": []
    }
    
    discovered_app_ids: Set[int] = set()
    
    try:
        # Проверяем токен
        discord_token = get_discord_token()
        if not is_discord_token_configured(discord_token):
            logger.warning("DISCORD_BOT_TOKEN not configured or invalid, skipping Discord signal collection")
            results["status"] = "skipped"
            results["errors"].append("DISCORD_BOT_TOKEN not configured. See docs/DISCORD_BOT_TOKEN_SETUP.md")
            return results
        
        scraper = DiscordScraper(bot_token=discord_token)
        
        # Проходим по всем серверам из конфига
        for server_id, server_info in DISCORD_SERVERS.items():
            server_name = server_info.get("name", server_id)
            channel_names = server_info.get("channel_names", [])
            
            logger.info(f"Processing Discord server: {server_name} ({server_id})")
            
            # Получаем каналы сервера
            channels = scraper.get_server_channels(server_id)
            
            # Фильтруем каналы по названиям из конфига
            target_channels = []
            for channel in channels:
                channel_name = channel.get("name", "")
                # Проверяем, есть ли канал в списке целевых
                for target_name in channel_names:
                    if target_name.replace("#", "").lower() in channel_name.lower():
                        target_channels.append(channel)
                        break
            
            if not target_channels:
                logger.info(f"No target channels found for server {server_name}")
                continue
            
            # Обрабатываем каждый канал
            for channel in target_channels:
                channel_id = channel.get("id")
                channel_name = channel.get("name", "")
                
                try:
                    # Получаем сообщения из канала
                    messages = scraper.get_channel_messages(
                        server_id=server_id,
                        channel_id=channel_id,
                        days=days,
                        limit=100
                    )
                    
                    results["messages_scanned"] += len(messages)
                    
                    # Обрабатываем каждое сообщение
                    for message in messages:
                        content = message.get("content", "")
                        if not content:
                            continue
                        
                        # Проверяем на publisher-seeking
                        seeking_result = scraper.check_publisher_seeking(content)
                        
                        if not seeking_result["is_seeking"]:
                            continue
                        
                        results["messages_matched"] += 1
                        
                        # Извлекаем Steam app_id
                        app_id = scraper.extract_steam_app_id(content)
                        
                        # Вычисляем confidence
                        channel_weight = get_channel_type_weight(channel_name)
                        author_weight = get_author_role_weight(message.get("author", {}))
                        phrase_count = len(seeking_result["publisher_phrases"])
                        
                        confidence = (
                            seeking_result["confidence"] * 0.4 +
                            channel_weight * 0.3 +
                            author_weight * 0.2 +
                            min(phrase_count * 0.1, 0.1)
                        )
                        
                        # Publisher intent score = 1.0 (базовый для Discord сигналов)
                        publisher_intent_score = 1.0
                        
                        # Извлекаем первую найденную publisher phrase
                        publisher_phrase = seeking_result["publisher_phrases"][0] if seeking_result["publisher_phrases"] else None
                        
                        # Формируем URL сообщения
                        message_url = f"https://discord.com/channels/{server_id}/{channel_id}/{message.get('id')}"
                        
                        # Парсим timestamp
                        try:
                            published_at = datetime.fromisoformat(
                                message.get("timestamp", "").replace("Z", "+00:00")
                            )
                        except:
                            published_at = datetime.utcnow()
                        
                        # Сохраняем сигнал
                        try:
                            # Проверяем существование (idempotency)
                            existing = db.execute(
                                text("SELECT id FROM deal_intent_signal WHERE source = 'discord' AND url = :url"),
                                {"url": message_url}
                            ).scalar()
                            
                            if existing:
                                continue
                            
                            # Вставляем сигнал
                            db.execute(
                                text("""
                                    INSERT INTO deal_intent_signal (
                                        app_id, source, url, text, signal_type, published_at, created_at,
                                        source_subtype, channel_name, server_name, publisher_intent_score, publisher_phrase, confidence
                                    ) VALUES (
                                        :app_id, 'discord', :url, :text, 'behavioral_intent', :published_at, NOW(),
                                        'discord', :channel_name, :server_name, :publisher_intent_score, :publisher_phrase, :confidence
                                    )
                                """),
                                {
                                    "app_id": app_id,
                                    "url": message_url,
                                    "text": content[:5000],  # Ограничиваем длину
                                    "published_at": published_at,
                                    "channel_name": channel_name,
                                    "server_name": server_name,
                                    "publisher_intent_score": publisher_intent_score,
                                    "publisher_phrase": publisher_phrase,
                                    "confidence": confidence
                                }
                            )
                            
                            db.commit()
                            
                            results["signals_saved"] += 1
                            if app_id:
                                discovered_app_ids.add(app_id)
                                results["app_ids_discovered"] += 1
                            
                            logger.debug(f"Saved Discord signal: {message_url}, app_id={app_id}")
                            
                        except Exception as insert_error:
                            logger.warning(f"Error inserting Discord signal: {insert_error}")
                            db.rollback()
                            continue
                        
                        time.sleep(0.5)  # Rate limiting между сообщениями
                    
                    time.sleep(1)  # Rate limiting между каналами
                    
                except Exception as channel_error:
                    error_msg = f"Error processing channel {channel_name}: {channel_error}"
                    logger.error(error_msg, exc_info=True)
                    results["errors"].append(error_msg)
                    continue
            
            time.sleep(2)  # Rate limiting между серверами
        
        results["app_ids_discovered"] = len(discovered_app_ids)
        
        logger.info(
            f"Discord Publisher Hunt Signals: scanned={results['messages_scanned']}, "
            f"matched={results['messages_matched']}, saved={results['signals_saved']}, "
            f"app_ids={results['app_ids_discovered']}"
        )
        
        return results
        
    except Exception as e:
        logger.error(f"Discord signal collection failed: {e}", exc_info=True)
        results["status"] = "error"
        results["errors"].append(str(e))
        return results
        
    finally:
        db.close()
