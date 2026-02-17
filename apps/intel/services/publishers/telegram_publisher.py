"""
Telegram Publisher for Intel Events
Publishes business briefs to Telegram channels (public/premium).
"""
import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass

import httpx

from apps.intel.db.models import IntelEvent, IntelPublishLog
from apps.intel.policy.policy_engine import load_policy
from apps.intel.config import get_telegram_config, INTEL_DRY_RUN
from typing import Tuple

logger = logging.getLogger(__name__)


@dataclass
class PublishResult:
    """Result of publishing an event"""
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None
    status: str = "published"  # published/failed/skipped


class TelegramPublisher:
    """Publishes Intel events to Telegram channels"""
    
    def __init__(self, db_session):
        self.db = db_session
        token, chat_id = get_telegram_config()
        self.bot_token = token
        self.chat_id = chat_id
        if self.bot_token:
            self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        else:
            self.base_url = None
        
        # Try to auto-detect chat_id if not set but token is available
        if self.bot_token and not self.chat_id:
            auto_chat_id = self._try_get_chat_id_from_updates()
            if auto_chat_id:
                self.chat_id = auto_chat_id
                logger.info(f"Auto-detected TELEGRAM_CHAT_ID: {auto_chat_id}")
    
    def _check_rate_limits(self) -> tuple[bool, Optional[str]]:
        """Check if rate limits allow publishing"""
        policy = load_policy()
        
        # Get recent publish count
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        one_day_ago = datetime.utcnow() - timedelta(days=1)
        
        recent_publishes = self.db.query(IntelPublishLog).filter(
            IntelPublishLog.published_at >= one_hour_ago
        ).count()
        
        daily_publishes = self.db.query(IntelPublishLog).filter(
            IntelPublishLog.published_at >= one_day_ago
        ).count()
        
        limits = policy.get("limits", {})
        max_per_hour = limits.get("max_posts_per_hour", 5)
        max_per_day = limits.get("max_posts_per_day", 30)
        
        if recent_publishes >= max_per_hour:
            return False, f"Rate limit: {recent_publishes}/{max_per_hour} posts in last hour"
        
        if daily_publishes >= max_per_day:
            return False, f"Rate limit: {daily_publishes}/{max_per_day} posts today"
        
        return True, None
    
    def _format_message(self, event: IntelEvent, brief: Optional[Dict[str, Any]] = None) -> str:
        """Format event as Telegram message with [Category | Score] format"""
        policy = load_policy()
        template_config = policy.get("telegram_template", {})
        max_chars = template_config.get("max_chars", 3500)
        
        # Use brief if available, otherwise use event fields
        if brief:
            title = brief.get("title", event.title_ru)
            what_happened = brief.get("what_happened", event.what_happened_ru)
            why_it_matters = brief.get("why_it_matters", event.why_it_matters_ru or "нет данных")
            key_points = brief.get("key_points", [])
            source_url = brief.get("source_url", "")
        else:
            title = event.title_ru
            what_happened = event.what_happened_ru
            why_it_matters = event.why_it_matters_ru or "нет данных"
            key_points = []
            source_url = event.sources[0] if event.sources and isinstance(event.sources, list) else (str(event.sources) if event.sources else "")
        
        # Get category and score
        signal_type = brief.get("signal_type", event.event_type) if brief else event.event_type
        score = event.significance_score if hasattr(event, 'significance_score') else 0
        
        # Format category name in Russian
        category_names = {
            "release": "Релиз",
            "patch_major": "Обновление",
            "discount": "Скидка",
            "publisher_deal": "Издатель",
            "funding": "Финансирование",
            "market_trend": "Тренд",
            "controversy": "Спор",
            "other": "Прочее"
        }
        category_ru = category_names.get(signal_type, signal_type)
        
        # Build message
        message_parts = []
        
        # Title with category and score
        message_parts.append(f"🔹 [{category_ru} | {score}] {title}\n")
        
        # What happened
        message_parts.append(f"Что произошло:\n{what_happened}\n")
        
        # Why it matters
        if why_it_matters and why_it_matters != "нет данных":
            message_parts.append(f"Почему это важно:\n{why_it_matters}\n")
        
        # Key points
        if key_points:
            message_parts.append("Ключевые факты:")
            for point in key_points[:6]:  # Max 6 points
                message_parts.append(f"• {point}")
            message_parts.append("")  # Empty line
        
        # Source URL (always required)
        if source_url:
            message_parts.append(f"Источник:\n{source_url}")
        elif event.sources:
            source_url = event.sources[0] if isinstance(event.sources, list) else str(event.sources)
            message_parts.append(f"Источник:\n{source_url}")
        else:
            message_parts.append("Источник: нет данных")
        
        message = "\n".join(message_parts)
        
        # Truncate if too long
        if len(message) > max_chars:
            message = message[:max_chars - 3] + "..."
        
        return message
    
    def _send_to_telegram(self, message: str, chat_id: Optional[str] = None) -> tuple[bool, Optional[str], Optional[str]]:
        """Send message to Telegram"""
        if not self.bot_token:
            return False, None, "TELEGRAM_BOT_TOKEN not configured"
        
        if not chat_id:
            chat_id = self.chat_id
        
        if not chat_id:
            return False, None, "TELEGRAM_CHAT_ID not configured"
        
        if INTEL_DRY_RUN:
            logger.info(f"[DRY RUN] Would send to Telegram chat {chat_id}: {message[:100]}...")
            return True, "dry_run_message_id", None
        
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML"
            }
            
            with httpx.Client(timeout=10.0) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                
                result = response.json()
                if result.get("ok"):
                    message_id = str(result["result"]["message_id"])
                    return True, message_id, None
                else:
                    error = result.get("description", "Unknown Telegram API error")
                    return False, None, error
                    
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}", exc_info=True)
            return False, None, str(e)
    
    def publish_event(
        self, 
        event: IntelEvent,
        brief: Dict[str, Any],
        dry_run: bool = False
    ) -> PublishResult:
        """
        Publish event to Telegram.
        
        Args:
            event: IntelEvent to publish
            brief: Business brief dict
            dry_run: If True, don't actually send (just log)
        
        Returns:
            PublishResult with success status and message_id
        """
        # Check duplicate
        existing = self.db.query(IntelPublishLog).filter(
            IntelPublishLog.event_id == event.id,
            IntelPublishLog.status == "published"
        ).first()
        
        if existing:
            logger.info(f"Event {event.id} already published, skipping")
            return PublishResult(
                success=False,
                status="skipped",
                error="Event already published"
            )
        
        # Check rate limits
        can_publish, rate_limit_error = self._check_rate_limits()
        if not can_publish:
            logger.warning(f"Rate limit exceeded: {rate_limit_error}")
            return PublishResult(
                success=False,
                status="skipped",
                error=rate_limit_error
            )
        
        # Format message
        message = self._format_message(event, brief)
        
        # Send to Telegram
        success, message_id, error = self._send_to_telegram(message)
        
        # Save to publish log
        publish_log = IntelPublishLog(
            event_id=event.id,
            channel_id="free",  # Single channel
            telegram_message_id=message_id or "",
            payload={"message": message[:500]},  # Store first 500 chars
            status="published" if success else "failed",
            error=error
        )
        self.db.add(publish_log)
        
        if success and message_id and not dry_run and not INTEL_DRY_RUN:
            # Update event
            event.publish_status = "published"
            event.publish_channel = "free"
            event.published_at = datetime.utcnow()
            event.telegram_message_id = message_id
        
        self.db.commit()
        
        return PublishResult(
            success=success,
            message_id=message_id,
            error=error,
            status="published" if success else "failed"
        )
    
    def _try_get_chat_id_from_updates(self) -> Optional[str]:
        """Try to get chat_id from recent bot updates (helper for finding channel ID)"""
        if not self.bot_token or not self.base_url:
            return None
        
        try:
            url = f"{self.base_url}/getUpdates"
            with httpx.Client(timeout=5.0) as client:
                response = client.get(url, params={"limit": 10})
                response.raise_for_status()
                result = response.json()
                
                if result.get("ok"):
                    updates = result.get("result", [])
                    for update in updates:
                        # Check channel posts
                        if "channel_post" in update:
                            chat = update["channel_post"].get("chat", {})
                            chat_id = chat.get("id")
                            if chat_id:
                                return str(chat_id)
                        # Check forwarded messages
                        if "message" in update:
                            chat = update["message"].get("chat", {})
                            if chat.get("type") == "channel":
                                chat_id = chat.get("id")
                                if chat_id:
                                    return str(chat_id)
        except Exception:
            pass
        
        return None
    
    def check_telegram_access(self) -> Tuple[bool, str, dict]:
        """
        Check Telegram bot and channel access without sending messages.
        
        Returns:
            (ok: bool, error: str, details: dict)
            - ok: True if bot token and chat are valid
            - error: Error message if failed
            - details: Dict with bot info, chat info (without exposing token)
        """
        if not self.bot_token:
            return False, "TELEGRAM_BOT_TOKEN not configured", {}
        
        # chat_id should be set by __init__ or auto-detection
        if not self.chat_id:
            return False, "TELEGRAM_CHAT_ID not configured. Set TELEGRAM_CHAT_ID environment variable or ensure bot has received messages from channel.", {}
        
        if not self.base_url:
            return False, "Telegram base_url not configured", {}
        
        details = {}
        
        try:
            # Check bot token via getMe
            url = f"{self.base_url}/getMe"
            with httpx.Client(timeout=5.0) as client:
                response = client.get(url)
                response.raise_for_status()
                result = response.json()
                
                if result.get("ok"):
                    bot_info = result.get("result", {})
                    details["bot_username"] = bot_info.get("username", "unknown")
                    details["bot_id"] = bot_info.get("id", "unknown")
                else:
                    error_code = result.get("error_code", 0)
                    error_msg = result.get("description", "Unknown error")
                    # Never expose token in error
                    error_msg = error_msg.replace(self.bot_token, "***TOKEN***")
                    
                    if error_code == 401:
                        return False, "Invalid bot token: token is incorrect or revoked", details
                    else:
                        return False, f"Bot token invalid (code {error_code}): {error_msg}", details
            
            # Check chat access via getChat
            url = f"{self.base_url}/getChat"
            payload = {"chat_id": self.chat_id}
            with httpx.Client(timeout=5.0) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                result = response.json()
                
                if result.get("ok"):
                    chat_info = result.get("result", {})
                    details["chat_title"] = chat_info.get("title", chat_info.get("first_name", "unknown"))
                    details["chat_type"] = chat_info.get("type", "unknown")
                    details["can_post"] = True  # If getChat succeeds, bot has access
                else:
                    error_code = result.get("error_code", 0)
                    error_msg = result.get("description", "Unknown error")
                    
                    # Detailed error messages
                    if error_code == 400:
                        if "chat not found" in error_msg.lower():
                            return False, "Chat not found: bot may not be added to channel or chat_id is incorrect", details
                        else:
                            return False, f"Invalid chat_id: {error_msg}", details
                    elif error_code == 403:
                        return False, "Bot not admin: bot must be added as administrator with 'Post messages' permission", details
                    elif error_code == 401:
                        return False, "Unauthorized: bot token may be invalid", details
                    else:
                        return False, f"Chat access failed (code {error_code}): {error_msg}", details
            
            return True, "", details
            
        except httpx.HTTPError as e:
            error_msg = str(e).replace(self.bot_token, "***TOKEN***") if self.bot_token else str(e)
            return False, f"HTTP error: {error_msg}", details
        except Exception as e:
            error_msg = str(e).replace(self.bot_token, "***TOKEN***") if self.bot_token else str(e)
            return False, f"Unexpected error: {error_msg}", details
