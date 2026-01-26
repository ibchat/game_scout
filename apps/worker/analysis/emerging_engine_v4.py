"""
Emerging Engine v4 - Final (Steam-only, честный радар)
Полностью отделён от TrendsBrain. Использует только steam_review_daily и steam_app_cache.
"""
import logging
import math
from datetime import date, datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Константы из ТЗ v4 Final
MIN_RECENT_REVIEWS_30D = 30  # Growth Filter
MIN_POSITIVE_RATIO = 0.70  # Quality Filter
EVERGREEN_YEARS = 3  # Evergreen Filter (возраст в годах)
EVERGREEN_REVIEWS_THRESHOLD = 50000  # Evergreen Filter
EMERGING_SCORE_THRESHOLD = 2.0  # Score Threshold

# Строгий набор вердиктов из ТЗ v4 Final
ALLOWED_VERDICTS = {
    "Устойчивый рост — emerging",
    "Ранний рост — требует наблюдения",
    "Рост есть, но слабая динамика",
    "Недостаточно данных",
    "Высокий интерес, но низкое качество",
    "Evergreen — исключено из emerging"
}


@dataclass
class EmergingResult:
    """Результат анализа emerging для игры"""
    steam_app_id: int
    emerging_score: float
    verdict: str
    reason: str
    passed_filters: bool
    
    # Данные для диагностики
    all_reviews_count: Optional[int]
    recent_reviews_count_30d: Optional[int]
    all_positive_ratio: Optional[float]
    
    # Флаги фильтров
    is_evergreen: bool
    is_low_quality: bool
    has_insufficient_growth: bool


def compute_emerging_score(
    recent_reviews_count_30d: Optional[int],
    all_positive_ratio: Optional[float]
) -> float:
    """
    Вычисляет emerging_score по формуле из ТЗ v4:
    emerging_score = log1p(recent_reviews_count_30d) * all_positive_ratio
    """
    if recent_reviews_count_30d is None or recent_reviews_count_30d <= 0:
        return 0.0
    
    if all_positive_ratio is None or all_positive_ratio <= 0:
        return 0.0
    
    log_component = math.log1p(recent_reviews_count_30d)
    score = log_component * all_positive_ratio
    
    return round(score, 2)


