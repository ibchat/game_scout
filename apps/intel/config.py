"""
Intel Module Configuration
Feature flags and settings for Intel subsystem.
"""
import os
from typing import Optional

# Feature flags (all default to safe/disabled)
INTEL_ENABLED = os.getenv("INTEL_ENABLED", "false").lower() == "true"
INTEL_DRY_RUN = os.getenv("INTEL_DRY_RUN", "true").lower() == "true"
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
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

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
    """Get Telegram bot token and chat ID. Returns (token, chat_id) or (None, None) if not configured."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return None, None
    return TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
