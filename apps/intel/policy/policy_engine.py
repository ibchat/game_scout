"""
Intel Policy Engine
Loads and enforces policy rules from intel_policy.yaml
"""
import logging
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, Literal
from urllib.parse import urlparse
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text

from apps.intel.config import (
    INTEL_ENABLED,
    INTEL_SOURCES_ALLOWLIST_ONLY,
    INTEL_AUTO_PUBLISH_SAFE_ONLY,
    INTEL_MAX_POSTS_PER_HOUR,
    INTEL_MAX_POSTS_PER_DAY
)

logger = logging.getLogger(__name__)

# Policy cache
_policy_cache: Optional[Dict[str, Any]] = None
_policy_hash: Optional[str] = None
_policy_loaded_at: Optional[datetime] = None


def get_policy_path() -> Path:
    """Get path to intel_policy.yaml file."""
    # __file__ = apps/intel/policy/policy_engine.py
    # .parent = apps/intel/policy
    # .parent.parent = apps/intel
    # .parent.parent.parent = apps
    # .parent.parent.parent.parent = root
    current_file = Path(__file__)
    policy_path = current_file.parent / "intel_policy.yaml"
    
    # Fallback: try relative to current working directory
    if not policy_path.exists():
        policy_path = Path("apps/intel/policy/intel_policy.yaml")
    
    return policy_path


