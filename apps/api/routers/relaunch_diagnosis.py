"""
Failure Diagnosis Engine для Relaunch Scout
Rule-based диагностика провала игры (без LLM).
Определяет категории провала и предлагает relaunch angles.
"""

from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# ============================================================
# Категории провала (фиксированный набор)
# ============================================================

FAILURE_CATEGORIES = [
    "visibility_failure",      # Игра не видна (алгоритмы, позиционирование)
    "launch_timing_failure",    # Плохой тайминг релиза
    "pricing_failure",          # Неправильная цена
    "expectation_mismatch",     # Несоответствие ожиданиям (жанр, контент)
    "polish_quality_failure",   # Проблемы с качеством/полировкой
    "content_depth_failure",    # Недостаточно контента/глубины
    "marketing_failure",        # Отсутствие маркетинга
]

# ============================================================
# Relaunch Angles (mapping failure → angles)
# ============================================================

FAILURE_TO_ANGLES = {
    "visibility_failure": [
        "regional_relaunch",
        "platform_relaunch",
        "publisher_takeover",
    ],
    "launch_timing_failure": [
        "content_update + relaunch",
        "regional_relaunch",
    ],
    "pricing_failure": [
        "price_repositioning",
        "regional_relaunch",
    ],
    "expectation_mismatch": [
        "content_update + relaunch",
        "platform_relaunch",
    ],
    "polish_quality_failure": [
        "content_update + relaunch",
        "publisher_takeover",
    ],
    "content_depth_failure": [
        "content_update + relaunch",
        "platform_relaunch",
    ],
    "marketing_failure": [
        "publisher_takeover",
        "regional_relaunch",
        "asia_localization_push",
    ],
}

# ============================================================
# Правила диагностики (rule-based)
# ============================================================