def analyze_emerging(app_row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Анализирует игру на предмет emerging (v4 Final).
    
    Args:
        app_row: Словарь с данными из SQL запроса:
            - steam_app_id
            - all_reviews_count (из steam_review_daily)
            - recent_reviews_count_30d (из steam_review_daily)
            - all_positive_percent (из steam_review_daily, 0-100)
            - release_date (из steam_app_cache или steam_app_facts)
            - game_name (из steam_app_cache)
            - steam_url (из steam_app_cache)
    
    Returns:
        {
            "app_id": int,
            "name": str,
            "recent_reviews_30d": int,
            "positive_ratio": float,
            "emerging_score": float,
            "verdict": str,
            "passed_filters": bool,
            "filter_results": {
                "growth": bool,
                "quality": bool,
                "evergreen": bool,
                "score": bool
            }
        }
    """
    steam_app_id = app_row.get("steam_app_id")
    all_reviews_count = app_row.get("all_reviews_count")
    recent_reviews_count_30d = app_row.get("recent_reviews_count_30d")
    all_positive_percent = app_row.get("all_positive_percent")
    release_date = app_row.get("release_date")
    
    # Конвертируем percent в ratio (0-100 -> 0.0-1.0)
    all_positive_ratio = None
    if all_positive_percent is not None:
        all_positive_ratio = all_positive_percent / 100.0
    
    # Результаты фильтров
    filter_results = {
        "growth": False,
        "quality": False,
        "evergreen": False,
        "score": False
    }
    
    # Фильтр 1: Growth
    if recent_reviews_count_30d is None or recent_reviews_count_30d < MIN_RECENT_REVIEWS_30D:
        return {
            "app_id": steam_app_id,
            "name": app_row.get("game_name") or f"App {steam_app_id}",
            "recent_reviews_30d": recent_reviews_count_30d or 0,
            "positive_ratio": all_positive_ratio or 0.0,
            "emerging_score": 0.0,
            "verdict": "Недостаточно данных",
            "passed_filters": False,
            "filter_results": filter_results
        }
    filter_results["growth"] = True
    
    # Фильтр 2: Quality
    if all_positive_ratio is None or all_positive_ratio < MIN_POSITIVE_RATIO:
        return {
            "app_id": steam_app_id,
            "name": app_row.get("game_name") or f"App {steam_app_id}",
            "recent_reviews_30d": recent_reviews_count_30d,
            "positive_ratio": all_positive_ratio or 0.0,
            "emerging_score": 0.0,
            "verdict": "Высокий интерес, но низкое качество",
            "passed_filters": False,
            "filter_results": filter_results
        }
    filter_results["quality"] = True
    
    # Фильтр 3: Evergreen
    is_evergreen = False
    if release_date:
        try:
            if isinstance(release_date, str):
                release_date_obj = datetime.fromisoformat(release_date.replace('Z', '+00:00')).date()
            elif isinstance(release_date, date):
                release_date_obj = release_date
            else:
                release_date_obj = None
            
            if release_date_obj:
                age_years = (date.today() - release_date_obj).days / 365.25
                if age_years > EVERGREEN_YEARS and all_reviews_count and all_reviews_count >= EVERGREEN_REVIEWS_THRESHOLD:
                    is_evergreen = True
        except Exception as e:
            logger.warning(f"Failed to parse release_date for app {steam_app_id}: {e}")
    
    if is_evergreen:
        filter_results["evergreen"] = True
        return {
            "app_id": steam_app_id,
            "name": app_row.get("game_name") or f"App {steam_app_id}",
            "recent_reviews_30d": recent_reviews_count_30d,
            "positive_ratio": all_positive_ratio,
            "emerging_score": 0.0,
            "verdict": "Evergreen — исключено из emerging",
            "passed_filters": False,
            "filter_results": filter_results
        }
    
    # Вычисляем emerging_score
    emerging_score = compute_emerging_score(recent_reviews_count_30d, all_positive_ratio)
    
    # Фильтр 4: Score Threshold
    if emerging_score < EMERGING_SCORE_THRESHOLD:
        filter_results["score"] = False
        if emerging_score >= 1.0:
            verdict = "Рост есть, но слабая динамика"
        else:
            verdict = "Ранний рост — требует наблюдения"
    else:
        filter_results["score"] = True
        verdict = "Устойчивый рост — emerging"
    
    return {
        "app_id": steam_app_id,
        "name": app_row.get("game_name") or f"App {steam_app_id}",
        "recent_reviews_30d": recent_reviews_count_30d,
        "positive_ratio": all_positive_ratio,
        "emerging_score": round(emerging_score, 2),
        "verdict": verdict,
        "passed_filters": filter_results["score"],
        "filter_results": filter_results,
        "steam_url": app_row.get("steam_url") or f"https://store.steampowered.com/app/{steam_app_id}/",
        "all_reviews_count": all_reviews_count,
        "release_date": release_date.isoformat() if isinstance(release_date, date) else (release_date if isinstance(release_date, str) else None)
    }


def analyze_emerging_legacy(
    steam_app_id: int,
    all_reviews_count: Optional[int],
    recent_reviews_count_30d: Optional[int],
    all_positive_ratio: Optional[float],
    # Параметры фильтров (можно переопределить)
    evergreen_threshold: int = EVERGREEN_REVIEWS_THRESHOLD,
    min_positive_ratio: float = MIN_POSITIVE_RATIO,
    min_recent_reviews: int = MIN_RECENT_REVIEWS_30D,
    score_threshold: float = EMERGING_SCORE_THRESHOLD
) -> EmergingResult:
    """
    Анализирует игру на предмет emerging согласно ТЗ v4.
    
    Фильтры применяются строго по порядку:
    1. Evergreen Filter
    2. Quality Filter
    3. Growth Filter
    4. Score Threshold
    """
    # Инициализация флагов
    is_evergreen = False
    is_low_quality = False
    has_insufficient_growth = False
    passed_filters = True
    verdict = "not_emerging"
    reason = ""
    
    # Фильтр 1: Evergreen
    if all_reviews_count is not None and all_reviews_count >= evergreen_threshold:
        is_evergreen = True
        passed_filters = False
        verdict = "filtered_evergreen"
        reason = f"Evergreen: {all_reviews_count} отзывов >= {evergreen_threshold}"
        return EmergingResult(
            steam_app_id=steam_app_id,
            emerging_score=0.0,
            verdict=verdict,
            reason=reason,
            passed_filters=passed_filters,
            all_reviews_count=all_reviews_count,
            recent_reviews_count_30d=recent_reviews_count_30d,
            all_positive_ratio=all_positive_ratio,
            is_evergreen=is_evergreen,
            is_low_quality=False,
            has_insufficient_growth=False
        )
    
    # Фильтр 2: Quality
    if all_positive_ratio is not None and all_positive_ratio < min_positive_ratio:
        is_low_quality = True
        passed_filters = False
        verdict = "low_quality"
        reason = f"Низкое качество: {all_positive_ratio*100:.1f}% < {min_positive_ratio*100:.0f}%"
        return EmergingResult(
            steam_app_id=steam_app_id,
            emerging_score=0.0,
            verdict=verdict,
            reason=reason,
            passed_filters=passed_filters,
            all_reviews_count=all_reviews_count,
            recent_reviews_count_30d=recent_reviews_count_30d,
            all_positive_ratio=all_positive_ratio,
            is_evergreen=False,
            is_low_quality=is_low_quality,
            has_insufficient_growth=False
        )
    
    # Фильтр 3: Growth
    if recent_reviews_count_30d is None or recent_reviews_count_30d < min_recent_reviews:
        has_insufficient_growth = True
        passed_filters = False
        verdict = "insufficient_signals"
        reason = f"Недостаточно роста: {recent_reviews_count_30d or 0} < {min_recent_reviews} отзывов за 30 дней"
        return EmergingResult(
            steam_app_id=steam_app_id,
            emerging_score=0.0,
            verdict=verdict,
            reason=reason,
            passed_filters=passed_filters,
            all_reviews_count=all_reviews_count,
            recent_reviews_count_30d=recent_reviews_count_30d,
            all_positive_ratio=all_positive_ratio,
            is_evergreen=False,
            is_low_quality=False,
            has_insufficient_growth=has_insufficient_growth
        )
    
    # Вычисляем emerging_score
    emerging_score = compute_emerging_score(recent_reviews_count_30d, all_positive_ratio)
    
    # Фильтр 4: Score Threshold
    if emerging_score < score_threshold:
        passed_filters = False
        verdict = "not_emerging"
        reason = f"Score ниже порога: {emerging_score:.2f} < {score_threshold}"
    else:
        # Проверяем, есть ли только Steam сигналы
        if all_reviews_count is not None and recent_reviews_count_30d is not None:
            verdict = "steam_only_growth"
            reason = f"Рост на Steam: {recent_reviews_count_30d} отзывов за 30 дней, score={emerging_score:.2f}"
        else:
            verdict = "emerging"
            reason = f"Emerging: score={emerging_score:.2f}"
    
    return EmergingResult(
        steam_app_id=steam_app_id,
        emerging_score=emerging_score,
        verdict=verdict,
        reason=reason,
        passed_filters=passed_filters,
        all_reviews_count=all_reviews_count,
        recent_reviews_count_30d=recent_reviews_count_30d,
        all_positive_ratio=all_positive_ratio,
        is_evergreen=False,
        is_low_quality=False,
        has_insufficient_growth=False
    )
