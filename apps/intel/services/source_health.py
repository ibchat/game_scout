"""
Source Health Tracking
Tracks source errors and auto-disables sources with repeated failures.
Uses new DB fields: failure_streak, last_error_code, backoff_until, disabled_reason, etc.
"""
import logging
from typing import Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from apps.intel.db.models import IntelSource

logger = logging.getLogger(__name__)

# Thresholds
MAX_404_410_FAILURES = 3  # Auto-disable after 3 consecutive 404/410
MAX_403_BACKOFF_HOURS = 24  # Backoff period for 403 errors
MAX_403_FAILURES_BEFORE_DISABLE = 10  # Disable after 10 403 errors (not just backoff)
MAX_5XX_BACKOFF_HOURS = 6  # Max backoff for 5xx errors (exponential, max 6h)


def track_source_error(
    db: Session,
    source: IntelSource,
    error_code: Optional[int] = None,
    error_message: Optional[str] = None
) -> None:
    """
    Track source error and update health status using DB fields.
    
    Args:
        db: Database session
        source: IntelSource to track
        error_code: HTTP status code (404, 410, 403, 5xx, etc.)
        error_message: Error message
    """
    try:
        now = datetime.utcnow()
        source.last_error_code = error_code
        
        if error_code in [404, 410]:
            # Track consecutive 404/410 failures
            source.failure_streak = (source.failure_streak or 0) + 1
            
            if source.failure_streak >= MAX_404_410_FAILURES:
                logger.warning(f"Source {source.name} ({source.url}) has {source.failure_streak} consecutive {error_code} errors - disabling")
                source.is_enabled = False
                source.disabled_reason = f"HTTP {error_code} errors ({source.failure_streak} consecutive failures)"
                source.disabled_at = now
                db.commit()
                logger.info(f"Source {source.name} disabled: {source.disabled_reason}")
        
        elif error_code == 403:
            # 403: backoff, don't disable immediately
            source.failure_streak = (source.failure_streak or 0) + 1
            source.blocked_reason = f"HTTP 403 Forbidden (streak: {source.failure_streak})"
            
            # Set backoff until 24h from now
            source.backoff_until = now + timedelta(hours=MAX_403_BACKOFF_HOURS)
            
            # Disable if too many 403s
            if source.failure_streak >= MAX_403_FAILURES_BEFORE_DISABLE:
                logger.warning(f"Source {source.name} has {source.failure_streak} 403 errors - disabling")
                source.is_enabled = False
                source.disabled_reason = f"HTTP 403 Forbidden ({source.failure_streak} failures)"
                source.disabled_at = now
            
            db.commit()
            logger.warning(f"Source {source.name} ({source.url}) returned 403 - backoff until {source.backoff_until}")
        
        elif error_code and 500 <= error_code < 600:
            # 5xx: exponential backoff (max 6h)
            source.failure_streak = (source.failure_streak or 0) + 1
            backoff_hours = min(MAX_5XX_BACKOFF_HOURS, 2 ** min(source.failure_streak - 1, 3))  # 1h, 2h, 4h, 6h max
            source.backoff_until = now + timedelta(hours=backoff_hours)
            source.blocked_reason = f"HTTP {error_code} Server Error (backoff {backoff_hours}h)"
            db.commit()
            logger.warning(f"Source {source.name} returned {error_code} - backoff {backoff_hours}h until {source.backoff_until}")
        
        else:
            # Other errors: increment streak but don't disable
            source.failure_streak = (source.failure_streak or 0) + 1
            db.commit()
        
    except Exception as e:
        logger.error(f"Failed to track source error: {e}", exc_info=True)
        db.rollback()


def should_skip_source_due_to_backoff(
    db: Session,
    source: IntelSource,
    error_code: Optional[int] = None
) -> Tuple[bool, Optional[str]]:
    """
    Check if source should be skipped due to backoff or disabled status.
    
    Returns:
        (should_skip: bool, reason: str or None)
    """
    now = datetime.utcnow()
    
    # Check if disabled
    if not source.is_enabled:
        if source.disabled_reason:
            return True, f"Source disabled: {source.disabled_reason}"
        return True, "Source disabled"
    
    # Check backoff period
    if source.backoff_until and source.backoff_until > now:
        remaining = source.backoff_until - now
        hours = remaining.total_seconds() / 3600
        return True, f"Source in backoff period (expires in {hours:.1f}h): {source.blocked_reason or 'HTTP error'}"
    
    # Clear backoff if expired
    if source.backoff_until and source.backoff_until <= now:
        source.backoff_until = None
        source.blocked_reason = None
        db.commit()
    
    return False, None


def reset_source_health_on_success(db: Session, source: IntelSource) -> None:
    """
    Reset source health tracking on successful collection.
    """
    try:
        now = datetime.utcnow()
        
        # Reset failure streak
        source.failure_streak = 0
        source.last_success_at = now
        source.last_error_code = None
        
        # Clear backoff if set
        if source.backoff_until:
            source.backoff_until = None
            source.blocked_reason = None
        
        # If source was auto-disabled but now succeeds, consider re-enabling
        # (but only if it was auto-disabled, not manually disabled)
        if not source.is_enabled and source.disabled_reason and "HTTP" in source.disabled_reason:
            logger.info(f"Source {source.name} succeeded after auto-disable - consider re-enabling manually")
        
        db.commit()
        
    except Exception as e:
        logger.error(f"Failed to reset source health: {e}", exc_info=True)
        db.rollback()
