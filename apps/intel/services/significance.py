"""
Significance Scoring for Intel Events
Rules-based scoring to determine event importance for publication.
"""
import logging
import re
from typing import Tuple, Optional
from apps.intel.db.models import IntelEvent, IntelExtractedItem

logger = logging.getLogger(__name__)


def score_event(
    event: IntelEvent,
    extracted: Optional[IntelExtractedItem] = None,
    policy: dict = None
) -> Tuple[int, str, str, float]:
    """
    Calculate significance score for an Intel event with source weighting.
    
    Args:
        event: IntelEvent to score
        extracted: Optional IntelExtractedItem with extracted text
        policy: Policy dict (optional, for future use)
    
    Returns:
        (score: int, reason: str, category: str, confidence: float)
        - score: 0-100
        - reason: Brief explanation
        - category: release, patch_major, discount, publisher_deal, funding, market_trend, controversy, other
        - confidence: 0.0-1.0
    """
    # Get text for analysis
    text = ""
    if extracted and extracted.text:
        text = extracted.text
    elif event.what_happened_ru:
        text = event.what_happened_ru
    elif event.title_ru:
        text = event.title_ru
    
    text_lower = text.lower()
    
    # Determine category (use event_type if available, otherwise classify)
    category = event.event_type if event.event_type else "other"
    
    # If category is "other", try to classify from text
    if category == "other":
        category = _classify_category_from_text(text_lower)
    
    # FALLBACK: If still "other" and no text, use market_trend as default
    if category == "other" and not text_lower:
        category = "market_trend"
    
    # Calculate base score based on category
    score, reason, confidence = _calculate_score_by_category(category, text_lower, event)
    
    # CRITICAL FIX: Ensure minimum baseline score = 25 (no score=0 events)
    if score == 0:
        score = 25  # Baseline for any event
        reason = "Базовый балл события"
        confidence = 0.5
    
    # Apply category weight boost
    category_boost = _get_category_weight(category)
    if category_boost == 0:
        category_boost = 5  # Default category weight if not found
    score = min(100, score + category_boost)
    
    # Apply source weighting (HIGH-NOISE MODE)
    source_boost = _calculate_source_boost(event, extracted)
    if source_boost == 0:
        source_boost = 2  # Default source weight if not found
    score = min(100, score + source_boost)
    
    # Apply recency boost (last 24h)
    recency_boost = _calculate_recency_boost(event, extracted)
    score = min(100, score + recency_boost)
    
    # Final safety: ensure score >= 25
    if score < 25:
        score = 25
    
    if category_boost > 0 or source_boost > 0 or recency_boost > 0:
        boosts = []
        if category_boost > 0:
            boosts.append(f"+{category_boost} категория")
        if source_boost > 0:
            boosts.append(f"+{source_boost} источник")
        if recency_boost > 0:
            boosts.append(f"+{recency_boost} свежесть")
        reason = f"{reason} ({', '.join(boosts)})"
    
    return score, reason, category, confidence


def _get_category_weight(category: str) -> int:
    """
    Get category weight boost for significance scoring.
    
    Returns:
        Boost amount (0-15)
    """
    weights = {
        "release": 10,
        "funding": 15,
        "publisher_deal": 12,
        "market_trend": 8,
        "controversy": 10,
        "discount": 5,
        "patch_major": 8,
        "early_access": 6,
        "other": 0
    }
    return weights.get(category, 0)


