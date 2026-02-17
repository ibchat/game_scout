"""
Intel Module Configuration
Feature flags and settings for Intel subsystem.
"""
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Feature flags (all default to safe/disabled)
# Parse INTEL_ENABLED with explicit boolean conversion
_intel_enabled_raw = os.getenv("INTEL_ENABLED", "false")
_intel_enabled_cleaned = _intel_enabled_raw.strip().lower() if _intel_enabled_raw else "false"
INTEL_ENABLED = _intel_enabled_cleaned == "true"

# Debug log the parsed value
logger.info(f"Intel config: INTEL_ENABLED raw='{_intel_enabled_raw}', cleaned='{_intel_enabled_cleaned}', parsed={INTEL_ENABLED}")
INTEL_DRY_RUN = os.getenv("INTEL_DRY_RUN", "false").lower() == "true"
INTEL_AUTO_PUBLISH = os.getenv("INTEL_AUTO_PUBLISH", "false").lower() == "true"
INTEL_AUTO_PUBLISH_SAFE_ONLY = os.getenv("INTEL_AUTO_PUBLISH_SAFE_ONLY", "true").lower() == "true"

# Rate limits
INTEL_MAX_POSTS_PER_HOUR = int(os.getenv("INTEL_MAX_POSTS_PER_HOUR", "5"))
INTEL_MAX_POSTS_PER_DAY = int(os.getenv("INTEL_MAX_POSTS_PER_DAY", "30"))

# Source filtering
INTEL_SOURCES_ALLOWLIST_ONLY = os.getenv("INTEL_SOURCES_ALLOWLIST_ONLY", "true").lower() == "true"

# LLM configuration (separate from main pipeline)
INTEL_LLM_PROVIDER = os.getenv("INTEL_LLM_PROVIDER", os.getenv("LLM_PROVIDER", "anthropic"))
INTEL_LLM_MODEL_FAST = os.getenv("INTEL_LLM_MODEL_FAST", "claude-3-5-haiku-20241022")
INTEL_LLM_MODEL_STRONG = os.getenv("INTEL_LLM_MODEL_STRONG", "claude-3-5-sonnet-20241022")

# Telegram configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()  # Legacy, use FREE/PREMIUM if available
TELEGRAM_CHAT_ID_FREE = os.getenv("TELEGRAM_CHAT_ID_FREE", "").strip()
TELEGRAM_CHAT_ID_PREMIUM = os.getenv("TELEGRAM_CHAT_ID_PREMIUM", "").strip()

# Pipeline configuration
INTEL_COLLECT_INTERVAL_MINUTES = int(os.getenv("INTEL_COLLECT_INTERVAL_MINUTES", "60"))
INTEL_PIPELINE_BATCH_SIZE = int(os.getenv("INTEL_PIPELINE_BATCH_SIZE", "50"))


def is_intel_enabled() -> bool:
    """Check if Intel module is enabled."""
    return INTEL_ENABLED


def is_dry_run() -> bool:
    """Check if Intel is in dry-run mode (no actual publishing)."""
    return INTEL_DRY_RUN


def can_auto_publish() -> bool:
    """Check if auto-publishing is enabled."""
    return INTEL_AUTO_PUBLISH and not INTEL_DRY_RUN and INTEL_ENABLED


def get_telegram_config() -> tuple[Optional[str], Optional[str]]:
    """
    Get Telegram bot token and chat ID. 
    Returns (token, chat_id) - token may be set even if chat_id is not (for auto-detection).
    Returns (None, None) only if token is not configured.
    """
    if not TELEGRAM_BOT_TOKEN:
        return None, None
    # Return token even if chat_id is not set - TelegramPublisher can try auto-detection
    return TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID if TELEGRAM_CHAT_ID else None


def get_telegram_channel_config(channel: str = "free") -> tuple[Optional[str], Optional[str]]:
    """
    Get Telegram bot token and chat ID for specific channel (free/premium).
    
    Args:
        channel: "free" or "premium"
    
    Returns:
        (token, chat_id) or (None, None) if not configured
    
    Raises:
        ValueError: If premium channel requested but not configured
    """
    if not TELEGRAM_BOT_TOKEN:
        return None, None
    
    if channel == "premium":
        if not TELEGRAM_CHAT_ID_PREMIUM:
            raise ValueError("TELEGRAM_CHAT_ID_PREMIUM not configured. Premium channel requires separate chat ID.")
        return TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID_PREMIUM
    else:  # free
        # Use FREE if available, fallback to legacy TELEGRAM_CHAT_ID
        chat_id = TELEGRAM_CHAT_ID_FREE or TELEGRAM_CHAT_ID
        if not chat_id:
            return None, None
        return TELEGRAM_BOT_TOKEN, chat_id


def is_telegram_configured(channel: str = "free") -> bool:
    """Check if Telegram is configured for given channel."""
    try:
        token, chat_id = get_telegram_channel_config(channel)
        return token is not None and chat_id is not None
    except ValueError:
        return False
