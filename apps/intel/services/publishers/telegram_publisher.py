"""
Telegram Publisher for Intel Events
Publishes business briefs to Telegram channels (public/premium).
"""
import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from apps.intel.db.models import IntelEvent, IntelPublishLog
from apps.intel.policy.policy_engine import load_policy
from apps.intel.config import get_telegram_config, INTEL_DRY_RUN
from typing import Tuple
from datetime import datetime

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
        """
        Format event as structured Telegram message with country tags, category, and importance badge.
        
        New format:
        {country_emoji} #{country_code} | {category_tag}
        {importance_emoji} {importance_label} (Score: {score})
        
        Steam: {title}
        
        Кратко:
        {executive_summary}
        
        Что произошло:
        {what_happened}
        ...
        """
        from apps.intel.services.country_detector import detect_country
        from apps.intel.services.telegram_formatters import format_telegram_message, importance_badge
        
        policy = load_policy()
        template_config = policy.get("telegram_template", {})
        max_chars = template_config.get("max_chars", 3500)
        
        # Use brief if available, otherwise use event fields
        if not brief:
            brief = {
                "title": event.title_ru or "",
                "what_happened": event.what_happened_ru or "",
                "why_it_matters": event.why_it_matters_ru or "нет данных",
                "key_points": [],
                "source_url": event.sources[0] if event.sources and isinstance(event.sources, list) else (str(event.sources) if event.sources else ""),
                "signal_type": event.event_type
            }
        
        # Detect country
        source_url = brief.get("source_url", "")
        text_for_country = brief.get("what_happened", "") or brief.get("title", "")
        country_info = detect_country(event, source_url=source_url, text=text_for_country)
        
        # Get importance badge
        score = event.significance_score if hasattr(event, 'significance_score') else 0
        importance_info = importance_badge(score)
        
        # Format message using new formatter
        message = format_telegram_message(event, brief, country_info, importance_info)
        
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
        
        # Retry logic: 3 attempts with exponential backoff (1s, 2s, 4s)
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=4),
            retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
            reraise=True
        )
        def _send_with_retry():
            # Clean HTML tags from message for Telegram HTML parse_mode
            # Telegram HTML parser is strict and doesn't support all tags
            import re
            # Remove unsupported HTML tags but keep text content
            message_clean = re.sub(r'<br\s*/?>', '\n', message, flags=re.IGNORECASE)
            message_clean = re.sub(r'</?ul[^>]*>', '', message_clean, flags=re.IGNORECASE)
            message_clean = re.sub(r'</?li[^>]*>', '• ', message_clean, flags=re.IGNORECASE)
            message_clean = re.sub(r'<[^>]+>', '', message_clean)  # Remove any remaining HTML tags
            # Escape HTML entities
            message_clean = message_clean.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": message_clean,
                "parse_mode": "HTML"
            }
            
            with httpx.Client(timeout=10.0) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                
                result = response.json()
                if result.get("ok"):
                    message_id = str(result["result"]["message_id"])
                    logger.info(f"Telegram message sent successfully: message_id={message_id}, chat_id={chat_id}")
                    return True, message_id, None
                else:
                    error = result.get("description", "Unknown Telegram API error")
                    logger.error(f"Telegram API error: {error}")
                    return False, None, error
        
        try:
            return _send_with_retry()
        except Exception as e:
            error_msg = str(e)
            # Never log token
            if self.bot_token:
                error_msg = error_msg.replace(self.bot_token, "***TOKEN***")
            logger.error(f"Failed to send Telegram message after retries: {error_msg}", exc_info=True)
            return False, None, error_msg
    
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
        # Check duplicate (with repost_for_test override)
        import os
        allow_repost_for_test = os.getenv("PIPELINE_ALLOW_REPOST_FOR_TEST", "false").lower() == "true"
        repost_count = 0
        
        if allow_repost_for_test:
            # Count existing repost_test entries
            repost_count = self.db.query(IntelPublishLog).filter(
                IntelPublishLog.status == "published",
                IntelPublishLog.error == "repost_test"
            ).count()
        
        existing = self.db.query(IntelPublishLog).filter(
            IntelPublishLog.event_id == event.id,
            IntelPublishLog.status == "published"
        ).first()
        
        if existing:
            # Allow repost if PIPELINE_ALLOW_REPOST_FOR_TEST=true and repost_count < 2
            if allow_repost_for_test and repost_count < 2:
                logger.info(f"Event {event.id} already published, but allowing repost for test (count: {repost_count + 1}/2)")
                # Continue to publish, but mark as repost_test
            else:
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
        
        # Normalize brief to Russian before formatting (A2: ensure all fields are Russian)
        from apps.intel.services.business_brief_generator import normalize_to_ru
        from apps.intel.services.translation.free_translate import TranslationError
        
        try:
            brief_normalized = normalize_to_ru(brief)
            # Check if translation failed for critical fields
            translation_meta = brief_normalized.get("translation_meta", {})
            if translation_meta.get("translation_failed"):
                logger.error(f"Event {event.id} translation failed for critical fields, blocking publication")
                skip_payload = {
                    "event_id": str(event.id),
                    "source_url": brief.get("source_url", ""),
                    "translation_meta": translation_meta,
                    "reason": "translation_unavailable"
                }
                skip_log = IntelPublishLog(
                    event_id=event.id,
                    channel_id="free",
                    telegram_message_id="",
                    status="skipped",
                    error="translation_unavailable",
                    payload=skip_payload
                )
                self.db.add(skip_log)
                self.db.commit()
                return PublishResult(
                    success=False,
                    status="skipped",
                    error="translation_unavailable"
                )
            brief = brief_normalized
        except TranslationError as e:
            logger.error(f"Event {event.id} translation service unavailable: {e}, blocking publication")
            skip_payload = {
                "event_id": str(event.id),
                "source_url": brief.get("source_url", ""),
                "error": str(e),
                "reason": "translation_unavailable"
            }
            skip_log = IntelPublishLog(
                event_id=event.id,
                channel_id="free",
                telegram_message_id="",
                status="skipped",
                error="translation_unavailable",
                payload=skip_payload
            )
            self.db.add(skip_log)
            self.db.commit()
            return PublishResult(
                success=False,
                status="skipped",
                error=f"translation_unavailable: {str(e)}"
            )
        
        # Format message
        message = self._format_message(event, brief)
        
        # Editorial quality checks (hard rules before publication)
        from apps.intel.services.editorial_rewriter import validate_editorial_quality, enforce_editorial_quality, rewrite_editorial_ru
        
        # CRITICAL: Multiple rewrite passes for complete cleanup
        # Pass 1: Basic rewrite
        message = rewrite_editorial_ru(message, event_type=event.event_type, score=event.significance_score if hasattr(event, 'significance_score') else 0)
        # Pass 2: Additional cleanup for any remaining artifacts
        message = rewrite_editorial_ru(message, event_type=event.event_type, score=event.significance_score if hasattr(event, 'significance_score') else 0)
        
        # Final cleanup: remove any remaining HTML/URL fragments
        import re
        message = re.sub(r'<[^>]+>', '', message)  # Remove any remaining HTML
        message = re.sub(r'https?://[^\s]+', '', message)  # Remove URLs
        message = re.sub(r'[a-zA-Z0-9_-]+\.(jpg|png|gif|webp|jpeg)\?[^\s]*', '', message, flags=re.IGNORECASE)  # Remove image URLs
        message = re.sub(r'\s+', ' ', message)  # Normalize whitespace
        message = message.strip()
        
        quality_check = validate_editorial_quality(message)
        if not quality_check["valid"]:
            logger.warning(f"Event {event.id} message quality check failed, attempting rewrite: {quality_check['errors']}")
            # Try to fix quality issues
            message = enforce_editorial_quality(message, max_iterations=5)  # Increased iterations
            # Re-check
            quality_check = validate_editorial_quality(message)
            if not quality_check["valid"]:
                logger.error(f"Event {event.id} message quality still fails after rewrite: {quality_check['errors']}")
                # Check if critical errors (non-Russian) - block publication
                critical_errors = [e for e in quality_check.get('errors', []) if 'Cyrillic' in e or 'English words' in e]
                if critical_errors:
                    logger.error(f"Event {event.id} has critical quality errors, blocking publication: {critical_errors}")
                    skip_payload = {
                        "event_id": str(event.id),
                        "source_url": brief.get("source_url", ""),
                        "quality_errors": quality_check.get('errors', []),
                        "reason": "editorial_quality_failed"
                    }
                    skip_log = IntelPublishLog(
                        event_id=event.id,
                        channel_id="free",
                        telegram_message_id="",
                        status="skipped",
                        error="editorial_quality_failed",
                        payload=skip_payload
                    )
                    self.db.add(skip_log)
                    self.db.commit()
                    return PublishResult(
                        success=False,
                        status="skipped",
                        error="editorial_quality_failed"
                    )
        
        # Strict Russian language check (A1: hard gate before sending)
        from apps.intel.services.translator import message_is_russian, detect_language
        detected_lang = detect_language(message)
        cyrillic_count = sum(1 for char in message if '\u0400' <= char <= '\u04FF')
        total_chars = len([c for c in message if c.isalpha()])
        ru_ratio = cyrillic_count / total_chars if total_chars > 0 else 0
        
        # Hard threshold: at least 30% Cyrillic for Russian text (increased from 25%)
        is_russian = message_is_russian(message) and ru_ratio >= 0.30
        
        if not is_russian:
            logger.error(f"Event {event.id} message is not in Russian! Blocking publication. "
                        f"Detected: {detected_lang}, Cyrillic ratio: {ru_ratio:.2%}")
            
            # Save skip log with details
            skip_payload = {
                "detected_lang": detected_lang,
                "ru_ratio": ru_ratio,
                "event_id": str(event.id),
                "source_url": brief.get("source_url", "") if brief else (event.sources[0] if event.sources else ""),
                "message_preview": message[:200]
            }
            skip_log = IntelPublishLog(
                event_id=event.id,
                channel_id="free",
                telegram_message_id="",
                status="skipped",
                error="non_russian_output",
                payload=skip_payload
            )
            self.db.add(skip_log)
            self.db.commit()
            
            return PublishResult(
                success=False,
                status="skipped",
                error=f"non_russian_output (detected: {detected_lang}, ru_ratio: {ru_ratio:.2%})"
            )
        
        # Send to Telegram
        success, message_id, error = self._send_to_telegram(message)
        
        # Determine if this is a repost_test
        is_repost_test = allow_repost_for_test and existing is not None
        
        # Save to publish log with significance info
        payload = {
            "message": message[:500],  # Store first 500 chars
            "significance_score": event.significance_score if hasattr(event, 'significance_score') else 0,
            "significance_reason": event.significance_reason if hasattr(event, 'significance_reason') else None,
            "event_type": event.event_type,
            "eligibility_decision": "accepted" if success else "rejected",
            "repost_test": is_repost_test
        }
        
        publish_log = IntelPublishLog(
            event_id=event.id,
            channel_id="free",  # Single channel
            telegram_message_id=message_id or "",
            payload=payload,
            status="published" if success else "failed",
            error="repost_test" if is_repost_test else error  # Mark repost_test in error field
        )
        self.db.add(publish_log)
        
        if success and message_id and not dry_run and not INTEL_DRY_RUN:
            # Update event
            event.publish_status = "published"
            event.publish_channel = "free"
            event.published_at = datetime.utcnow()
            event.telegram_message_id = message_id
            score = event.significance_score if hasattr(event, 'significance_score') else 0
            if is_repost_test:
                logger.info(f"✅ Event {event.id} republished to Telegram for test (message_id={message_id}, score={score})")
            else:
                logger.info(f"✅ Event {event.id} published to Telegram: message_id={message_id}, score={score}, type={event.event_type}")
        
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
