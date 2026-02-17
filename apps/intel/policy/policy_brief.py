"""
Intel Policy Brief
Compiles YAML policy into short text for LLM prompts (≤ 2000-3000 chars).
Ensures LLM sees rules on every call.
"""
import logging
from typing import Optional

from apps.intel.policy.policy_engine import load_policy

logger = logging.getLogger(__name__)

# Cache for compiled brief
_policy_brief_cache: Optional[str] = None
_policy_brief_hash: Optional[str] = None


def get_policy_brief() -> str:
    """
    Compile policy YAML into short text for LLM prompts.
    Returns policy brief (≤ 3000 characters).
    """
    global _policy_brief_cache, _policy_brief_hash
    
    from apps.intel.policy.policy_engine import get_policy_hash
    
    current_hash = get_policy_hash()
    
    # Return cached if hash matches
    if _policy_brief_cache and _policy_brief_hash == current_hash:
        return _policy_brief_cache
    
    policy = load_policy()
    
    brief_parts = []
    
    # Header
    brief_parts.append("=== INTEL POLICY (STRICT RULES) ===\n")
    
    # Hard rules
    hard_rules = policy.get("hard_rules", {})
    brief_parts.append("HARD RULES:")
    brief_parts.append(f"- NO FABRICATION: {hard_rules.get('no_fabrication', True)}")
    brief_parts.append(f"- Numbers must come from: {', '.join(hard_rules.get('numbers_must_come_from', []))}")
    brief_parts.append(f"- If missing data, write: '{hard_rules.get('if_missing_data_write', 'нет данных')}'")
    brief_parts.append(f"- Output language: {hard_rules.get('output_language', 'ru')}")
    brief_parts.append("")
    
    # Event types
    brief_parts.append("EVENT TYPES:")
    allowed_autopublish = policy.get("allowed_event_types_for_autopublish", [])
    brief_parts.append(f"- Auto-publish allowed: {', '.join(allowed_autopublish)}")
    needs_review = policy.get("always_needs_review_event_types", [])
    brief_parts.append(f"- Always needs review: {', '.join(needs_review)}")
    brief_parts.append("")
    
    # Moderation
    moderation = policy.get("moderation", {})
    brief_parts.append("MODERATION:")
    brief_parts.append(f"- Unresolved entity policy: {moderation.get('unresolved_entity_policy', 'needs_review')}")
    brief_parts.append(f"- Low confidence threshold: {moderation.get('low_confidence_threshold', 0.75)}")
    brief_parts.append("")
    
    # Limits
    limits = policy.get("limits", {})
    brief_parts.append("RATE LIMITS:")
    brief_parts.append(f"- Max posts per hour: {limits.get('max_posts_per_hour', 5)}")
    brief_parts.append(f"- Max posts per day: {limits.get('max_posts_per_day', 30)}")
    brief_parts.append("")
    
    # Critical instructions
    brief_parts.append("CRITICAL INSTRUCTIONS:")
    brief_parts.append("- DO NOT invent facts or numbers")
    brief_parts.append("- DO NOT add information not present in input")
    brief_parts.append("- If data is missing, write 'нет данных' (not 'unknown' or 'N/A')")
    brief_parts.append("- All numbers must be from: extracted_text, key_facts, or steam_snapshot")
    brief_parts.append("- Output must be in Russian (ru)")
    brief_parts.append("- If unsure about any fact, write 'нет данных'")
    brief_parts.append("")
    
    brief_parts.append("=== END POLICY ===")
    
    compiled = "\n".join(brief_parts)
    
    # Ensure it's within limit
    max_chars = 3000
    if len(compiled) > max_chars:
        logger.warning(f"Policy brief exceeds {max_chars} chars ({len(compiled)}), truncating")
        compiled = compiled[:max_chars] + "\n... (truncated)"
    
    # Cache
    _policy_brief_cache = compiled
    _policy_brief_hash = current_hash
    
    logger.debug(f"Policy brief compiled ({len(compiled)} chars)")
    
    return compiled


def get_policy_brief_for_llm() -> str:
    """
    Get policy brief formatted for LLM prompt insertion.
    Adds clear markers for LLM to recognize policy section.
    """
    brief = get_policy_brief()
    return f"\n\n{brief}\n\n"


def clear_policy_brief_cache() -> None:
    """Clear policy brief cache (for testing/reloading)."""
    global _policy_brief_cache, _policy_brief_hash
    _policy_brief_cache = None
    _policy_brief_hash = None
