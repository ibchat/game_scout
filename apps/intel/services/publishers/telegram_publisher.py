"""
Telegram Publisher for Intel Events
Publishes business briefs to Telegram channels (public/premium).
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass

import httpx

from apps.intel.db.models import IntelEvent, IntelPublishLog
from apps.intel.policy.policy_engine import load_policy, enforce_rate_limits
from apps.intel.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, INTEL_DRY_RUN

logger = logging.getLogger(__name__)


@dataclass
class PublishResult:
    """Result of publishing an event"""
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None
    channel: Optional[str] = None


class TelegramPublisher:
    """Publishes Intel events to Telegram channels"""
    
    def __init__(self, db_session):
        self.db = db_session
        self.bot_token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
    
    def _check_rate_limits(self, channel: str = "public") -> tuple[bool, Optional[str]]:
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
        """Format event as Telegram message"""
        policy = load_policy()
        template_config = policy.get("telegram_template", {})
        max_chars = template_config.get("max_chars", 3500)
        
        # Use brief if available, otherwise use event fields
        if brief:
            headline = brief.get("headline", event.title_ru)
            what_happened = brief.get("what_happened", event.what_happened_ru)
            why_it_matters = brief.get("why_it_matters", event.why_it_matters_ru or "нет данных")
            market_signal = brief.get("market_signal", "neutral")
            risk_level = brief.get("risk_level", "medium")
        else:
            headline = event.title_ru
            what_happened = event.what_happened_ru
            why_it_matters = event.why_it_matters_ru or "нет данных"
            market_signal = "neutral"
            risk_level = "medium"
        
        # Build message
        message_parts = []
        
        # Title
        message_parts.append(f"📊 {headline}\n")
        
        # What happened
        message_parts.append(f"🔍 Что произошло:\n{what_happened}\n")
        
        # Why it matters
        if why_it_matters and why_it_matters != "нет данных":
            message_parts.append(f"💡 Почему важно:\n{why_it_matters}\n")
        
        # Market signal
        signal_emoji = {
            "bullish": "📈",
            "bearish": "📉",
            "neutral": "➡️"
        }.get(market_signal.lower(), "➡️")
        message_parts.append(f"{signal_emoji} Сигнал рынка: {market_signal.upper()}")
        
        # Risk level
        risk_emoji = {
            "low": "🟢",
            "medium": "🟡",
            "high": "🔴"
        }.get(risk_level.lower(), "🟡")
        message_parts.append(f"{risk_emoji} Уровень риска: {risk_level.upper()}\n")
        
        # Event type and Steam app
        if event.steam_appid:
            message_parts.append(f"🎮 Steam: {event.steam_appid}")
        message_parts.append(f"📌 Тип: {event.event_type}")
        
        # Sources
        if event.sources:
            message_parts.append(f"\n🔗 Источники: {len(event.sources)}")
        
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
        dry_run: bool = False,
        channel: str = "public"
    ) -> PublishResult:
        """
        Publish event to Telegram.
        
        Args:
            event: IntelEvent to publish
            dry_run: If True, don't actually send (just log)
            channel: "public" or "premium"
        
        Returns:
            PublishResult with success status and message_id
        """
        # Check policy: allowed event types
        policy = load_policy()
        allowed_types = policy.get("allowed_event_types_for_autopublish", [])
        
        if event.event_type not in allowed_types:
            return PublishResult(
                success=False,
                error=f"Event type {event.event_type} not in allowed_types_for_autopublish"
            )
        
        # Check rate limits
        can_publish, rate_limit_error = self._check_rate_limits(channel)
        if not can_publish:
            return PublishResult(
                success=False,
                error=rate_limit_error
            )
        
        # Get business brief if available
        brief = event.business_brief_json
        
        # Format message
        message = self._format_message(event, brief)
        
        # Determine chat ID based on channel
        chat_id = self.chat_id  # For now, use same chat. Can be extended for premium channel
        
        # Send to Telegram
        success, message_id, error = self._send_to_telegram(message, chat_id)
        
        if success and message_id and not dry_run and not INTEL_DRY_RUN:
            # Save to publish log
            publish_log = IntelPublishLog(
                event_id=event.id,
                channel_id=channel,
                telegram_message_id=message_id,
                payload={"message": message[:500]}  # Store first 500 chars
            )
            self.db.add(publish_log)
            
            # Update event
            event.publish_status = "published"
            event.publish_channel = channel
            event.published_at = datetime.utcnow()
            event.telegram_message_id = message_id
            
            self.db.commit()
        
        return PublishResult(
            success=success,
            message_id=message_id,
            error=error,
            channel=channel
        )
