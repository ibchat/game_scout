"""
Deal Intent Detection Configuration v3
Behavioral Intent & Freshness - фиксированная логика для определения намерений издателей.
НЕ МЕНЯТЬ без согласования.
"""
from typing import Any, Dict, List

# ============================================================================
# 1. BEHAVIORAL INTENT KEYWORDS (v3 - ОБЯЗАТЕЛЬНЫЙ СЛОЙ)
# ============================================================================

BEHAVIORAL_INTENT_KEYWORDS: Dict[str, List[str]] = {
    "looking_for_publisher": [
        "looking for publisher",
        "seeking publisher",
        "publisher wanted",
        "looking for publishing partner",
        "publisher needed",
        "need publisher",
        "seeking publishing partner"
    ],
    "funding": [
        "looking for funding",
        "seeking funding",
        "investment",
        "raising funds",
        "need investment",
        "seeking investors",
        "investor wanted"
    ],
    "pitch_deck": [
        "pitch deck",
        "investor deck",
        "pitch available",
        "deck available"
    ],
    "marketing_help": [
        "need marketing",
        "help with marketing",
        "marketing support",
        "need marketing help",
        "seeking marketing"
    ],
    "contact_open": [
        "dm open",
        "contact us",
        "reach out",
        "get in touch",
        "email us"
    ],
    "publisher_wanted": [
        "publisher wanted",
        "publisher needed",
        "looking for publisher"
    ]
}

# ============================================================================
# 1.1 BEHAVIORAL INTENT SOURCES (v3)
# ============================================================================

BEHAVIORAL_INTENT_SOURCES: List[str] = [
    "discord",
    "twitter",
    "x",  # Twitter rebrand
    "reddit",
    "website",
    "linkedin",
    "steam"  # Steam community posts, announcements
]

# ============================================================================
# 1.2 INTENT FRESHNESS THRESHOLDS (v3)
# ============================================================================

FRESHNESS_THRESHOLDS: Dict[str, int] = {
    "steam_page_months": 6,  # Страница Steam создана/опубликована < 6 месяцев
    "external_signal_days": 60,  # Внешний сигнал намерения < 60 дней
    "festival_days": 90,  # Участие в фестивале < 90 дней
    "success_penalty_months": 18  # Success Penalty: выпущена > 18 месяцев
}

# ============================================================================
# 1.3 LEGACY INTENT KEYWORDS (для обратной совместимости)
# ============================================================================

INTENT_KEYWORDS: Dict[str, List[str]] = BEHAVIORAL_INTENT_KEYWORDS

# ============================================================================
# 2. INTENT WEIGHTS v3 (3 СЛОЯ: Behavioral, Structural, Temporal)
# ============================================================================

# 2.1 BEHAVIORAL INTENT WEIGHTS (главный слой, обязательный)
BEHAVIORAL_INTENT_WEIGHTS: Dict[str, int] = {
    "looking_for_publisher": 40,  # Высокий вес - явный запрос
    "funding": 35,  # Высокий вес - поиск инвестиций
    "pitch_deck": 30,  # Средний-высокий - готовность к презентации
    "marketing_help": 20,  # Средний - нужна помощь
    "contact_open": 15,  # Средний - открыт к контакту
    "publisher_wanted": 25  # Средний-высокий - явный запрос
}

# 2.2 STRUCTURAL INTENT WEIGHTS (вспомогательный слой)
STRUCTURAL_INTENT_WEIGHTS: Dict[str, int] = {
    "no_publisher_on_steam": 12,  # Нет издателя на Steam
    "self_published": 10,  # Self-published
    "self_published_early": 15,  # Self-published + ранняя стадия
    "stage_demo": 18,  # Demo стадия
    "stage_coming_soon": 15,  # Скоро релиз
    "stage_early_access_fresh": 12,  # Свежий EA
    "stage_early_access": 8,  # EA
    "stage_released_fresh": 6,  # Свежий релиз
    "has_website": 3,  # Есть сайт
    "has_discord": 3,  # Есть Discord
    "has_publisher": -3,  # Есть издатель (штраф)
    "known_publisher_penalty": -20,  # Известный издатель (большой штраф)
    "old_release_penalty": -15  # Старый релиз (штраф)
}

# 2.3 TEMPORAL BOOST WEIGHTS (временной слой)
TEMPORAL_BOOST_WEIGHTS: Dict[str, int] = {
    "fresh_steam_page": 8,  # Свежая страница Steam (< 6 мес)
    "recent_signal": 10,  # Недавний сигнал (< 60 дней)
    "recent_festival": 12,  # Недавний фестиваль (< 90 дней)
    "recent_announcement": 8,  # Недавний анонс
    "recent_activity": 5  # Недавняя активность команды
}