def _calculate_recency_boost(event: IntelEvent, extracted: Optional[IntelExtractedItem] = None) -> int:
    """
    Calculate recency boost (last 24h events get boost).
    Uses extracted_at if available (for proper daily run filtering), otherwise event.created_at.
    
    Returns:
        Boost amount (0-10)
    """
    from datetime import datetime, timedelta, timezone
    
    # Prefer extracted_at for recency (proper daily run filtering)
    reference_time = None
    if extracted and hasattr(extracted, 'extracted_at') and extracted.extracted_at:
        reference_time = extracted.extracted_at
    elif event.created_at:
        reference_time = event.created_at
    
    if not reference_time:
        return 0
    
    now = datetime.now(timezone.utc)
    age_hours = (now - reference_time).total_seconds() / 3600
    
    if age_hours <= 24:
        return 10  # Full boost for last 24h
    elif age_hours <= 48:
        return 5   # Half boost for 24-48h
    else:
        return 0   # No boost for older


def _calculate_source_boost(event: IntelEvent, extracted: Optional[IntelExtractedItem] = None) -> int:
    """
    Calculate source-based boost for significance score.
    
    Returns:
        Boost amount (0-20)
    """
    boost = 0
    
    # Get source URL from event or extracted item
    source_url = ""
    if event.sources and isinstance(event.sources, list) and len(event.sources) > 0:
        source_url = event.sources[0]
    elif extracted and extracted.url_norm:
        source_url = extracted.url_norm
    
    if not source_url:
        return 0
    
    source_lower = source_url.lower()
    
    # Official Steam sources: +10
    official_steam_domains = [
        "store.steampowered.com",
        "steamcommunity.com",
        "rss.steampowered.com"
    ]
    if any(domain in source_lower for domain in official_steam_domains):
        boost = 10
        return boost
    
    # SteamDB: +8
    if "steamdb.info" in source_lower:
        boost = 8
        return boost
    
    # Major gaming media: +5
    major_media_domains = [
        "pcgamer.com",
        "ign.com",
        "gamespot.com",
        "eurogamer.net",
        "kotaku.com",
        "polygon.com",
        "theverge.com",
        "rockpapershotgun.com",
        "gamesindustry.biz"
    ]
    if any(domain in source_lower for domain in major_media_domains):
        boost = 5
        return boost
    
    # Reddit: +3
    if "reddit.com" in source_lower:
        boost = 3
        return boost
    
    # Google News: +2
    if "news.google.com" in source_lower:
        boost = 2
        return boost
    
    # Funding news: +20 (already handled in category scoring, but extra boost for visibility)
    # This is handled in category scoring
    
    # Global publisher mention: +15 (handled in publisher_deal category)
    
    # Minor patch: -20 (handled in category scoring)
    
    return boost


def _classify_category_from_text(text_lower: str) -> str:
    """Classify category from text using rules"""
    # release patterns
    if any(pattern in text_lower for pattern in ["launch", "released", "out now", "выход", "запуск", "выпуск"]):
        return "release"
    
    # patch_major patterns
    if any(pattern in text_lower for pattern in ["major update", "overhaul", "2.0", "3.0", "season", "chapter", "большое обновление", "крупное обновление"]):
        return "patch_major"
    
    # discount patterns
    if any(pattern in text_lower for pattern in ["% off", "discount", "sale", "скидка", "распродажа", "со скидкой"]):
        return "discount"
    
    # publisher_deal patterns
    if any(pattern in text_lower for pattern in ["publisher", "publishing deal", "издатель", "издательская сделка"]):
        return "publisher_deal"
    
    # funding patterns
    if any(pattern in text_lower for pattern in ["funding", "investment", "raised", "финансирование", "инвестиции", "привлек"]):
        return "funding"
    
    # market_trend patterns
    if any(pattern in text_lower for pattern in ["chart", "ranking", "peak players", "топ", "рейтинг", "пик игроков"]):
        return "market_trend"
    
    # controversy patterns
    if any(pattern in text_lower for pattern in ["controversy", "scandal", "ban", "скандал", "запрет"]):
        return "controversy"
    
    return "other"


