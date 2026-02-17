"""
Discord Invite Link Extractor
Extracts Discord invite codes from text using regex patterns
"""
import re
from typing import List, Set
from urllib.parse import urlparse, parse_qs


def extract_discord_invites(text: str) -> List[str]:
    """
    Extract Discord invite codes from text.
    
    Supports:
    - discord.gg/<code>
    - discord.com/invite/<code>
    - https://discord.gg/...
    - https://discord.com/invite/...
    
    Returns:
        List of normalized invite codes (unique, lowercase)
    """
    if not text:
        return []
    
    invite_codes: Set[str] = set()
    
    # Pattern 1: discord.gg/<code> or discord.com/invite/<code>
    # Matches: discord.gg/abc123, discord.com/invite/abc123, https://discord.gg/abc123, etc.
    pattern1 = r'(?:https?://)?(?:www\.)?discord\.(?:gg|com/invite)/([a-zA-Z0-9]+)'
    
    for match in re.finditer(pattern1, text, re.IGNORECASE):
        code = match.group(1).lower().strip()
        if code and len(code) >= 3:  # Minimum reasonable invite code length
            invite_codes.add(code)
    
    # Pattern 2: discord.gg/<code>?param=value (extract code before query params)
    pattern2 = r'(?:https?://)?(?:www\.)?discord\.(?:gg|com/invite)/([a-zA-Z0-9]+)(?:\?|/|$)'
    
    for match in re.finditer(pattern2, text, re.IGNORECASE):
        code = match.group(1).lower().strip()
        if code and len(code) >= 3:
            invite_codes.add(code)
    
    # Pattern 3: Try to extract from full URLs with query params
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+discord\.(?:gg|com/invite)/[a-zA-Z0-9]+'
    for url_match in re.finditer(url_pattern, text, re.IGNORECASE):
        try:
            parsed = urlparse(url_match.group(0))
            # Extract code from path
            path_parts = parsed.path.strip('/').split('/')
            if path_parts:
                code = path_parts[-1].lower().strip()
                if code and len(code) >= 3:
                    invite_codes.add(code)
        except Exception:
            pass
    
    return sorted(list(invite_codes))


def normalize_invite_code(code: str) -> str:
    """
    Normalize invite code to standard format.
    
    Args:
        code: Raw invite code (may contain query params, etc.)
        
    Returns:
        Normalized invite code (lowercase, no query params)
    """
    if not code:
        return ""
    
    # Remove query params if present
    code = code.split('?')[0].split('#')[0]
    
    # Extract from URL if needed
    if '/' in code:
        code = code.split('/')[-1]
    
    return code.lower().strip()


def build_invite_url(code: str) -> str:
    """
    Build standard Discord invite URL from code.
    
    Args:
        code: Normalized invite code
        
    Returns:
        Full invite URL (discord.gg format)
    """
    return f"https://discord.gg/{code}"
