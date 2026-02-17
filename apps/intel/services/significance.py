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
    Calculate significance score for an Intel event.
    
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
    
    # Calculate score based on category
    score, reason, confidence = _calculate_score_by_category(category, text_lower, event)
    
    return score, reason, category, confidence


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
        return score, "Финансирование проекта", 0.9
    
    # publisher_deal: 60-90
    if category == "publisher_deal":
        score = 75  # Base score
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
        # Try to extract discount percentage
        discount_match = re.search(r'(\d+)%', text_lower)
        if discount_match:
            discount_pct = int(discount_match.group(1))
            if discount_pct >= 75:
                score = 65
            elif discount_pct >= 50:
                score = 55
            elif discount_pct >= 25:
                score = 45
            else:
                score = 35
        return score, f"Скидка", 0.7
    
    # patch_major: 30-70
    if category == "patch_major":
        score = 50  # Base score
        # Boost for major version numbers
        if re.search(r'\b(2\.0|3\.0|season|chapter)\b', text_lower):
            score = 65
        elif "major" in text_lower or "крупное" in text_lower:
            score = 55
        return score, "Крупное обновление", 0.7
    
    # routine patch: 5-25
    if category == "patch" or ("patch" in text_lower and "major" not in text_lower):
        score = 15  # Base score for routine patches
        return score, "Обычное обновление", 0.6
    
    # controversy: 60-90 (but may need review)
    if category == "controversy":
        score = 75  # Base score
        return score, "Спорное событие (требует review)", 0.8
    
    # other: 10-40
    score = 25  # Default for unknown
    return score, "Прочее событие", 0.5