def load_policy() -> Dict[str, Any]:
    """
    Load policy from intel_policy.yaml.
    Caches policy in memory and reloads if file changes.
    """
    global _policy_cache, _policy_hash, _policy_loaded_at
    
    policy_path = get_policy_path()
    
    if not policy_path.exists():
        logger.error(f"Policy file not found: {policy_path}")
        return _get_default_policy()
    
    # Read file and compute hash
    try:
        with open(policy_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        
        # Reload if hash changed or not cached
        if _policy_cache is None or _policy_hash != content_hash:
            try:
                import yaml
                _policy_cache = yaml.safe_load(content)
            except ImportError:
                # Fallback: simple YAML parsing for basic structure
                logger.warning("PyYAML not available, using fallback parser")
                _policy_cache = _parse_yaml_simple(content)
            
            _policy_hash = content_hash
            _policy_loaded_at = datetime.utcnow()
            logger.info(f"Policy loaded from {policy_path} (hash: {content_hash})")
        
        return _policy_cache
    except Exception as e:
        logger.error(f"Failed to load policy: {e}", exc_info=True)
        return _get_default_policy()


def _parse_yaml_simple(content: str) -> Dict[str, Any]:
    """
    Simple YAML parser fallback (basic structure only).
    Used when PyYAML is not available.
    """
    # Very basic parser for MVP - just return default if PyYAML unavailable
    logger.warning("Using default policy (PyYAML not available for parsing)")
    return _get_default_policy()


def _get_default_policy() -> Dict[str, Any]:
    """Return default policy if file cannot be loaded."""
    return {
        "version": "1.0",
        "allowed_domains": [],
        "blocked_domains": [],
        "allowed_event_types_for_autopublish": [
            "release", "patch_major", "discount", "publisher_deal", "funding", "market_trend"
        ],
        "always_needs_review_event_types": ["controversy"],
        "hard_rules": {
            "no_fabrication": True,
            "numbers_must_come_from": ["steam_snapshot", "extracted_text", "key_facts"],
            "if_missing_data_write": "нет данных",
            "output_language": "ru"
        },
        "telegram_template": {
            "max_chars": 3500,
            "format": ["title", "what_happened", "why_it_matters", "bullets", "sources"]
        },
        "limits": {
            "max_posts_per_hour": 5,
            "max_posts_per_day": 30
        },
        "moderation": {
            "unresolved_entity_policy": "needs_review",
            "low_confidence_threshold": 0.75
        }
    }


def get_policy_hash() -> Optional[str]:
    """Get current policy hash."""
    load_policy()  # Ensure policy is loaded
    return _policy_hash


def validate_source_url(url: str) -> Tuple[Literal["allow", "deny"], str]:
    """
    Validate source URL against policy.
    Returns: (decision, reason)
    """
    if not url:
        return "deny", "Empty URL"
    
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        # Remove port if present
        if ':' in domain:
            domain = domain.split(':')[0]
        
        # Remove www. prefix
        if domain.startswith('www.'):
            domain = domain[4:]
        
        policy = load_policy()
        
        # Check blocked domains first
        blocked = policy.get("blocked_domains", [])
        if domain in blocked or any(domain.endswith(f".{b}") for b in blocked):
            return "deny", f"Domain {domain} is in blocked list"
        
        # Check allowlist if enabled
        if INTEL_SOURCES_ALLOWLIST_ONLY:
            allowed = policy.get("allowed_domains", [])
            if not allowed:
                # Empty allowlist with allowlist_only=true means deny all
                return "deny", "Allowlist is empty and INTEL_SOURCES_ALLOWLIST_ONLY=true"
            
            if domain not in allowed and not any(domain.endswith(f".{a}") for a in allowed):
                return "deny", f"Domain {domain} not in allowed list"
        
        return "allow", "OK"
    except Exception as e:
        logger.error(f"Error validating URL {url}: {e}", exc_info=True)
        return "deny", f"Validation error: {str(e)}"


def validate_event(event_payload: Dict[str, Any]) -> Tuple[Literal["ok", "needs_review", "deny"], str]:
    """
    Validate event against policy.
    Returns: (decision, reason)
    """
    policy = load_policy()
    event_type = event_payload.get("event_type", "")
    
    # Check if event type always needs review
    needs_review_types = policy.get("always_needs_review_event_types", [])
    if event_type in needs_review_types:
        return "needs_review", f"Event type '{event_type}' always requires review"
    
    # Check for unresolved entities
    steam_appid = event_payload.get("steam_appid")
    if steam_appid is None:
        unresolved_policy = policy.get("moderation", {}).get("unresolved_entity_policy", "needs_review")
        if unresolved_policy == "needs_review":
            return "needs_review", "Unresolved entity (no steam_appid)"
        elif unresolved_policy == "deny":
            return "deny", "Unresolved entity (no steam_appid) - denied by policy"
    
    # Check confidence threshold
    confidence = event_payload.get("confidence", 1.0)
    min_confidence = policy.get("moderation", {}).get("low_confidence_threshold", 0.75)
    if confidence < min_confidence:
        return "needs_review", f"Low confidence {confidence:.2f} < {min_confidence}"
    
    return "ok", "OK"


def validate_summary(summary_json: Dict[str, Any], fact_whitelist: list) -> Tuple[Literal["ok", "needs_review"], str]:
    """
    Validate summary against fact whitelist.
    Checks that no numbers/facts are fabricated.
    Returns: (decision, reason)
    """
    policy = load_policy()
    hard_rules = policy.get("hard_rules", {})
    
    if not hard_rules.get("no_fabrication", True):
        return "ok", "Fabrication check disabled"
    
    # Extract all numbers from summary
    import re
    summary_text = str(summary_json)
    numbers = re.findall(r'\d+\.?\d*', summary_text)
    
    # Check if numbers are in fact whitelist or metadata
    fact_text = " ".join(str(f) for f in fact_whitelist)
    metadata = summary_json.get("llm_meta", {})
    metadata_text = str(metadata)
    
    for num in numbers:
        if num not in fact_text and num not in metadata_text:
            # Number not found in whitelist - needs review
            return "needs_review", f"Number {num} not found in fact whitelist or metadata"
    
    return "ok", "OK"


def enforce_rate_limits(stats: Dict[str, Any], db: Optional[Session] = None) -> Tuple[Literal["allow", "deny"], str]:
    """
    Enforce rate limits based on policy.
    stats should contain: posts_per_hour, posts_per_day
    Returns: (decision, reason)
    """
    policy = load_policy()
    limits = policy.get("limits", {})
    
    max_per_hour = limits.get("max_posts_per_hour", INTEL_MAX_POSTS_PER_HOUR)
    max_per_day = limits.get("max_posts_per_day", INTEL_MAX_POSTS_PER_DAY)
    
    posts_per_hour = stats.get("posts_per_hour", 0)
    posts_per_day = stats.get("posts_per_day", 0)
    
    if posts_per_hour >= max_per_hour:
        return "deny", f"Rate limit exceeded: {posts_per_hour}/{max_per_hour} posts per hour"
    
    if posts_per_day >= max_per_day:
        return "deny", f"Rate limit exceeded: {posts_per_day}/{max_per_day} posts per day"
    
    return "allow", "OK"


def should_autopublish(event: Dict[str, Any]) -> bool:
    """
    Check if event should be auto-published based on policy.
    Takes into account INTEL_AUTO_PUBLISH_SAFE_ONLY flag.
    """
    if not INTEL_ENABLED:
        return False
    
    policy = load_policy()
    event_type = event.get("event_type", "")
    
    # Check if event type is in allowed list
    allowed_types = policy.get("allowed_event_types_for_autopublish", [])
    
    if INTEL_AUTO_PUBLISH_SAFE_ONLY:
        # Only allow safe event types
        return event_type in allowed_types
    else:
        # Allow all except those that need review
        needs_review_types = policy.get("always_needs_review_event_types", [])
        return event_type not in needs_review_types


def log_policy_decision(
    db: Session,
    decision: str,
    reason: str,
    details: Optional[Dict[str, Any]] = None
) -> None:
    """
    Log policy decision to intel_audit_log table.
    """
    try:
        from apps.intel.db.models import IntelAuditLog
        import uuid
        
        audit_entry = IntelAuditLog(
            id=uuid.uuid4(),
            created_at=datetime.utcnow(),
            status=decision,
            details=details or {}
        )
        
        db.add(audit_entry)
        db.commit()
        logger.debug(f"Policy decision logged: {decision} - {reason}")
    except Exception as e:
        logger.error(f"Failed to log policy decision: {e}", exc_info=True)
        db.rollback()
