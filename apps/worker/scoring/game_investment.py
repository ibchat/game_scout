"""
Game Investment Scoring
Расчёт Product Potential, GTM Execution, GAP, Fixability
"""
import logging
from typing import Optional, Tuple, Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def compute_pp(
    game_data: dict,
    narrative_data: Optional[dict] = None,
    metrics: Optional[dict] = None,
    external_signals: Optional[dict] = None
) -> Tuple[float, str]:
    """
    Вычислить Product Potential (PP) 0-10
    
    Компоненты:
    1. Pattern Strength (0-3): Сила нарративного паттерна
    2. Universality (0-2.5): Универсальность темы
    3. Genre Fit (0-2.5): Соответствие жанру
    4. Loop Repeatability (0-2): Реиграбельность
    
    Args:
        game_data: {title, description, tags, genre, ...}
        narrative_data: {pattern, level, in_gameplay, ...}
        metrics: {reviews, rating, playtime, ...}
        external_signals: {ewi, epv, intent_ratio, ...}
    
    Returns:
        (pp_score, confidence)
    """
    score = 0.0
    factors = []
    
    # 1. Pattern Strength (0-3)
    if narrative_data:
        pattern = narrative_data.get('primary_pattern', '')
        in_gameplay = narrative_data.get('pattern_in_gameplay', False)
        
        if in_gameplay:
            # Паттерн в геймплее = сильный продукт
            pattern_strength = 3.0
            factors.append("Strong narrative in gameplay")
        elif pattern:
            # Есть паттерн но не в геймплее
            pattern_strength = 1.5
            factors.append("Narrative present but weak")
        else:
            pattern_strength = 0.5
            factors.append("No clear narrative pattern")
        
        score += pattern_strength
    else:
        # Нет данных о нарративе
        score += 1.5  # Neutral
        factors.append("No narrative data")
    
    # 2. Universality (0-2.5)
    if narrative_data:
        level = narrative_data.get('primary_level', 'biological')
        
        # Biological/Social = более универсальные темы
        if level in ['biological', 'social']:
            universality = 2.5
            factors.append(f"Universal theme ({level})")
        elif level == 'identity':
            universality = 1.5
            factors.append("Identity theme (niche)")
        else:  # meta
            universality = 1.0
            factors.append("Meta theme (very niche)")
        
        score += universality
    else:
        score += 1.5  # Neutral
    
    # 3. Genre Fit (0-2.5)
    # Проверяем метрики качества
    if metrics:
        rating = metrics.get('rating', 0)
        reviews = metrics.get('reviews', 0)
        
        if rating >= 0.85 and reviews >= 100:
            genre_fit = 2.5
            factors.append("Excellent ratings + volume")
        elif rating >= 0.75 and reviews >= 50:
            genre_fit = 1.8
            factors.append("Good ratings")
        elif rating >= 0.6:
            genre_fit = 1.0
            factors.append("Mixed ratings")
        else:
            genre_fit = 0.5
            factors.append("Poor ratings")
        
        score += genre_fit
    else:
        score += 1.2  # Neutral
    
    # 4. Loop Repeatability (0-2)
    if metrics:
        avg_playtime = metrics.get('avg_playtime_hours', 0)
        
        if avg_playtime >= 50:
            repeatability = 2.0
            factors.append(f"High replayability ({avg_playtime:.0f}h)")
        elif avg_playtime >= 20:
            repeatability = 1.5
            factors.append(f"Good playtime ({avg_playtime:.0f}h)")
        elif avg_playtime >= 10:
            repeatability = 1.0
            factors.append(f"Moderate playtime ({avg_playtime:.0f}h)")
        else:
            repeatability = 0.5
            factors.append(f"Low playtime ({avg_playtime:.0f}h)")
        
        score += repeatability
    else:
        score += 1.0  # Neutral
    
    # External signals boost
    if external_signals:
        intent = external_signals.get('intent_ratio', 0)
        if intent >= 0.7:
            score += 0.5
            factors.append("High user intent boost")
    
    # Clamp to 0-10
    score = max(0, min(10, score))
    
    # Confidence
    data_points = sum([
        narrative_data is not None,
        metrics is not None,
        external_signals is not None
    ])
    
    if data_points >= 3:
        confidence = "high"
    elif data_points >= 2:
        confidence = "medium"
    else:
        confidence = "low"
    
    logger.info(f"PP calculated: {score:.1f} ({confidence}), factors: {factors}")
    
    return round(score, 1), confidence


