"""
Steam Mention Detector (Enhanced)
Detects if text/content is relevant to Steam games with scoring.
"""
import re
import logging
from typing import Tuple, Optional, List, Dict

logger = logging.getLogger(__name__)

# Steam-related patterns with weights (BROAD DETECTION)
STEAM_PATTERNS = [
    (r'\bsteam\b', 20),  # Word "steam" (case-insensitive)
    (r'store\.steampowered\.com', 100),  # Steam store URL (strongest)
    (r'steamcommunity\.com', 90),  # Steam community URL
    (r'steamdb\.info', 85),  # SteamDB URL
    (r'steampowered\.com', 95),  # Steam powered domain
    (r'steam\s+(release|update|sale|discount|launch|game|works|os|deck)', 50),  # Steam + keyword
    (r'on\s+steam', 40),  # "on Steam"
    (r'steam\s+game', 45),  # "Steam game"
    (r'appid[:\s]*\d+', 60),  # App ID pattern
    (r'steam\s+app[/\s]*\d+', 70),  # Steam app URL pattern
    (r'\bvalve\b', 30),  # Valve mention
    (r'steam\s+deck', 50),  # Steam Deck
    (r'steam\s+store', 40),  # Steam store
    (r'steam\s+community', 35),  # Steam community
    (r'steamworks', 45),  # Steamworks
    (r'steamos', 40),  # SteamOS
    (r'wishlist', 30),  # Wishlist (Steam context)
    (r'early\s+access', 35),  # Early Access (Steam context)
    (r'pc\s+game', 25),  # PC game (Steam context)
    (r'indie\s+game', 25),  # Indie game (Steam context)
    (r'publisher', 20),  # Publisher (Steam context)
    (r'launch', 20),  # Launch (Steam context)
    (r'patch', 20),  # Patch (Steam context)
    (r'update', 20),  # Update (Steam context)
    (r'bundle', 25),  # Bundle (Steam context)
]

# Steam store URL patterns (highest weight)
STEAM_URL_PATTERNS = [
    (r'store\.steampowered\.com/app/(\d+)', 100),  # /app/123456
    (r'steamcommunity\.com/app/(\d+)', 95),  # /app/123456
    (r'steamdb\.info/app/(\d+)', 90),  # /app/123456
    (r'steam:\/\/run\/(\d+)', 85),  # steam://run/123456
]


def detect_steam_relevance(text: str, min_score: int = 30) -> Tuple[bool, Optional[str], int, List[str]]:
    """
    Detect if text is relevant to Steam games with scoring.
    
    Args:
        text: Text to analyze
        min_score: Minimum relevance score (0-100) to consider relevant
    
    Returns:
        (is_relevant: bool, reason: str or None, score: int, matched_keywords: List[str])
        - is_relevant: True if score >= min_score
        - reason: Brief explanation why it's relevant
        - score: Relevance score (0-100)
        - matched_keywords: List of matched keywords/patterns
    """
    if not text:
        return False, None, 0, []
    
    text_lower = text.lower()
    score = 0
    matched_keywords = []
    reasons = []
    
    # Check for Steam URL patterns (strongest signal)
    for pattern, weight in STEAM_URL_PATTERNS:
        match = re.search(pattern, text_lower)
        if match:
            appid = match.group(1) if match.groups() else None
            score = max(score, weight)
            matched_keywords.append(f"steam_url_{pattern[:30]}")
            if appid:
                reasons.append(f"Steam URL with appid {appid}")
            else:
                reasons.append("Steam URL detected")
    
    # Check for Steam-related patterns
    for pattern, weight in STEAM_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            score = max(score, weight)
            matched_text = re.search(pattern, text_lower, re.IGNORECASE).group(0)
            matched_keywords.append(matched_text[:50])
            if not reasons:
                reasons.append(f"Steam mention: '{matched_text[:50]}'")
    
    # Cap score at 100
    score = min(score, 100)
    
    is_relevant = score >= min_score
    reason = "; ".join(reasons) if reasons else None
    
    return is_relevant, reason, score, matched_keywords


def detect_steam_relevance_legacy(text: str) -> Tuple[bool, Optional[str]]:
    """
    Legacy function for backward compatibility.
    Returns (is_relevant, reason) without scoring.
    """
    is_relevant, reason, score, keywords = detect_steam_relevance(text)
    return is_relevant, reason


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
    
    # Ensure text is a string
    if not isinstance(text, str):
        text = str(text)
    
    text_lower = text.lower()
    
    for pattern_item in STEAM_URL_PATTERNS:
        # STEAM_URL_PATTERNS is list of tuples (pattern, weight)
        if isinstance(pattern_item, tuple):
            pattern = pattern_item[0]
        else:
            pattern = pattern_item
        
        # Ensure pattern is a string or compiled regex
        if isinstance(pattern, str):
            match = re.search(pattern, text_lower)
        else:
            match = pattern.search(text_lower)
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