def _calculate_score_by_category(
    category: str,
    text_lower: str,
    event: IntelEvent
) -> Tuple[int, str, float]:
    """
    Calculate score, reason, and confidence based on category.
    
    Returns: (score, reason, confidence)
    """
    if not text_lower:
        return 5, "нет данных", 0.3
    
    # release: 60-85
    if category == "release":
        score = 70  # Base score
        # Boost if mentions "early access" or "full release"
        if "early access" in text_lower or "ранний доступ" in text_lower:
            score = 65
        elif "full release" in text_lower or "полный релиз" in text_lower:
            score = 80
        # +15 boost for AAA releases
        aaa_indicators = ["aaa", "triple-a", "blockbuster", "major studio"]
        if any(indicator in text_lower for indicator in aaa_indicators):
            score = min(100, score + 15)
        return score, "Релиз игры", 0.85
    
    # funding: 70-95
    if category == "funding":
        score = 80  # Base score
        # Try to extract amount (boost if large)
        amount_match = re.search(r'(\d+)\s*(млн|million|M|\$)', text_lower)
        if amount_match:
            amount = int(amount_match.group(1))
            if amount >= 10:
                score = 90
            elif amount >= 5:
                score = 85
            # +15 boost for > 1M
            if amount >= 1:
                score = min(100, score + 15)
        return score, "Финансирование проекта", 0.9
    
    # publisher_deal: 60-90
    if category == "publisher_deal":
        score = 75  # Base score
        # +15 boost for known publishers
        known_publishers = ["ea", "ubisoft", "activision", "take-two", "warner", "sony", "microsoft", "nintendo"]
        if any(pub in text_lower for pub in known_publishers):
            score = min(100, score + 15)
        return score, "Издательская сделка", 0.85
    
    # market_trend: 55-85
    if category == "market_trend":
        score = 70  # Base score
        # Boost if mentions "peak" or "record"
        if "peak" in text_lower or "record" in text_lower or "рекорд" in text_lower:
            score = 80
        return score, "Тренд рынка", 0.75
    
    # discount: 35-65
    if category == "discount":
        score = 50  # Base score
        confidence = 0.75  # Base confidence (meets min_confidence threshold)
        # Try to extract discount percentage
        discount_match = re.search(r'(\d+)%', text_lower)
        if discount_match:
            discount_pct = int(discount_match.group(1))
            if discount_pct >= 75:
                score = 65
                confidence = 0.85  # High confidence for major discounts
            elif discount_pct >= 50:
                score = 55
                # +10 boost for 50%+ discount
                score = min(100, score + 10)
                confidence = 0.8  # Good confidence for significant discounts
            elif discount_pct >= 25:
                score = 45
                confidence = 0.75  # Meets threshold
            else:
                score = 35
                confidence = 0.75  # Meets threshold
        return score, f"Скидка", confidence
    
    # patch_major: 30-70
    if category == "patch_major":
        score = 50  # Base score
        # Boost for major version numbers
        if re.search(r'\b(2\.0|3\.0|season|chapter)\b', text_lower):
            score = 65
        elif "major" in text_lower or "крупное" in text_lower:
            score = 55
        return score, "Крупное обновление", 0.7
    
    # routine patch: 5-25 (max 20)
    if category == "patch" or ("patch" in text_lower and "major" not in text_lower and "overhaul" not in text_lower):
        score = 15  # Base score for routine patches
        score = min(20, score)  # Cap at 20 for routine patches
        return score, "Обычное обновление", 0.6
    
    # controversy: 60-90 (but may need review)
    if category == "controversy":
        score = 75  # Base score
        return score, "Спорное событие (требует review)", 0.8
    
    # other: 25-40 (baseline minimum)
    # Try to reclassify as market_trend if has any Steam-related content
    if "steam" in text_lower or "valve" in text_lower or "deck" in text_lower:
        category = "market_trend"
        score = 55  # Market trend base score
        return score, "Тренд рынка (переклассифицировано)", 0.7
    
    score = 30  # Default for unknown (increased from 25 to ensure > baseline)
    return score, "Прочее событие", 0.5
