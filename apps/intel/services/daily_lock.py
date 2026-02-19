"""
Daily run lock for Intel pipeline.
Prevents duplicate runs on the same day using Redis.
"""
import os
import logging
import redis
from datetime import datetime, timedelta
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Redis connection
REDIS_URL = os.getenv("REDIS_URL") or os.getenv("CELERY_BROKER_URL") or "redis://redis:6379/0"

# Lock key prefix
DAILY_LOCK_KEY_PREFIX = "gs:intel:daily_run:"
LOCK_TTL_HOURS = 26  # TTL 26 hours to cover edge cases


def get_redis_client() -> Optional[redis.Redis]:
    """Get Redis client."""
    try:
        return redis.from_url(REDIS_URL, decode_responses=True)
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        return None


def get_daily_lock_key(date_str: Optional[str] = None) -> str:
    """
    Get daily lock key for a specific date.
    
    Args:
        date_str: Date in YYYY-MM-DD format. If None, uses today in Europe/Madrid timezone.
    
    Returns:
        Redis key string
    """
    if date_str is None:
        tz = ZoneInfo(os.getenv("INTEL_DAILY_RUN_TZ", "Europe/Madrid"))
        today = datetime.now(tz).date()
        date_str = today.isoformat()
    
    return f"{DAILY_LOCK_KEY_PREFIX}{date_str}"


def acquire_daily_lock(date_str: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """
    Try to acquire daily lock.
    
    Args:
        date_str: Date in YYYY-MM-DD format. If None, uses today.
    
    Returns:
        (success: bool, lock_key: str or None)
    """
    redis_client = get_redis_client()
    if not redis_client:
        logger.warning("Redis unavailable, cannot acquire daily lock - allowing run")
        return True, None  # Allow run if Redis is down
    
    lock_key = get_daily_lock_key(date_str)
    
    try:
        # Try to set key with TTL (SET NX - only if not exists)
        ttl_seconds = LOCK_TTL_HOURS * 3600
        acquired = redis_client.set(lock_key, datetime.utcnow().isoformat(), ex=ttl_seconds, nx=True)
        
        if acquired:
            logger.info(f"Daily lock acquired: {lock_key}")
            return True, lock_key
        else:
            existing_value = redis_client.get(lock_key)
            logger.info(f"Daily lock already exists: {lock_key} (set at {existing_value})")
            return False, lock_key
    except Exception as e:
        logger.error(f"Failed to acquire daily lock: {e}")
        return False, lock_key


def check_daily_lock(date_str: Optional[str] = None) -> bool:
    """
    Check if daily lock exists (without acquiring).
    
    Args:
        date_str: Date in YYYY-MM-DD format. If None, uses today.
    
    Returns:
        True if lock exists, False otherwise
    """
    redis_client = get_redis_client()
    if not redis_client:
        return False
    
    lock_key = get_daily_lock_key(date_str)
    
    try:
        exists = redis_client.exists(lock_key)
        return bool(exists)
    except Exception as e:
        logger.error(f"Failed to check daily lock: {e}")
        return False


def release_daily_lock(date_str: Optional[str] = None) -> bool:
    """
    Release daily lock (for testing/debugging).
    
    Args:
        date_str: Date in YYYY-MM-DD format. If None, uses today.
    
    Returns:
        True if released, False otherwise
    """
    redis_client = get_redis_client()
    if not redis_client:
        return False
    
    lock_key = get_daily_lock_key(date_str)
    
    try:
        deleted = redis_client.delete(lock_key)
        logger.info(f"Daily lock released: {lock_key}")
        return bool(deleted)
    except Exception as e:
        logger.error(f"Failed to release daily lock: {e}")
        return False
