"""
Discord Scraper for Publisher Hunt v1
Собирает сообщения из Discord серверов для поиска проектов, ищущих издателя.
V1: Без Discord SDK, использует HTTP API напрямую (требует bot token).
"""
import requests
import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import re

from apps.worker.config.discord_publisher_hunt_config import (
    PUBLISHER_SEEKING_PHRASES,
    NEGATIVE_PHRASES,
    CHANNEL_TYPE_WEIGHTS,
    AUTHOR_ROLE_WEIGHTS
)

logger = logging.getLogger(__name__)


class DiscordScraper:
    """
    Discord scraper для Publisher Hunt.
    V1: Использует Discord HTTP API (требует bot token в ENV).
    """
    
    def __init__(self, bot_token: Optional[str] = None):
        """
        Инициализация Discord scraper.
        
        Args:
            bot_token: Discord bot token (из ENV или параметр)
        """
        import os
        self.bot_token = bot_token or os.getenv("DISCORD_BOT_TOKEN")
        if not self.bot_token:
            logger.warning("DISCORD_BOT_TOKEN not set, Discord scraping will be disabled")
        
        self.base_url = "https://discord.com/api/v10"
        self.headers = {
            "Authorization": f"Bot {self.bot_token}" if self.bot_token else None,
            "User-Agent": "GameScout/1.0"
        }
    
    def check_publisher_seeking(self, text: str) -> Dict[str, Any]:
        """
        Проверяет, содержит ли текст признаки поиска издателя.
        
        Args:
            text: Текст сообщения
            
        Returns:
            {
                "is_seeking": bool,
                "publisher_phrases": List[str],
                "negative_phrases": List[str],
                "confidence": float
            }
        """
        text_lower = text.lower()
        
        # Ищем publisher-seeking phrases (сначала regex для гибкости)
        publisher_phrases = []
        
        # Regex паттерны для более гибкого поиска
        regex_patterns = [
            (r'looking\s+for\s+(a\s+)?publisher', 'looking for publisher'),
            (r'need\s+(a\s+)?publisher', 'need a publisher'),
            (r'seeking\s+(a\s+)?publisher', 'seeking publisher'),
            (r'publisher\s+wanted', 'publisher wanted'),
            (r'looking\s+for\s+(a\s+)?publishing\s+partner', 'looking for publishing partner'),
            (r'seeking\s+(a\s+)?publishing\s+partner', 'seeking publishing partner'),
            (r'looking\s+for\s+(a\s+)?funding\s+partner', 'looking for funding partner'),
        ]
        
        # Проверяем regex паттерны
        for pattern, phrase_name in regex_patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                if phrase_name not in publisher_phrases:
                    publisher_phrases.append(phrase_name)
        
        # Также проверяем точные фразы из конфига (fallback)
        for phrase in PUBLISHER_SEEKING_PHRASES:
            if phrase.lower() in text_lower:
                if phrase not in publisher_phrases:
                    publisher_phrases.append(phrase)
        
        # Ищем negative phrases
        negative_phrases = []
        for phrase in NEGATIVE_PHRASES:
            if phrase.lower() in text_lower:
                negative_phrases.append(phrase)
        
        # Signal rule: publisher_phrase >= 1 AND negative_phrase == 0
        is_seeking = len(publisher_phrases) >= 1 and len(negative_phrases) == 0
        
        # Confidence: базовая на количестве фраз
        confidence = min(len(publisher_phrases) * 0.3, 1.0) if is_seeking else 0.0
        
        return {
            "is_seeking": is_seeking,
            "publisher_phrases": publisher_phrases,
            "negative_phrases": negative_phrases,
            "confidence": confidence,
            "matched_phrases": publisher_phrases  # Для debug: какие фразы сработали
        }
    
    def extract_text_from_message(self, msg: Dict[str, Any]) -> str:
        """
        Извлекает полный текст из сообщения Discord, включая content, embeds и attachments.
        
        Args:
            msg: Объект сообщения Discord
            
        Returns:
            Единый текст, собранный из всех источников
        """
        parts = []
        
        # Content
        content = msg.get("content", "")
        if content:
            parts.append(content)
        
        # Embeds
        embeds = msg.get("embeds", [])
        for embed in embeds:
            # Title
            title = embed.get("title")
            if title:
                parts.append(title)
            
            # Description
            description = embed.get("description")
            if description:
                parts.append(description)
            
            # URL
            url = embed.get("url")
            if url:
                parts.append(url)
            
            # Fields
            fields = embed.get("fields", [])
            for field in fields:
                name = field.get("name")
                value = field.get("value")
                if name:
                    parts.append(name)
                if value:
                    parts.append(value)
        
        # Attachments
        attachments = msg.get("attachments", [])
        for attachment in attachments:
            url = attachment.get("url")
            filename = attachment.get("filename")
            if url:
                parts.append(url)
            if filename:
                parts.append(filename)
        
        return "\n".join(parts).strip()
    
    def extract_urls(self, text: str) -> List[str]:
        """
        Извлекает все URL из текста.
        
        Args:
            text: Текст для поиска URL
            
        Returns:
            Список уникальных URL (максимум 20)
        """
        if not text:
            return []
        
        # Regex для поиска URL
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        urls = re.findall(url_pattern, text, re.IGNORECASE)
        
        # Убираем дубликаты и ограничиваем до 20
        unique_urls = list(dict.fromkeys(urls))[:20]
        
        return unique_urls
    
    def extract_steam_app_ids(self, text: str) -> List[int]:
        """
        Извлекает все Steam app_id из текста.
        
        Поддерживаемые варианты:
        1. https://store.steampowered.com/app/<app_id>
        2. store.steampowered.com/app/<app_id>
        3. https://steamcommunity.com/app/<app_id> (опционально)
        
        Args:
            text: Текст сообщения
            
        Returns:
            Список уникальных app_id
        """
        app_ids = []
        
        # Паттерн 1: https://store.steampowered.com/app/123456
        pattern1 = r'https?://store\.steampowered\.com/app/(\d+)'
        for match in re.finditer(pattern1, text, re.IGNORECASE):
            try:
                app_id = int(match.group(1))
                if app_id not in app_ids:
                    app_ids.append(app_id)
            except ValueError:
                pass
        
        # Паттерн 2: store.steampowered.com/app/123456 (без протокола)
        pattern2 = r'store\.steampowered\.com/app/(\d+)'
        for match in re.finditer(pattern2, text, re.IGNORECASE):
            try:
                app_id = int(match.group(1))
                if app_id not in app_ids:
                    app_ids.append(app_id)
            except ValueError:
                pass
        
        # Паттерн 3: https://steamcommunity.com/app/<app_id> (опционально)
        pattern3 = r'https?://steamcommunity\.com/app/(\d+)'
        for match in re.finditer(pattern3, text, re.IGNORECASE):
            try:
                app_id = int(match.group(1))
                if app_id not in app_ids:
                    app_ids.append(app_id)
            except ValueError:
                pass
        
        return app_ids
    
    def extract_steam_app_id(self, text: str) -> Optional[int]:
        """
        Извлекает Steam app_id из текста.
        
        Поддерживаемые варианты:
        1. https://store.steampowered.com/app/<app_id>
        2. store.steampowered.com/app/<app_id>
        
        Args:
            text: Текст сообщения
            
        Returns:
            app_id (int) или None
        """
        # Паттерн 1: https://store.steampowered.com/app/123456
        pattern1 = r'https?://store\.steampowered\.com/app/(\d+)'
        match = re.search(pattern1, text, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                pass
        
        # Паттерн 2: store.steampowered.com/app/123456 (без протокола)
        pattern2 = r'store\.steampowered\.com/app/(\d+)'
        match = re.search(pattern2, text, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                pass
        
        return None
    
    def get_channel_messages(
        self, 
        server_id: str, 
        channel_id: str, 
        days: int = 1,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Получает сообщения из Discord канала.
        
        Args:
            server_id: ID Discord сервера
            channel_id: ID канала
            days: Количество дней назад
            limit: Максимум сообщений
            
        Returns:
            Список сообщений с полями: id, content, author, timestamp, etc.
        """
        if not self.bot_token:
            logger.warning("DISCORD_BOT_TOKEN not set, skipping Discord channel messages")
            return []
        
        try:
            url = f"{self.base_url}/channels/{channel_id}/messages"
            params = {
                "limit": min(limit, 100)  # Discord API limit
            }
            
            # Вычисляем timestamp для фильтрации по дням
            cutoff_time = datetime.utcnow() - timedelta(days=days)
            cutoff_timestamp = int(cutoff_time.timestamp())
            
            messages = []
            after = None
            
            while len(messages) < limit:
                if after:
                    params["after"] = after
                
                response = requests.get(url, headers=self.headers, params=params, timeout=15)
                
                # Сохраняем статус для диагностики (будет использоваться в вызывающем коде)
                if response.status_code == 429:
                    # Rate limit - ждём
                    retry_after = int(response.headers.get("Retry-After", 5))
                    logger.warning(f"Discord rate limited, waiting {retry_after}s")
                    time.sleep(retry_after)
                    continue
                
                if response.status_code == 403:
                    logger.warning(f"Discord API returned 403 (Forbidden) for channel {channel_id} - no read permission")
                    return []  # Возвращаем пустой список, не падаем
                
                if response.status_code == 404:
                    logger.warning(f"Discord API returned 404 (Not Found) for channel {channel_id}")
                    return []  # Возвращаем пустой список, не падаем
                
                if response.status_code != 200:
                    logger.warning(f"Discord API returned {response.status_code} for channel {channel_id}")
                    return []  # Возвращаем пустой список вместо break
                
                data = response.json()
                if not data:
                    break
                
                for msg in data:
                    # Фильтруем по времени
                    msg_timestamp = int(datetime.fromisoformat(msg["timestamp"].replace("Z", "+00:00")).timestamp())
                    if msg_timestamp < cutoff_timestamp:
                        # Сообщения старше cutoff - прекращаем
                        return messages
                    
                    messages.append({
                        "id": msg.get("id"),
                        "content": msg.get("content", ""),
                        "embeds": msg.get("embeds", []),  # Сохраняем embeds для извлечения текста
                        "attachments": msg.get("attachments", []),  # Сохраняем attachments
                        "author": {
                            "id": msg.get("author", {}).get("id"),
                            "username": msg.get("author", {}).get("username"),
                            "bot": msg.get("author", {}).get("bot", False)
                        },
                        "timestamp": msg.get("timestamp"),
                        "channel_id": channel_id,
                        "server_id": server_id
                    })
                    
                    if len(messages) >= limit:
                        break
                
                # Проверяем, есть ли ещё сообщения
                if len(data) < params["limit"]:
                    break
                
                after = data[-1]["id"]
                time.sleep(1)  # Rate limiting
            
            return messages
            
        except Exception as e:
            logger.error(f"Error fetching Discord messages: {e}", exc_info=True)
            return []
    
    def get_server_channels(self, server_id: str) -> List[Dict[str, Any]]:
        """
        Получает список каналов Discord сервера.
        
        Args:
            server_id: ID Discord сервера
            
        Returns:
            Список каналов с полями: id, name, type
        """
        if not self.bot_token:
            logger.warning("DISCORD_BOT_TOKEN not set, skipping Discord server channels")
            return []
        
        try:
            url = f"{self.base_url}/guilds/{server_id}/channels"
            response = requests.get(url, headers=self.headers, timeout=15)
            
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 5))
                logger.warning(f"Discord rate limited, waiting {retry_after}s")
                time.sleep(retry_after)
                return []
            
            if response.status_code != 200:
                logger.warning(f"Discord API returned {response.status_code} for server {server_id}")
                return []
            
            channels = []
            for channel in response.json():
                # Только текстовые каналы
                if channel.get("type") == 0:  # GUILD_TEXT
                    channels.append({
                        "id": channel.get("id"),
                        "name": channel.get("name"),
                        "type": channel.get("type"),
                        "last_message_id": channel.get("last_message_id")  # Может быть None
                    })
            
            return channels
            
        except Exception as e:
            logger.error(f"Error fetching Discord channels: {e}", exc_info=True)
            return []
    
    def calculate_channel_activity_score(
        self,
        channel_id: str,
        sample_size: int = 10,
        days: int = 3
    ) -> Dict[str, Any]:
        """
        Вычисляет approx_activity_score для канала.
        
        Формула:
        score = count(messages) + 2*count(messages_with_links) + 3*count(messages_with_keywords)
        
        Args:
            channel_id: ID канала
            sample_size: Количество сообщений для анализа (N=10)
            days: Период для поиска сообщений (24-72 часа, default 3 дня)
            
        Returns:
            {
                "score": float,
                "message_count": int,
                "messages_with_links": int,
                "messages_with_keywords": int,
                "error": str (optional)
            }
        """
        if not self.bot_token:
            return {"score": 0.0, "message_count": 0, "messages_with_links": 0, "messages_with_keywords": 0}
        
        try:
            # Получаем sample сообщений
            messages = self.get_channel_messages(
                server_id="",  # Не используется в get_channel_messages для activity
                channel_id=channel_id,
                days=days,
                limit=sample_size
            )
            
            if not messages:
                return {"score": 0.0, "message_count": 0, "messages_with_links": 0, "messages_with_keywords": 0}
            
            message_count = len(messages)
            messages_with_links = 0
            messages_with_keywords = 0
            
            # Ключевые слова для publisher intent (минимальный набор)
            keywords = [
                "publisher", "publishing", "pitch", "funding", "investor",
                "deal", "partnership", "partner", "bizdev", "business"
            ]
            
            for msg in messages:
                # Извлекаем полный текст из сообщения
                extracted_text = self.extract_text_from_message(msg)
                extracted_urls = self.extract_urls(extracted_text)
                text_lower = extracted_text.lower()
                
                # Проверка на ссылки (по extracted_urls)
                if len(extracted_urls) > 0:
                    messages_with_links += 1
                
                # Проверка на ключевые слова (по полному тексту)
                for keyword in keywords:
                    if keyword in text_lower:
                        messages_with_keywords += 1
                        break
            
            # Формула: score = count(messages) + 2*count(messages_with_links) + 3*count(messages_with_keywords)
            score = message_count + 2 * messages_with_links + 3 * messages_with_keywords
            
            return {
                "score": float(score),
                "message_count": message_count,
                "messages_with_links": messages_with_links,
                "messages_with_keywords": messages_with_keywords
            }
            
        except Exception as e:
            logger.warning(f"Error calculating activity score for channel {channel_id}: {e}")
            return {
                "score": 0.0,
                "message_count": 0,
                "messages_with_links": 0,
                "messages_with_keywords": 0,
                "error": str(e)
            }