def compute_gtm(
    game_data: dict,
    narrative_data: Optional[dict] = None,
    page_quality: Optional[dict] = None,
    external_signals: Optional[dict] = None
) -> Tuple[float, str]:
    """
    Вычислить GTM Execution (0-10)
    
    Компоненты:
    1. Visibility (0-3): Сколько людей видят игру
    2. Message Clarity (0-2.5): Понятно ли что это за игра
    3. Conversion (0-2.5): Конвертируют ли просмотры в интерес
    4. Marketing Quality (0-2): Качество материалов
    
    Args:
        game_data: {reviews, followers, wishlists, ...}
        narrative_data: ...
        page_quality: {has_trailer, screenshots_count, description_length}
        external_signals: {confusion_ratio, engagement, ...}
    
    Returns:
        (gtm_score, confidence)
    """
    score = 0.0
    factors = []
    
    # 1. Visibility (0-3)
    reviews = game_data.get('reviews', 0)
    
    if reviews >= 1000:
        visibility = 3.0
        factors.append(f"High visibility ({reviews} reviews)")
    elif reviews >= 500:
        visibility = 2.5
        factors.append(f"Good visibility ({reviews} reviews)")
    elif reviews >= 100:
        visibility = 1.5
        factors.append(f"Moderate visibility ({reviews} reviews)")
    elif reviews >= 10:
        visibility = 0.8
        factors.append(f"Low visibility ({reviews} reviews)")
    else:
        visibility = 0.2
        factors.append(f"Very low visibility ({reviews} reviews)")
    
    score += visibility
    
    # 2. Message Clarity (0-2.5)
    if external_signals:
        confusion = external_signals.get('confusion_ratio', 0.5)
        
        if confusion <= 0.1:
            clarity = 2.5
            factors.append("Excellent message clarity")
        elif confusion <= 0.3:
            clarity = 1.8
            factors.append("Good message clarity")
        elif confusion <= 0.5:
            clarity = 1.0
            factors.append("Moderate confusion")
        else:
            clarity = 0.5
            factors.append("High confusion")
        
        score += clarity
    else:
        # Fallback: проверяем описание
        description = game_data.get('description', '')
        if len(description) >= 200:
            score += 1.5
            factors.append("Has description")
        else:
            score += 0.5
            factors.append("Minimal description")
    
    # 3. Conversion (0-2.5)
    if external_signals:
        intent = external_signals.get('intent_ratio', 0)
        engagement = external_signals.get('engagement', 0)
        
        combined = (intent * 0.7 + engagement * 0.3)
        
        if combined >= 0.6:
            conversion = 2.5
            factors.append("High conversion")
        elif combined >= 0.4:
            conversion = 1.8
            factors.append("Good conversion")
        elif combined >= 0.2:
            conversion = 1.0
            factors.append("Moderate conversion")
        else:
            conversion = 0.5
            factors.append("Low conversion")
        
        score += conversion
    else:
        # Fallback: positive ratio
        positive_ratio = game_data.get('positive_ratio', 0.5)
        score += positive_ratio * 2.5
        factors.append(f"Positive ratio {positive_ratio:.0%}")
    
    # 4. Marketing Quality (0-2)
    if page_quality:
        has_trailer = page_quality.get('has_trailer', False)
        screenshots = page_quality.get('screenshots_count', 0)
        
        quality = 0
        if has_trailer:
            quality += 1.0
            factors.append("Has trailer")
        if screenshots >= 5:
            quality += 1.0
            factors.append(f"{screenshots} screenshots")
        elif screenshots >= 2:
            quality += 0.5
        
        score += quality
    else:
        score += 1.0  # Neutral
    
    # Clamp
    score = max(0, min(10, score))
    
    # Confidence
    data_points = sum([
        'reviews' in game_data,
        external_signals is not None,
        page_quality is not None
    ])
    
    confidence = "high" if data_points >= 2 else "medium" if data_points >= 1 else "low"
    
    logger.info(f"GTM calculated: {score:.1f} ({confidence}), factors: {factors}")
    
    return round(score, 1), confidence


