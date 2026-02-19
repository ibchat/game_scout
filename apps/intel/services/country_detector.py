"""
Country Detection for Intel Events
Detects country from domain, text, or publisher location.
"""
import logging
import re
from typing import Dict, Optional, Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# Country mapping: code -> (name_ru, emoji)
COUNTRY_MAP = {
    "US": ("США", "🇺🇸"),
    "GB": ("Великобритания", "🇬🇧"),
    "UK": ("Великобритания", "🇬🇧"),
    "DE": ("Германия", "🇩🇪"),
    "FR": ("Франция", "🇫🇷"),
    "ES": ("Испания", "🇪🇸"),
    "IT": ("Италия", "🇮🇹"),
    "PL": ("Польша", "🇵🇱"),
    "BR": ("Бразилия", "🇧🇷"),
    "JP": ("Япония", "🇯🇵"),
    "KR": ("Южная Корея", "🇰🇷"),
    "CN": ("Китай", "🇨🇳"),
    "RU": ("Россия", "🇷🇺"),
    "CA": ("Канада", "🇨🇦"),
    "AU": ("Австралия", "🇦🇺"),
    "NL": ("Нидерланды", "🇳🇱"),
    "SE": ("Швеция", "🇸🇪"),
    "NO": ("Норвегия", "🇳🇴"),
    "FI": ("Финляндия", "🇫🇮"),
    "DK": ("Дания", "🇩🇰"),
    "CZ": ("Чехия", "🇨🇿"),
    "TR": ("Турция", "🇹🇷"),
    "IN": ("Индия", "🇮🇳"),
    "MX": ("Мексика", "🇲🇽"),
    "AR": ("Аргентина", "🇦🇷"),
    "ZA": ("ЮАР", "🇿🇦"),
}

# Domain TLD -> country code mapping
TLD_COUNTRY_MAP = {
    ".us": "US",
    ".uk": "GB",
    ".co.uk": "GB",
    ".de": "DE",
    ".fr": "FR",
    ".es": "ES",
    ".it": "IT",
    ".pl": "PL",
    ".br": "BR",
    ".jp": "JP",
    ".kr": "KR",
    ".cn": "CN",
    ".ru": "RU",
    ".ca": "CA",
    ".au": "AU",
    ".nl": "NL",
    ".se": "SE",
    ".no": "NO",
    ".fi": "FI",
    ".dk": "DK",
    ".cz": "CZ",
    ".tr": "TR",
    ".in": "IN",
    ".mx": "MX",
    ".ar": "AR",
    ".za": "ZA",
}

# Country name patterns in text (case-insensitive)
COUNTRY_PATTERNS = {
    "US": [r"\busa\b", r"\bunited states\b", r"\bсша\b", r"\bамерик\w*"],
    "GB": [r"\buk\b", r"\bbritain\b", r"\bunited kingdom\b", r"\bвеликобритани\w*"],
    "DE": [r"\bgermany\b", r"\bdeutschland\b", r"\bгермани\w*"],
    "FR": [r"\bfrance\b", r"\bfrançais\b", r"\bфранци\w*"],
    "JP": [r"\bjapan\b", r"\bяпони\w*"],
    "KR": [r"\bkorea\b", r"\bюжная корея\b", r"\bкоре\w*"],
    "CN": [r"\bchina\b", r"\bкита\w*"],
    "RU": [r"\brussia\b", r"\bросси\w*"],
    "CA": [r"\bcanada\b", r"\bканад\w*"],
    "AU": [r"\baustralia\b", r"\bавстрали\w*"],
    "BR": [r"\bbrazil\b", r"\bбразили\w*"],
    "PL": [r"\bpoland\b", r"\bпольш\w*"],
    "ES": [r"\bspain\b", r"\bиспани\w*"],
    "IT": [r"\bitaly\b", r"\bитали\w*"],
}


def detect_country_from_domain(url: str) -> Optional[str]:
    """
    Detect country from domain TLD.
    
    Args:
        url: Source URL
    
    Returns:
        Country code or None
    """
    if not url:
        return None
    
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        # Check TLD
        for tld, country_code in TLD_COUNTRY_MAP.items():
            if domain.endswith(tld):
                return country_code
        
        # Check subdomain patterns (e.g., de.news.google.com)
        parts = domain.split(".")
        for part in parts:
            if part in COUNTRY_MAP:
                return part.upper()
        
        # Check common domain patterns
        if "news.google.com" in domain:
            # Google News URLs often have locale in query params
            # But we can't parse query here, so skip
            pass
        
    except Exception as e:
        logger.debug(f"Failed to detect country from domain {url}: {e}")
    
    return None


def detect_country_from_text(text: str) -> Optional[str]:
    """
    Detect country from text content.
    
    Args:
        text: Text to analyze
    
    Returns:
        Country code or None
    """
    if not text:
        return None
    
    text_lower = text.lower()
    
    # Check patterns
    for country_code, patterns in COUNTRY_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return country_code
    
    return None


def detect_country(
    event: Any,
    source_url: Optional[str] = None,
    text: Optional[str] = None
) -> Dict[str, Any]:
    """
    Detect country for Intel event.
    
    Priority:
    1. Domain TLD
    2. Text content
    3. Publisher location (if available in event metadata)
    4. Fallback to Global
    
    Args:
        event: IntelEvent object
        source_url: Source URL (optional, will use event.sources if not provided)
        text: Text content (optional, will use event fields if not provided)
    
    Returns:
        Dict with country_code, country_name_ru, emoji
    """
    country_code = None
    
    # Priority 1: Domain TLD
    source_url_to_check = source_url
    if not source_url_to_check and event and hasattr(event, 'sources') and event.sources:
        if isinstance(event.sources, list) and event.sources:
            source_url_to_check = event.sources[0]
        elif isinstance(event.sources, str):
            source_url_to_check = event.sources
    
    if source_url_to_check:
        country_code = detect_country_from_domain(source_url_to_check)
    
    # Priority 2: Text content
    if not country_code:
        if text:
            country_code = detect_country_from_text(text)
        elif event:
            # Combine event text fields
            event_text = ""
            if hasattr(event, 'title_ru') and event.title_ru:
                event_text += " " + event.title_ru
            if hasattr(event, 'what_happened_ru') and event.what_happened_ru:
                event_text += " " + event.what_happened_ru
            if event_text:
                country_code = detect_country_from_text(event_text)
    
    # Priority 3: Publisher location (from metadata)
    if not country_code and event and hasattr(event, 'llm_meta') and event.llm_meta:
        publisher_location = event.llm_meta.get("publisher_location")
        if publisher_location:
            country_code = detect_country_from_text(publisher_location)
    
    # Fallback to Global
    if not country_code:
        return {
            "country_code": "GLOBAL",
            "country_name_ru": "Глобально",
            "emoji": "🌍"
        }
    
    # Get country info
    country_info = COUNTRY_MAP.get(country_code)
    if country_info:
        country_name_ru, emoji = country_info
        return {
            "country_code": country_code,
            "country_name_ru": country_name_ru,
            "emoji": emoji
        }
    else:
        # Unknown country code, return as-is with default emoji
        return {
            "country_code": country_code,
            "country_name_ru": country_code,
            "emoji": "🌍"
        }
