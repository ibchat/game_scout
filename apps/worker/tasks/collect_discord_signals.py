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
def collect_discord_signals_task(
    days: int = 1,
    debug: bool = False,
    test_inject: bool = False,
    max_channels: int = 5
) -> Dict[str, Any]:
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
        "errors": [],
        "channels_visible": [],  # Для debug mode
        "channels_scanned": 0,
        "channels_ranked": [],  # Для debug mode: топ каналов с activity_score
        "sample_messages": [],  # Для debug mode: примеры сообщений
        "match_reasons": [],  # Для debug mode: почему не матчится
        "discord_api_status_codes": {},  # Для debug: статусы API по каналам
        "content_empty_reason_guess": "",  # Для debug: предположение о причине пустого content
        "non_system_messages_seen": 0,  # Для debug: количество не-системных сообщений
        "latest_non_system_message_id": None,  # Для debug: ID последнего не-системного сообщения
        "latest_non_system_message_preview": "",  # Для debug: preview последнего не-системного сообщения
        "latest_non_system_message_has_links": False,  # Для debug: есть ли ссылки в последнем сообщении
        "latest_non_system_message_urls": [],  # Для debug: URLs из последнего сообщения
        "action_required": ""  # Для debug: что нужно сделать пользователю
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
        
        # Test inject режим: создаем виртуальное сообщение для калибровки
        if test_inject:
            logger.info("Test inject mode: creating virtual test message")
            test_message_content = "Looking for publisher for our Steam game. Here is the page: https://store.steampowered.com/app/620/ Portal 2"
            
            # Проверяем на publisher-seeking
            seeking_result = scraper.check_publisher_seeking(test_message_content)
            app_id = scraper.extract_steam_app_id(test_message_content)
            
            logger.info(f"Test inject validation: is_seeking={seeking_result['is_seeking']}, app_id={app_id}, phrases={seeking_result.get('publisher_phrases', [])}")
            
            if seeking_result["is_seeking"] and app_id:
                try:
                    # Проверяем существование (idempotency)
                    test_url = "https://discord.com/channels/TEST/TEST/TEST_INJECT"
                    existing = db.execute(
                        text("SELECT id FROM deal_intent_signal WHERE source = 'discord' AND url = :url"),
                        {"url": test_url}
                    ).scalar()
                    
                    if not existing:
                        publisher_phrase = seeking_result["publisher_phrases"][0] if seeking_result["publisher_phrases"] else "looking for publisher"
                        confidence = seeking_result.get("confidence", 0.5)
                        
                        # Вставляем тестовый сигнал
                        db.execute(
                            text("""
                                INSERT INTO deal_intent_signal (
                                    app_id, source, url, text, signal_type, published_at, created_at,
                                    source_subtype, channel_name, server_name, publisher_intent_score, publisher_phrase, confidence
                                ) VALUES (
                                    :app_id, 'discord', :url, :text, 'behavioral_intent', NOW(), NOW(),
                                    'test_inject', 'TEST', 'TEST', :publisher_intent_score, :publisher_phrase, :confidence
                                )
                            """),
                            {
                                "app_id": app_id,
                                "url": test_url,
                                "text": test_message_content[:5000],
                                "published_at": datetime.utcnow(),
                                "channel_name": "TEST",
                                "server_name": "TEST",
                                "publisher_intent_score": 1.0,
                                "publisher_phrase": publisher_phrase,
                                "confidence": confidence
                            }
                        )
                        
                        db.commit()
                        results["signals_saved"] += 1
                        results["app_ids_discovered"] += 1
                        discovered_app_ids.add(app_id)
                        logger.info(f"Test inject: saved signal with app_id={app_id}")
                    else:
                        logger.info("Test inject: signal already exists (idempotency)")
                except Exception as inject_error:
                    logger.error(f"Test inject failed: {inject_error}", exc_info=True)
                    db.rollback()
                    results["errors"].append(f"Test inject failed: {inject_error}")
            else:
                logger.warning(f"Test inject: message did not match (is_seeking={seeking_result['is_seeking']}, app_id={app_id})")
                results["errors"].append("Test inject: message validation failed")
        
        # Проходим по всем серверам из конфига
        for server_id, server_info in DISCORD_SERVERS.items():
            server_name = server_info.get("name", server_id)
            channel_names = server_info.get("channel_names", [])
            
            logger.info(f"Processing Discord server: {server_name} ({server_id})")
            
            # Получаем каналы сервера
            channels = scraper.get_server_channels(server_id)
            
            if debug:
                # В debug mode сохраняем список всех видимых каналов
                for ch in channels[:50]:  # Ограничиваем до 50
                    results["channels_visible"].append({
                        "id": ch.get("id"),
                        "name": ch.get("name")
                    })
            
            # Фильтруем каналы по названиям из конфига (если указаны)
            # Если channel_names пустой - используем auto-pick TOP_K каналов
            target_channels = []
            if channel_names:
                # Режим с фильтрацией по названиям
                for channel in channels:
                    channel_name = channel.get("name", "")
                    # Проверяем, есть ли канал в списке целевых
                    for target_name in channel_names:
                        if target_name.replace("#", "").lower() in channel_name.lower():
                            target_channels.append(channel)
                            break
            else:
                # Auto-pick режим: выбираем TOP_K каналов по activity_score
                logger.info(f"Auto-picking top {max_channels} channels for server {server_name}")
                
                # Вычисляем activity_score для каждого канала
                channels_with_scores = []
                for channel in channels:
                    channel_id = channel.get("id")
                    channel_name = channel.get("name", "")
                    
                    activity_data = scraper.calculate_channel_activity_score(
                        channel_id=channel_id,
                        sample_size=10,
                        days=3
                    )
                    
                    score = activity_data.get("score", 0.0)
                    channels_with_scores.append({
                        **channel,
                        "activity_score": score,
                        "activity_data": activity_data
                    })
                    
                    if debug:
                        # Сохраняем в channels_ranked для debug (будет отсортирован позже)
                        results["channels_ranked"].append({
                            "id": channel_id,
                            "name": channel_name,
                            "activity_score": score,
                            "message_count": activity_data.get("message_count", 0),
                            "messages_with_links": activity_data.get("messages_with_links", 0),
                            "messages_with_keywords": activity_data.get("messages_with_keywords", 0)
                        })
                    
                    time.sleep(0.5)  # Rate limiting между проверками активности
                
                # Сортируем по activity_score (по убыванию) и берем TOP_K
                channels_with_scores.sort(key=lambda x: x.get("activity_score", 0.0), reverse=True)
                target_channels = channels_with_scores[:max_channels]
                
                # В debug mode: сортируем и ограничиваем channels_ranked до top 10
                if debug:
                    results["channels_ranked"].sort(key=lambda x: x.get("activity_score", 0.0), reverse=True)
                    results["channels_ranked"] = results["channels_ranked"][:10]
                
                logger.info(
                    f"Selected {len(target_channels)} channels for server {server_name}: "
                    f"{[ch.get('name') for ch in target_channels]}"
                )
            
            if not target_channels:
                logger.info(f"No target channels found for server {server_name}")
                results["errors"].append(f"No accessible channels found for server {server_name}")
                if debug:
                    results["match_reasons"].append(f"No channels available or accessible on server {server_name}")
                continue
            
            # Обрабатываем каждый канал
            for channel in target_channels:
                channel_id = channel.get("id")
                channel_name = channel.get("name", "")
                
                # Получаем сообщения из канала
                # Проверяем статус через прямой запрос для диагностики
                api_status = None
                messages = []
                
                try:
                    # Прямой запрос для получения статуса
                    import requests
                    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
                    headers = scraper.headers
                    test_response = requests.get(url, headers=headers, params={"limit": 1}, timeout=10)
                    api_status = test_response.status_code
                    
                    if api_status == 200:
                        # Если статус 200, получаем сообщения через обычный метод
                        messages = scraper.get_channel_messages(
                            server_id=server_id,
                            channel_id=channel_id,
                            days=days,
                            limit=100
                        )
                    else:
                        # Сохраняем статус для debug, но не падаем
                        messages = []
                except Exception as e:
                    logger.warning(f"Error checking channel {channel_name} ({channel_id}): {e}")
                    api_status = "error"
                    messages = []
                
                # Сохраняем статус для debug
                if debug:
                    results["discord_api_status_codes"][channel_id] = api_status
                
                # Если вернулся пустой список из-за 403/404 - пропускаем канал
                if not messages:
                    logger.warning(f"No messages read from channel {channel_name} ({channel_id}) - may be inaccessible (status: {api_status})")
                    results["errors"].append(f"Cannot read channel {channel_name} ({channel_id}) - status: {api_status}")
                    continue
                
                results["messages_scanned"] += len(messages)
                results["channels_scanned"] += 1
                
                # Диагностика: определяем причину пустого content
                if debug and len(messages) > 0:
                    all_content_empty = all(len(msg.get("content", "")) == 0 for msg in messages)
                    all_embeds_empty = all(len(msg.get("embeds", [])) == 0 for msg in messages)
                    all_attachments_empty = all(len(msg.get("attachments", [])) == 0 for msg in messages)
                    
                    if all_content_empty and all_embeds_empty and all_attachments_empty:
                        # Сообщения есть, но все пустые - очень странно
                        if api_status == 403:
                            results["content_empty_reason_guess"] = "missing_channel_permissions"
                        else:
                            results["content_empty_reason_guess"] = "webhook/system_message_only"
                    elif all_content_empty and not (all_embeds_empty and all_attachments_empty):
                        # Content пустой, но есть embeds/attachments
                        results["content_empty_reason_guess"] = "no_text_only_embeds"
                    elif all_content_empty:
                        # Content пустой, но embeds/attachments тоже пустые - вероятно Message Content Intent
                        results["content_empty_reason_guess"] = "missing_message_content_intent"
                    elif len(messages) == 0:
                        results["content_empty_reason_guess"] = "no_messages_in_range"
                    else:
                        results["content_empty_reason_guess"] = "content_available"
                
                # Для debug mode: сохраняем sample сообщений (первые 3)
                if debug and len(results["sample_messages"]) < 3:
                    for msg in messages[:3]:
                        # Извлекаем полный текст из сообщения
                        extracted_text = scraper.extract_text_from_message(msg)
                        extracted_urls = scraper.extract_urls(extracted_text)
                        steam_app_ids = scraper.extract_steam_app_ids(extracted_text)
                        
                        # Диагностические поля
                        content = msg.get("content", "")
                        embeds = msg.get("embeds", [])
                        attachments = msg.get("attachments", [])
                        
                        # Preview из extracted_text (обрезаем до 200)
                        text_preview = extracted_text[:200] if extracted_text else ""
                        
                        # Embed previews (первые 1-2)
                        embed_previews = []
                        for embed in embeds[:2]:
                            embed_previews.append({
                                "title": embed.get("title", "")[:50],
                                "description_len": len(embed.get("description", "")),
                                "url": embed.get("url", "")
                            })
                        
                        # Raw message sample (обрезанный для debug)
                        raw_msg_sample = {
                            "id": str(msg.get("id", ""))[:50],
                            "type": msg.get("type"),
                            "content": content[:200] if content else "",
                            "content_len": len(content),
                            "embeds_count": len(embeds),
                            "attachments_count": len(attachments),
                            "author": {
                                "username": str(msg.get("author", {}).get("username", ""))[:50],
                                "bot": msg.get("author", {}).get("bot", False)
                            }
                        }
                        
                        results["sample_messages"].append({
                            "channel": channel_name,
                            "content_len": len(content),
                            "content_preview": content[:120] if content else "",
                            "embed_count": len(embeds),
                            "attachment_count": len(attachments),
                            "embed_previews": embed_previews,
                            "extracted_text_preview": text_preview,
                            "extracted_text_len": len(extracted_text),
                            "extracted_urls": extracted_urls[:5],  # Первые 5 URL
                            "steam_app_ids_extracted": steam_app_ids,
                            "has_links": len(extracted_urls) > 0,
                            "raw_message_sample": raw_msg_sample,
                            "preview": text_preview  # Для обратной совместимости
                        })
                
                # Обрабатываем каждое сообщение
                try:
                    # Отслеживаем последнее не-системное сообщение для debug
                    latest_non_system_msg = None
                    non_system_count = 0
                    
                    for message in messages:
                        # Пропускаем системные сообщения (type != 0)
                        msg_type = message.get("type", 0)
                        if msg_type != 0:
                            # Системное сообщение - пропускаем при матчинге, но считаем в scanned
                            if debug and len(results["match_reasons"]) < 10:
                                results["match_reasons"].append(f"skipped: system_message_type={msg_type}")
                            continue
                        
                        # Не-системное сообщение
                        non_system_count += 1
                        if not latest_non_system_msg:
                            latest_non_system_msg = message
                        
                        # Извлекаем полный текст из сообщения (content + embeds + attachments)
                        extracted_text = scraper.extract_text_from_message(message)
                        if not extracted_text:
                            continue
                        
                        # Извлекаем URL
                        extracted_urls = scraper.extract_urls(extracted_text)
                        
                        # Проверяем на publisher-seeking (по полному тексту)
                        seeking_result = scraper.check_publisher_seeking(extracted_text)
                        
                        if not seeking_result["is_seeking"]:
                            # Для debug mode: собираем причины, почему не матчится
                            if debug and len(results["match_reasons"]) < 5:
                                reason = "no keywords found"
                                if seeking_result.get("negative_phrases"):
                                    reason = f"negative phrase found: {seeking_result['negative_phrases'][0]}"
                                elif not seeking_result.get("publisher_phrases"):
                                    reason = "no publisher-seeking phrases"
                                results["match_reasons"].append(reason)
                            continue
                        
                        # Для debug mode: сохраняем matched_phrases
                        if debug:
                            matched_phrases = seeking_result.get("matched_phrases", [])
                            if matched_phrases and len(results["match_reasons"]) < 5:
                                results["match_reasons"].append(f"matched: {', '.join(matched_phrases)}")
                        
                        results["messages_matched"] += 1
                        
                        # Извлекаем Steam app_id из полного текста
                        app_id = scraper.extract_steam_app_id(extracted_text)
                        
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
                                    "text": extracted_text[:5000],  # Ограничиваем длину (полный текст)
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
                    
                    # Сохраняем информацию о последнем не-системном сообщении для debug
                    if debug:
                        results["non_system_messages_seen"] = results.get("non_system_messages_seen", 0) + non_system_count
                        if latest_non_system_msg:
                            extracted_text_latest = scraper.extract_text_from_message(latest_non_system_msg)
                            extracted_urls_latest = scraper.extract_urls(extracted_text_latest)
                            
                            results["latest_non_system_message_id"] = latest_non_system_msg.get("id")
                            results["latest_non_system_message_preview"] = extracted_text_latest[:80] if extracted_text_latest else ""
                            results["latest_non_system_message_has_links"] = len(extracted_urls_latest) > 0
                            results["latest_non_system_message_urls"] = extracted_urls_latest[:5]
                    
                    time.sleep(1)  # Rate limiting между каналами
                    
                except Exception as channel_error:
                    error_msg = f"Error processing channel {channel_name}: {channel_error}"
                    logger.error(error_msg, exc_info=True)
                    results["errors"].append(error_msg)
                    continue
            
            time.sleep(2)  # Rate limiting между серверами
        
        results["app_ids_discovered"] = len(discovered_app_ids)
        
        # Определяем action_required для debug
        if debug:
            if results["non_system_messages_seen"] == 0:
                results["action_required"] = "send_any_text_message_to_channel"
            else:
                results["action_required"] = "none"
        
        logger.info(
            f"Discord Publisher Hunt Signals: scanned={results['messages_scanned']}, "
            f"matched={results['messages_matched']}, saved={results['signals_saved']}, "
            f"app_ids={results['app_ids_discovered']}, non_system={results.get('non_system_messages_seen', 0)}"
        )
        
        return results
        
    except Exception as e:
        logger.error(f"Discord signal collection failed: {e}", exc_info=True)
        results["status"] = "error"
        results["errors"].append(str(e))
        return results
        
    finally:
        db.close()