# 2.4 LEGACY INTENT WEIGHTS (для обратной совместимости)
INTENT_WEIGHTS: Dict[str, int] = {
    **BEHAVIORAL_INTENT_WEIGHTS,
    **STRUCTURAL_INTENT_WEIGHTS,
    **TEMPORAL_BOOST_WEIGHTS
}

# ============================================================================
# 3. KNOWN PUBLISHERS (Penalty List)
# ============================================================================

KNOWN_PUBLISHERS: List[str] = [
    "devolver",
    "paradox",
    "ubisoft",
    "ea",
    "activision",
    "bandai",
    "focus entertainment",
    "2k",
    "take-two",
    "warner bros",
    "square enix",
    "capcom",
    "sega",
    "nintendo",
    "sony",
    "microsoft",
    "epic games",
    "valve"
]

# ============================================================================
# 4. QUALITY THRESHOLDS v3 (готовность к издателю, не успешность)
# ============================================================================

QUALITY_THRESHOLDS: Dict[str, float] = {
    "positive_ratio_strong": 0.85,
    "positive_ratio_ok": 0.75,
    "min_reviews_30d": 20,
    "growth_multiplier": 1.5,
    "success_penalty_reviews": 2000,  # Success Penalty: total reviews >= 2000
    "success_penalty_reviews_30d": 200,  # Success Penalty: reviews_30d >= 200
    "success_penalty_positive_ratio": 0.90,  # Success Penalty: positive_ratio >= 90% AND reviews >= 1000
    "success_penalty_reviews_for_ratio": 1000
}

# ============================================================================
# 5. QUALITY WEIGHTS v3 (готовность к издателю)
# ============================================================================

QUALITY_WEIGHTS: Dict[str, int] = {
    "visual_quality": 20,  # Визуал (капсулы, трейлер) - готовность к презентации
    "clear_usp": 15,  # Чёткость USP (unique selling proposition)
    "demo_reviews": 15,  # Отзывы демо (если есть)
    "update_tempo": 12,  # Темп апдейтов
    "team_activity": 10,  # Активность команды
    "adequate_scale": 8,  # Адекватный масштаб (не AAA)
    "positive_ratio": 20,  # Положительные отзывы (готовность к масштабированию)
    "reviews_30d": 15,  # Активность отзывов за 30 дней
    "has_demo": 10  # Есть демо
}

# ============================================================================
# 6. STAGE MAPPING
# ============================================================================

STAGE_MAPPING: Dict[str, str] = {
    "coming_soon": "coming_soon",
    "demo": "demo",
    "early_access": "early_access",
    "released": "released"
}

# ============================================================================
# 6. VERDICTS v3 (5 категорий на русском)
# ============================================================================

VERDICTS: Dict[str, Dict[str, Any]] = {
    "actively_seeking": {
        "code": "actively_seeking",
        "label_ru": "🟢 Активно ищет издателя",
        "min_intent_score": 40,
        "requires_behavioral": True,
        "freshness_required": True
    },
    "early_request": {
        "code": "early_request",
        "label_ru": "🟡 Ранний запрос, требуется контакт",
        "min_intent_score": 25,
        "requires_behavioral": False,
        "freshness_required": True
    },
    "possible_deal": {
        "code": "possible_deal",
        "label_ru": "🟠 Возможная сделка, нет явного запроса",
        "min_intent_score": 15,
        "requires_behavioral": False,
        "freshness_required": False
    },
    "successful_not_target": {
        "code": "successful_not_target",
        "label_ru": "⚪ Успешный проект, не целевая сделка",
        "min_intent_score": 0,
        "requires_behavioral": False,
        "freshness_required": False,
        "success_penalty": True
    },
    "no_intent_signs": {
        "code": "no_intent_signs",
        "label_ru": "🔴 Нет признаков намерения",
        "min_intent_score": 0,
        "requires_behavioral": False,
        "freshness_required": False
    }
}

# ============================================================================
# 7. INTENT SCORE BOUNDS
# ============================================================================

INTENT_SCORE_MIN = 0
INTENT_SCORE_MAX = 100
QUALITY_SCORE_MIN = 0
QUALITY_SCORE_MAX = 100

# ============================================================================
# 8. BEHAVIORAL INTENT REQUIREMENTS (v3)
# ============================================================================

# Если Behavioral Intent = 0, максимальный Intent Score ограничен
BEHAVIORAL_INTENT_MAX_SCORE_WITHOUT_SIGNALS = 25