def compute_fixability(
    game_data: dict,
    narrative_data: Optional[dict] = None,
    issues: Optional[list] = None
) -> Tuple[float, str]:
    """
    Вычислить Fixability (0-10)
    
    Насколько легко исправить проблемы?
    - High fixability = маркетинг можно улучшить быстро
    - Low fixability = продукт надо переделывать
    
    Args:
        game_data: ...
        narrative_data: ...
        issues: List of identified issues
    
    Returns:
        (fixability_score, estimated_timeline)
    """
    score = 10.0  # Start optimistic
    timeline = "30-45 days"
    
    # Проверяем продуктовые проблемы (снижают fixability)
    if narrative_data:
        in_gameplay = narrative_data.get('pattern_in_gameplay', False)
        
        if not in_gameplay:
            score -= 3.0
            timeline = "6-12 months"
            logger.info("Product issue: narrative not in gameplay")
    
    # Проверяем метрики
    rating = game_data.get('positive_ratio', 0.5)
    
    if rating < 0.6:
        score -= 4.0
        timeline = "12+ months"
        logger.info("Product issue: poor ratings")
    elif rating < 0.75:
        score -= 2.0
        timeline = "3-6 months"
    
    # Marketing issues легче исправить
    reviews = game_data.get('reviews', 0)
    if reviews < 100:
        # Low visibility = легко исправить маркетингом
        score = max(score, 7.0)  # Keep fixability high
        timeline = "30-45 days"
        logger.info("Marketing issue: low visibility (easily fixable)")
    
    score = max(0, min(10, score))
    
    logger.info(f"Fixability: {score:.1f}, timeline: {timeline}")
    
    return round(score, 1), timeline


def classify_investment(
    pp: float,
    gtm: float,
    gap: float,
    fix: float,
    ewi: Optional[float] = None,
    epv: Optional[float] = None
) -> Tuple[str, str, str]:
    """
    Классифицировать инвестиционную возможность
    
    Returns:
        (category, reasoning, roi_estimate)
    """
    # UNDERMARKETED_GEM
    if pp >= 7 and gap >= 2 and fix >= 7:
        if ewi and ewi >= 60:
            return (
                "undermarketed_gem",
                "💎 Редкая находка! Сильный продукт + слабый маркетинг + высокий EWI",
                "ROI 5-10x"
            )
        return (
            "undermarketed_gem",
            "💎 Недооценённый шедевр! Сильный продукт с разрывом в маркетинге",
            "ROI 5-10x"
        )
    
    # MARKETING_FIXABLE
    if pp >= 6 and gap >= 1.5 and fix >= 6:
        return (
            "marketing_fixable",
            "🔧 Маркетинг исправим. Хороший продукт с недостаточной видимостью",
            "ROI 2-4x"
        )
    
    # PRODUCT_RISK
    if pp < 5 or fix < 4:
        return (
            "product_risk",
            "⚠️ Продуктовый риск. Маркетинг не поможет если продукт слабый",
            "High risk"
        )
    
    # NOT_INVESTABLE
    if gap < 1:
        return (
            "not_investable",
            "❌ Нет инвестиционной возможности. GTM уже соответствует продукту",
            "No opportunity"
        )
    
    # DEFAULT
    return (
        "watch",
        "👀 Наблюдаем. Потенциал есть но нужно больше данных",
        "Monitor"
    )
