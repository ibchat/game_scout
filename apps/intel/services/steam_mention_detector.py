"""
Steam Mention Detector
Detects if text/content is relevant to Steam games.
"""
import re
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

# Steam-related patterns
STEAM_PATTERNS = [
    r'\bsteam\b',  # Word "steam" (case-insensitive)
    r'store\.steampowered\.com',  # Steam store URL
    r'steamcommunity\.com',  # Steam community URL
    r'steamdb\.info',  # SteamDB URL
    r'steam\s+(release|update|sale|discount|launch)',  # Steam + action
    r'on\s+steam',  # "on Steam"
    r'steam\s+game',  # "Steam game"
    r'appid[:\s]*\d+',  # App ID pattern
    r'steam\s+app[/\s]*\d+',  # Steam app URL pattern
]

# Steam store URL patterns
STEAM_URL_PATTERNS = [
    r'store\.steampowered\.com/app/(\d+)',  # /app/123456
    r'steamcommunity\.com/app/(\d+)',  # /app/123456
    r'steamdb\.info/app/(\d+)',  # /app/123456
]


def detect_steam_relevance(text: str) -> Tuple[bool, Optional[str]]:
    """
    Detect if text is relevant to Steam games.
    
    Args:
        text: Text to analyze
    
    Returns:
        (is_relevant: bool, reason: str or None)
        - is_relevant: True if text mentions Steam
        - reason: Brief explanation why it's relevant (or None if not)
    """
    if not text:
        return False, None
    
    text_lower = text.lower()
    
    # Check for Steam URL patterns (strongest signal)
    for pattern in STEAM_URL_PATTERNS:
        match = re.search(pattern, text_lower)
        if match:
            appid = match.group(1) if match.groups() else None
            return True, f"Steam URL detected (appid: {appid})" if appid else "Steam URL detected"
    
    # Check for Steam-related patterns
    for pattern in STEAM_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            matched_text = re.search(pattern, text_lower, re.IGNORECASE).group(0)
            return True, f"Steam mention detected: '{matched_text[:50]}'"
    
    return False, None


def extract_steam_appid(text: str) -> Optional[int]:
    """
    Extract Steam app ID from text if present.
    
    Args:
        text: Text to search
    
    Returns:
        appid (int) or None if not found
    """
    if not text:
        return None
    
    text_lower = text.lower()
    
    for pattern in STEAM_URL_PATTERNS:
        match = re.search(pattern, text_lower)
        if match and match.groups():
            try:
                return int(match.group(1))
            except (ValueError, IndexError):
                continue
    
    # Try to find appid pattern directly
    appid_match = re.search(r'appid[:\s]*(\d+)', text_lower)
    if appid_match:
        try:
            return int(appid_match.group(1))
        except (ValueError, IndexError):
            pass
    
    return None