def diagnose_visibility_failure(steam_data: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    """
    Диагностика: игра не видна (алгоритмы Steam, позиционирование).
    
    Сигналы:
    - Низкое total_reviews при хорошем positive_ratio
    - Низкая review_velocity
    - Отсутствие в топах
    """
    total_reviews = steam_data.get("reviews_total", 0)
    positive_ratio = steam_data.get("positive_ratio", 0.0)
    
    confidence = 0.0
    signals = {}
    
    # Правило 1: Хорошие отзывы, но мало их
    if total_reviews < 1000 and positive_ratio > 0.7:
        confidence += 0.4
        signals["low_reviews_good_ratio"] = True
    
    # Правило 2: Очень низкая review velocity (если есть данные)
    recent_reviews = steam_data.get("recent_reviews_30d", 0)
    if total_reviews > 0 and recent_reviews / total_reviews < 0.05:
        confidence += 0.3
        signals["low_review_velocity"] = True
    
    # Правило 3: Низкие reviews при возрасте 6-24 месяца (должно было быть больше)
    age_months = steam_data.get("age_months", 0)
    if 6 <= age_months <= 24 and total_reviews < 500:
        confidence += 0.3
        signals["low_reviews_for_age"] = True
    
    return min(confidence, 1.0), signals


def diagnose_launch_timing_failure(steam_data: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    """
    Диагностика: плохой тайминг релиза.
    
    Сигналы:
    - Резкий спад после launch
    - Ранние негативные отзывы
    - Релиз в конкурентный период
    """
    age_months = steam_data.get("age_months", 0)
    total_reviews = steam_data.get("reviews_total", 0)
    positive_ratio = steam_data.get("positive_ratio", 0.0)
    recent_reviews = steam_data.get("recent_reviews_30d", 0)
    
    confidence = 0.0
    signals = {}
    
    # Правило 1: Резкий спад после launch (много ранних отзывов, мало недавних)
    if total_reviews > 100 and recent_reviews < total_reviews * 0.1:
        confidence += 0.4
        signals["post_launch_drop"] = True
    
    # Правило 2: Ранние негативные отзывы (если есть данные)
    early_negative_ratio = steam_data.get("early_negative_ratio", None)
    if early_negative_ratio and early_negative_ratio > 0.4:
        confidence += 0.3
        signals["early_negative_spike"] = True
    
    # Правило 3: Релиз в "мертвый" период (аппроксимация: если игра старше 12 месяцев и reviews низкие)
    if age_months > 12 and total_reviews < 1000:
        confidence += 0.3
        signals["bad_timing_window"] = True
    
    return min(confidence, 1.0), signals


def diagnose_pricing_failure(steam_data: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    """
    Диагностика: неправильная цена.
    
    Сигналы:
    - Высокая цена при низких reviews
    - Упоминания "overpriced" в отзывах (если есть)
    - Низкая цена при хорошем качестве
    """
    price = steam_data.get("price", 0)
    total_reviews = steam_data.get("reviews_total", 0)
    positive_ratio = steam_data.get("positive_ratio", 0.0)
    
    confidence = 0.0
    signals = {}
    
    # Правило 1: Высокая цена (>$20) при низких reviews и хорошем качестве
    if price > 20 and total_reviews < 500 and positive_ratio > 0.7:
        confidence += 0.5
        signals["high_price_low_reviews"] = True
    
    # Правило 2: Очень низкая цена (<$5) при хорошем качестве (недооценка)
    if price < 5 and positive_ratio > 0.75 and total_reviews < 1000:
        confidence += 0.3
        signals["underpriced"] = True
    
    # Правило 3: Средняя цена, но reviews очень низкие (возможно переоценка)
    if 5 <= price <= 20 and total_reviews < 200 and positive_ratio > 0.6:
        confidence += 0.2
        signals["price_mismatch"] = True
    
    return min(confidence, 1.0), signals


def diagnose_expectation_mismatch(steam_data: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    """
    Диагностика: несоответствие ожиданиям (жанр, контент, теги).
    
    Сигналы:
    - Низкий positive_ratio при средних reviews
    - Несоответствие тегов/жанра
    """
    positive_ratio = steam_data.get("positive_ratio", 0.0)
    total_reviews = steam_data.get("reviews_total", 0)
    
    confidence = 0.0
    signals = {}
    
    # Правило 1: Низкий positive_ratio (много негатива) при средних reviews
    if 0.4 <= positive_ratio <= 0.6 and total_reviews > 100:
        confidence += 0.5
        signals["mixed_reception"] = True
    
    # Правило 2: Резкое падение positive_ratio со временем (если есть данные)
    delta_recent = steam_data.get("delta_recent_90d", None)
    if delta_recent and delta_recent < -0.1:
        confidence += 0.3
        signals["declining_sentiment"] = True
    
    # Правило 3: Средние reviews, но низкий positive_ratio (ожидания не оправдались)
    if 200 <= total_reviews <= 2000 and positive_ratio < 0.65:
        confidence += 0.2
        signals["expectation_gap"] = True
    
    return min(confidence, 1.0), signals


def diagnose_polish_quality_failure(steam_data: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    """
    Диагностика: проблемы с качеством/полировкой.
    
    Сигналы:
    - Низкий positive_ratio
    - Ранние негативные отзывы
    - Упоминания багов/крашей
    """
    positive_ratio = steam_data.get("positive_ratio", 0.0)
    total_reviews = steam_data.get("reviews_total", 0)
    early_negative_ratio = steam_data.get("early_negative_ratio", None)
    
    confidence = 0.0
    signals = {}
    
    # Правило 1: Очень низкий positive_ratio (<50%)
    if positive_ratio < 0.5 and total_reviews > 50:
        confidence += 0.5
        signals["low_positive_ratio"] = True
    
    # Правило 2: Ранние негативные отзывы (технические проблемы при launch)
    if early_negative_ratio and early_negative_ratio > 0.5:
        confidence += 0.3
        signals["early_technical_issues"] = True
    
    # Правило 3: Низкий positive_ratio при средних reviews (качество не вытянуло)
    if 0.3 <= positive_ratio <= 0.55 and total_reviews > 100:
        confidence += 0.2
        signals["quality_issues"] = True
    
    return min(confidence, 1.0), signals


def diagnose_content_depth_failure(steam_data: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    """
    Диагностика: недостаточно контента/глубины.
    
    Сигналы:
    - Низкие reviews при хорошем positive_ratio
    - Ранний спад активности
    """
    total_reviews = steam_data.get("reviews_total", 0)
    positive_ratio = steam_data.get("positive_ratio", 0.0)
    recent_reviews = steam_data.get("recent_reviews_30d", 0)
    age_months = steam_data.get("age_months", 0)
    
    confidence = 0.0
    signals = {}
    
    # Правило 1: Хорошие отзывы, но очень мало reviews (недостаточно контента для удержания)
    if positive_ratio > 0.7 and total_reviews < 300 and age_months > 6:
        confidence += 0.4
        signals["good_quality_low_engagement"] = True
    
    # Правило 2: Резкий спад после начального периода (контент закончился)
    if total_reviews > 100 and recent_reviews < total_reviews * 0.05 and age_months > 9:
        confidence += 0.3
        signals["content_exhaustion"] = True
    
    # Правило 3: Низкие reviews при хорошем качестве (недостаточно глубины для долгой игры)
    if positive_ratio > 0.75 and total_reviews < 500 and age_months > 12:
        confidence += 0.3
        signals["shallow_content"] = True
    
    return min(confidence, 1.0), signals


def diagnose_marketing_failure(steam_data: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    """
    Диагностика: отсутствие маркетинга.
    
    Сигналы:
    - Очень низкие reviews при хорошем качестве
    - Отсутствие роста
    """
    total_reviews = steam_data.get("reviews_total", 0)
    positive_ratio = steam_data.get("positive_ratio", 0.0)
    age_months = steam_data.get("age_months", 0)
    
    confidence = 0.0
    signals = {}
    
    # Правило 1: Отличное качество, но очень мало reviews (никто не знает об игре)
    if positive_ratio > 0.8 and total_reviews < 200 and age_months > 6:
        confidence += 0.5
        signals["hidden_gem"] = True
    
    # Правило 2: Хорошее качество, но стагнация reviews (нет маркетинга)
    if positive_ratio > 0.7 and total_reviews < 500 and age_months > 12:
        confidence += 0.3
        signals["no_marketing_growth"] = True
    
    # Правило 3: Низкие reviews при среднем качестве (недостаточная видимость)
    if 0.6 <= positive_ratio <= 0.75 and total_reviews < 300:
        confidence += 0.2
        signals["low_visibility"] = True
    
    return min(confidence, 1.0), signals


# ============================================================
# Главная функция диагностики
# ============================================================

def diagnose_game(steam_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Полная диагностика игры: определяет категории провала и предлагает angles.
    
    Args:
        steam_data: Словарь с данными Steam:
            - reviews_total
            - positive_ratio (0.0-1.0)
            - recent_reviews_30d
            - delta_recent_90d (опционально)
            - early_negative_ratio (опционально)
            - price
            - age_months
            - review_velocity (опционально)
    
    Returns:
        {
            "failure_categories": [{"category": str, "confidence": float, "signals": dict}],
            "suggested_angles": [str],
            "key_signals": dict,
            "confidence_map": {category: confidence},
        }
    """
    # Вычисляем confidence для каждой категории
    diagnosis_funcs = {
        "visibility_failure": diagnose_visibility_failure,
        "launch_timing_failure": diagnose_launch_timing_failure,
        "pricing_failure": diagnose_pricing_failure,
        "expectation_mismatch": diagnose_expectation_mismatch,
        "polish_quality_failure": diagnose_polish_quality_failure,
        "content_depth_failure": diagnose_content_depth_failure,
        "marketing_failure": diagnose_marketing_failure,
    }
    
    failure_categories = []
    confidence_map = {}
    all_signals = {}
    
    for category, diagnose_func in diagnosis_funcs.items():
        confidence, signals = diagnose_func(steam_data)
        
        if confidence > 0.2:  # Порог для включения категории
            failure_categories.append({
                "category": category,
                "confidence": round(confidence, 2),
                "signals": signals,
            })
            confidence_map[category] = confidence
            all_signals.update(signals)
    
    # Сортируем по confidence (высокий → низкий)
    failure_categories.sort(key=lambda x: x["confidence"], reverse=True)
    
    # Определяем suggested_angles на основе failure_categories
    suggested_angles = []
    angle_set = set()
    
    for fc in failure_categories[:3]:  # Топ-3 категории
        category = fc["category"]
        angles = FAILURE_TO_ANGLES.get(category, [])
        for angle in angles:
            if angle not in angle_set:
                angle_set.add(angle)
                suggested_angles.append(angle)
    
    # Если нет категорий - добавляем общие angles
    if not suggested_angles:
        suggested_angles = ["content_update + relaunch", "regional_relaunch"]
    
    return {
        "failure_categories": [fc["category"] for fc in failure_categories],
        "suggested_angles": suggested_angles,
        "key_signals": all_signals,
        "confidence_map": confidence_map,
    }
