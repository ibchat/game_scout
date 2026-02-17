"""
Behavioral Intent Keywords v3.2
Словарь ключевых слов для обнаружения намерений издателей/инвестиций.
Каждому ключу назначен intent_strength (1..5) для оценки силы сигнала.
"""
from typing import Dict, List

# ============================================================================
# PRIMARY KEYWORDS (intent_strength 4-5)
# ============================================================================

PRIMARY_KEYWORDS: Dict[str, int] = {
    "looking for a publisher": 5,
    "looking for publisher": 5,  # Без артикля (согласно ТЗ п.4.2.A)
    "seeking publisher": 5,
    "need a publisher": 5,
    "need publisher": 5,  # Без артикля (согласно ТЗ п.4.2.A)
    "publisher wanted": 5,
    "looking for publishing partner": 5,
    "seeking funding": 5,
    "need funding": 5,  # Согласно ТЗ п.4.2.A
    "looking for funding": 5,
    "pitch deck": 4,
    "investor deck": 4,
    "publishing deal": 4,
    "we are looking for": 4,
    "need marketing help": 4,  # Согласно ТЗ п.4.2.A
    "marketing help": 4,  # Согласно ТЗ п.4.2.A
    "seeking marketing": 4,
    "looking for marketing": 4,
    "need marketing support": 4,
    "publisher help": 4,  # Согласно ТЗ п.4.2.A
    "publisher needed": 5,
    "seeking investors": 5,
    "investment wanted": 5,
    "raising funds": 4,
    "need investment": 5,
    "dm open": 3,  # Менее прямой, но всё же сигнал
    "contact us": 3,
    "reach out": 3,
    "get in touch": 3
}

# ============================================================================
# SECONDARY KEYWORDS (intent_strength 1-3)
# ============================================================================

SECONDARY_KEYWORDS: Dict[str, int] = {
    "wishlist": 2,
    "wishlists low": 2,  # Согласно ТЗ п.4.2.A
    "steam page is live": 2,
    "demo available": 2,
    "next fest": 2,
    "press kit": 1,
    "steam festival": 2,
    "coming soon": 1,
    "early access": 1,
    "early access failed": 3,  # Согласно ТЗ п.4.2.A
    "launching soon": 1,
    # Дополнительные keywords согласно TZ_SIGNAL_INGESTION_VECTOR_A_EXEC_V1.md п.4.2.A
    "launch failed": 3,
    "no visibility": 3,
    "poor sales": 3,  # Согласно ТЗ п.4.2.A
    "low sales": 3,
    "wishlist low": 2,
    "help promote": 2
}

# ============================================================================
# COMBINED KEYWORDS DICT (для удобства)
# ============================================================================

BEHAVIORAL_KEYWORDS: Dict[str, int] = {
    **PRIMARY_KEYWORDS,
    **SECONDARY_KEYWORDS
}

# ============================================================================
# KEYWORD GROUPS (для группировки в UI/аналитике)
# ============================================================================

KEYWORD_GROUPS: Dict[str, List[str]] = {
    "publisher_seeking": [
        "looking for a publisher",
        "seeking publisher",
        "need a publisher",
        "publisher wanted",
        "publisher needed",
        "looking for publishing partner"
    ],
    "funding_seeking": [
        "seeking funding",
        "need funding",
        "looking for funding",
        "seeking investors",
        "investment wanted",
        "need investment",
        "raising funds"
    ],
    "pitch_deck": [
        "pitch deck",
        "investor deck"
    ],
    "marketing_help": [
        "need marketing help",
        "seeking marketing",
        "looking for marketing",
        "need marketing support"
    ],
    "contact_open": [
        "dm open",
        "contact us",
        "reach out",
        "get in touch"
    ],
    "announcement": [
        "steam page is live",
        "demo available",
        "next fest",
        "steam festival",
        "wishlist"
    ]
}
