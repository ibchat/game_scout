"""
Relaunch Scout Filters
Функции фильтрации для определения eligible игр.
"""

from typing import Dict, Any, Optional, Tuple
from datetime import datetime

from apps.api.routers.relaunch_config import (
    EXCLUDE_APP_IDS,
    EXCLUDE_NAME_CONTAINS,
    EXCLUDE_TYPES,
    DEFAULT_MEGA_HIT_REVIEWS,
)


def should_exclude_app(
    app_id: int,
    name: str,
    game_type: str,
    is_free: bool,
    reviews_total: int,
    exclude_f2p: bool = True,
    mega_hit_reviews: int = DEFAULT_MEGA_HIT_REVIEWS,
) -> Tuple[bool, Optional[str]]:
    """
    Проверяет, должна ли игра быть исключена.
    Возвращает (should_exclude, reason).
    """
    # 1) Blacklist по app_id
    if app_id in EXCLUDE_APP_IDS:
        return (True, "blacklist_app_id")
    
    # 2) Blacklist по имени
    name_lower = name.lower()
    for exclude_name in EXCLUDE_NAME_CONTAINS:
        if exclude_name.lower() in name_lower:
            return (True, "blacklist_name")
    
    # 3) Тип не игра
    if game_type.lower() in EXCLUDE_TYPES:
        return (True, "not_a_game")
    
    # 4) F2P
    if exclude_f2p and is_free:
        return (True, "f2p")
    
    # 5) Мега-хит
    if reviews_total >= mega_hit_reviews:
        return (True, "mega_hit")
    
    return (False, None)


def is_in_rebound_window(
    release_date: Optional[datetime],
    min_months: int = 6,
    max_months: int = 24,
) -> Tuple[bool, Optional[str]]:
    """
    Проверяет, находится ли игра в Rebound Window.
    Возвращает (is_in_window, reason_if_not).
    """
    if not release_date:
        return (False, "no_release_date")
    
    now = datetime.now()
    age_months = (now.year - release_date.year) * 12 + (now.month - release_date.month)
    
    if age_months < min_months:
        return (False, "too_new")
    if age_months > max_months:
        return (False, "too_old")
    
    return (True, None)


def is_reviews_in_range(
    reviews_total: int,
    min_reviews: int = 50,
    max_reviews: int = 10000,
) -> Tuple[bool, Optional[str]]:
    """
    Проверяет, находится ли reviews_total в допустимом диапазоне.
    Возвращает (is_in_range, reason_if_not).
    """
    if reviews_total < min_reviews:
        return (False, "reviews_too_low")
    if reviews_total > max_reviews:
        return (False, "reviews_too_high")
    
    return (True, None)


def filter_game_details(
    app_details: Dict[str, Any],
    min_months: int = 6,
    max_months: int = 24,
    min_reviews: int = 50,
    max_reviews: int = 10000,
    exclude_f2p: bool = True,
    mega_hit_reviews: int = DEFAULT_MEGA_HIT_REVIEWS,
    strict_window: bool = True,
) -> Tuple[bool, Optional[str], Dict[str, Any]]:
    """
    Полная фильтрация игры по всем критериям.
    Возвращает (is_eligible, exclude_reason, breakdown).
    
    breakdown содержит статистику по каждому критерию.
    """
    from apps.api.routers.relaunch import _parse_release_date as parse_release_date
    
    app_id = app_details.get("app_id", 0)
    name = app_details.get("name", "")
    game_type = app_details.get("type", "").lower()
    is_free = app_details.get("is_free", False)
    reviews_total = app_details.get("reviews_total", 0)
    release_date_str = app_details.get("release_date")
    
    breakdown = {
        "checked": True,
        "exclude_reasons": [],
    }
    
    # 1) Исключения (blacklist, type, f2p, mega-hit) - ЖЁСТКИЕ, всегда применяются
    should_exclude, exclude_reason = should_exclude_app(
        app_id, name, game_type, is_free, reviews_total, exclude_f2p, mega_hit_reviews
    )
    if should_exclude:
        breakdown["exclude_reasons"].append(exclude_reason)
        return (False, exclude_reason, breakdown)
    
    # 2) Reviews диапазон (с правильной категоризацией)
    # КРИТИЧНО: reviews_total=0 НЕ hard-exclude, а снижение score
    # Используем flags из app_details если есть
    flags = app_details.get("_flags", {})
    reviews_missing = flags.get("reviews_missing", False)
    
    # В мягком режиме: reviews_total=0 или missing - НЕ исключаем, только снижаем score
    if reviews_total == 0 and not strict_window:
        # В мягком режиме пропускаем игры без reviews (может быть needs_review)
        # Добавляем flag для снижения score вместо hard-exclude
        breakdown["reviews_missing"] = True
        pass
    elif reviews_total > 0:
        # Проверяем диапазон только если reviews_total > 0
        reviews_ok, reviews_reason = is_reviews_in_range(reviews_total, min_reviews, max_reviews)
        if not reviews_ok:
            breakdown["exclude_reasons"].append(reviews_reason)
            # Маппинг для правильной категоризации в excluded
            if reviews_reason == "reviews_too_low":
                return (False, "reviews_too_low", breakdown)
            elif reviews_reason == "reviews_too_high":
                return (False, "reviews_too_high", breakdown)
            return (False, reviews_reason, breakdown)
    
    # 3) Проверка на unreleased (Coming soon / TBD / Q1 2026 и т.п.)
    # КРИТИЧНО: даже в мягком режиме исключаем unreleased
    if release_date_str:
        unreleased_keywords = [
            "coming soon", "tbd", "q1 2025", "q2 2025", "q3 2025", "q4 2025",
            "q1 2026", "q2 2026", "q3 2026", "q4 2026",
            "q1 2027", "q2 2027", "q3 2027", "q4 2027",
        ]
        release_date_lower = release_date_str.lower()
        if any(keyword in release_date_lower for keyword in unreleased_keywords):
            breakdown["exclude_reasons"].append("unreleased_or_unknown_date")
            return (False, "unreleased_or_unknown_date", breakdown)
    
    # 4) Rebound Window
    release_date = parse_release_date(release_date_str)
    if strict_window:
        window_ok, window_reason = is_in_rebound_window(release_date, min_months, max_months)
        if not window_ok:
            breakdown["exclude_reasons"].append(window_reason)
            return (False, window_reason, breakdown)
    else:
        # Мягкий режим: пропускаем только очень новые (< 1 месяца)
        # Если release_date не распарсилась - НЕ исключаем (может быть needs_review)
        if release_date:
            age_months = (datetime.now().year - release_date.year) * 12 + (datetime.now().month - release_date.month)
            if age_months < 1:
                breakdown["exclude_reasons"].append("too_new")
                return (False, "too_new", breakdown)
            # В мягком режиме не исключаем старые игры автоматически
        # Если release_date не распарсилась - ПРОПУСКАЕМ (не убиваем весь поток)
    
    # Все проверки пройдены
    breakdown["eligible"] = True
    return (True, None, breakdown)
