"""
Engine v5: Функции интерпретации сигналов для TrendsBrain.
Каждая функция возвращает структурированный объект с валидностью, скором, объяснением и флагами риска.
"""
from typing import Dict, Any, Optional, List
from datetime import date
import logging

logger = logging.getLogger(__name__)


def interpret_steam(
    reviews_delta_7d: Optional[int],
    reviews_delta_1d: Optional[int],
    positive_ratio: Optional[float],
    reviews_total: Optional[int],
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Интерпретация Steam сигналов.
    
    Правила:
    - Steam - единственный источник подтверждения
    - Отрицательная динамика может обнулить social score
    - Качество (positive_ratio) важно для валидации
    
    Returns:
        {
            "valid": bool,
            "score": int (0-100),
            "signal_strength": "weak" | "medium" | "strong",
            "reason": str,
            "risk_flags": List[str]
        }
    """
    result = {
        "valid": False,
        "score": 0,
        "signal_strength": "weak",
        "reason": "",
        "risk_flags": []
    }
    
    # Проверка наличия данных
    if reviews_delta_7d is None and reviews_delta_1d is None and positive_ratio is None:
        result["reason"] = "Нет данных Steam"
        return result
    
    # Отрицательная динамика - критический флаг
    if reviews_delta_7d is not None and reviews_delta_7d < 0:
        result["risk_flags"].append("Отрицательная динамика Steam может обнулить social score")
        result["reason"] = f"Падение отзывов: {reviews_delta_7d} за 7 дней"
        return result
    
    # Вычисляем score на основе delta_7d
    score = 0
    signal_strength = "weak"
    
    if reviews_delta_7d is not None:
        if reviews_delta_7d >= 150:
            score = 80
            signal_strength = "strong"
            result["reason"] = f"Сильный рост: +{reviews_delta_7d} отзывов за 7 дней"
        elif reviews_delta_7d >= 50:
            score = 50
            signal_strength = "medium"
            result["reason"] = f"Умеренный рост: +{reviews_delta_7d} отзывов за 7 дней"
        elif reviews_delta_7d >= 10:
            score = 25
            signal_strength = "weak"
            result["reason"] = f"Слабый рост: +{reviews_delta_7d} отзывов за 7 дней"
        else:
            result["reason"] = f"Минимальный рост: +{reviews_delta_7d} отзывов за 7 дней"
    
    # Корректировка по качеству (positive_ratio)
    if positive_ratio is not None:
        if positive_ratio < 0.70:
            score = max(0, score - 20)
            result["risk_flags"].append(f"Низкое качество: {positive_ratio*100:.0f}% положительных")
        elif positive_ratio >= 0.90:
            score = min(100, score + 10)
            if not result["reason"]:
                result["reason"] = f"Высокое качество: {positive_ratio*100:.0f}% положительных"
            else:
                result["reason"] += f", качество {positive_ratio*100:.0f}%"
    
    # Бонус за масштаб (если есть достаточное количество отзывов)
    if reviews_total and reviews_total >= 100:
        scale_bonus = min(10, (reviews_total / 1000.0) * 10)
        score = min(100, score + scale_bonus)
    
    result["valid"] = score > 0
    result["score"] = score
    result["signal_strength"] = signal_strength
    
    if not result["reason"]:
        result["reason"] = "Steam данные присутствуют, но рост минимален"
    
    return result


def interpret_reddit(
    reddit_posts_count_7d: Optional[int],
    reddit_velocity: Optional[int],
    reddit_comments_count_7d: Optional[int],
    reddit_uniqueness: Optional[int],
    context: Dict[str, Any],
    steam_confirmed: bool
) -> Dict[str, Any]:
    """
    Интерпретация Reddit сигналов.
    
    Правила:
    - Reddit не может быть главным драйвером без Steam
    - Reddit в early-stage усиливает confidence, а не score
    - Reddit без velocity = шум
    
    Returns:
        {
            "valid": bool,
            "score": int (0-30),
            "signal_strength": "weak" | "medium" | "strong",
            "reason": str,
            "risk_flags": List[str]
        }
    """
    result = {
        "valid": False,
        "score": 0,
        "signal_strength": "weak",
        "reason": "",
        "risk_flags": []
    }
    
    # Проверка наличия данных
    if not reddit_posts_count_7d or reddit_posts_count_7d == 0:
        result["reason"] = "Нет данных Reddit"
        return result
    
    # Правило: Reddit без velocity = шум
    if reddit_velocity is None or reddit_velocity <= 0:
        result["risk_flags"].append("Reddit без velocity = шум, не засчитывается")
        result["reason"] = f"{reddit_posts_count_7d} постов, но нет роста (velocity)"
        return result
    
    # Правило: Reddit не может быть главным драйвером без Steam
    if not steam_confirmed:
        # В early-stage Reddit усиливает confidence, но не score
        if context.get("stage") == "early":
            result["valid"] = True
            result["score"] = 5  # Минимальный score для early signal
            result["signal_strength"] = "weak"
            result["reason"] = f"Ранний сигнал: {reddit_posts_count_7d} постов, velocity +{reddit_velocity} (требуется подтверждение Steam)"
            result["risk_flags"].append("Reddit без Steam подтверждения - только ранний индикатор")
            return result
        else:
            result["risk_flags"].append("Reddit без Steam подтверждения - не засчитывается")
            result["reason"] = f"{reddit_posts_count_7d} постов, но нет Steam подтверждения"
            return result
    
    # Reddit с Steam подтверждением - валидный сигнал
    result["valid"] = True
    
    # Вычисляем score на основе количества постов и velocity
    base_score = min(15, reddit_posts_count_7d * 1.5)
    
    # Бонус за velocity
    if reddit_velocity and reddit_velocity > 0:
        velocity_bonus = min(5, reddit_velocity * 0.5)
        base_score += velocity_bonus
    
    # Бонус за комментарии (активность)
    if reddit_comments_count_7d and reddit_comments_count_7d > 0:
        comments_bonus = min(3, reddit_comments_count_7d / 50.0)
        base_score += comments_bonus
    
    # Бонус за уникальность (разные сабреддиты)
    if reddit_uniqueness and reddit_uniqueness > 1:
        uniqueness_bonus = min(2, reddit_uniqueness * 0.5)
        base_score += uniqueness_bonus
    
    result["score"] = min(30, int(base_score))
    
    # Определяем signal_strength
    if result["score"] >= 20:
        result["signal_strength"] = "strong"
    elif result["score"] >= 10:
        result["signal_strength"] = "medium"
    else:
        result["signal_strength"] = "weak"
    
    result["reason"] = f"Обсуждения в Reddit: {reddit_posts_count_7d} постов, velocity +{reddit_velocity}"
    if reddit_comments_count_7d:
        result["reason"] += f", {reddit_comments_count_7d} комментариев"
    
    return result


def interpret_youtube(
    youtube_videos_count_7d: Optional[int],
    youtube_velocity: Optional[int],
    youtube_views_7d: Optional[int],
    youtube_channel_quality: Optional[float],
    context: Dict[str, Any],
    steam_confirmed: bool,
    reddit_confirmed: bool
) -> Dict[str, Any]:
    """
    Интерпретация YouTube сигналов.
    
    Правила:
    - YouTube учитывается ТОЛЬКО при росте velocity
    - Должно быть совпадение с Reddit ИЛИ Steam
    - Одиночные видео не засчитываются
    
    Returns:
        {
            "valid": bool,
            "score": int (0-30),
            "signal_strength": "weak" | "medium" | "strong",
            "reason": str,
            "risk_flags": List[str]
        }
    """
    result = {
        "valid": False,
        "score": 0,
        "signal_strength": "weak",
        "reason": "",
        "risk_flags": []
    }
    
    # Проверка наличия данных
    if not youtube_videos_count_7d or youtube_videos_count_7d == 0:
        result["reason"] = "Нет данных YouTube"
        return result
    
    # Правило: одиночные видео не засчитываются
    if youtube_videos_count_7d < 2:
        result["risk_flags"].append("Одиночное видео не засчитывается")
        result["reason"] = f"Только {youtube_videos_count_7d} видео (минимум 2)"
        return result
    
    # Правило: YouTube учитывается ТОЛЬКО при росте velocity
    if youtube_velocity is None or youtube_velocity <= 0:
        result["risk_flags"].append("YouTube без velocity не засчитывается")
        result["reason"] = f"{youtube_videos_count_7d} видео, но нет роста (velocity)"
        return result
    
    # Правило: должно быть совпадение с Reddit ИЛИ Steam
    if not steam_confirmed and not reddit_confirmed:
        result["risk_flags"].append("YouTube без совпадения с Reddit/Steam - не засчитывается")
        result["reason"] = f"{youtube_videos_count_7d} видео, но нет подтверждения от других источников"
        return result
    
    # YouTube с подтверждением - валидный сигнал
    result["valid"] = True
    
    # Вычисляем score на основе количества видео и velocity
    base_score = min(15, youtube_videos_count_7d * 2.0)
    
    # Бонус за velocity
    if youtube_velocity and youtube_velocity > 0:
        velocity_bonus = min(5, youtube_velocity * 0.5)
        base_score += velocity_bonus
    
    # Бонус за просмотры (масштаб)
    if youtube_views_7d and youtube_views_7d > 1000:
        views_bonus = min(5, (youtube_views_7d / 10000.0) * 5)
        base_score += views_bonus
    
    # Бонус за качество каналов
    if youtube_channel_quality and youtube_channel_quality > 3.0:
        quality_bonus = min(3, youtube_channel_quality * 0.5)
        base_score += quality_bonus
    
    result["score"] = min(30, int(base_score))
    
    # Определяем signal_strength
    if result["score"] >= 20:
        result["signal_strength"] = "strong"
    elif result["score"] >= 10:
        result["signal_strength"] = "medium"
    else:
        result["signal_strength"] = "weak"
    
    result["reason"] = f"Видео на YouTube: {youtube_videos_count_7d} видео, velocity +{youtube_velocity}"
    if youtube_views_7d:
        result["reason"] += f", {youtube_views_7d:,} просмотров"
    
    return result


def interpret_news(
    steam_news_posts_7d: Optional[int],
    steam_news_velocity: Optional[int],
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Интерпретация Steam News сигналов.
    
    Правила:
    - Усиливает "why_now"
    - Влияет на catalyst score, но не на confirmation
    - Новости без velocity менее значимы
    
    Returns:
        {
            "valid": bool,
            "score": int (0-20),
            "signal_strength": "weak" | "medium" | "strong",
            "reason": str,
            "risk_flags": List[str]
        }
    """
    result = {
        "valid": False,
        "score": 0,
        "signal_strength": "weak",
        "reason": "",
        "risk_flags": []
    }
    
    # Проверка наличия данных
    if not steam_news_posts_7d or steam_news_posts_7d == 0:
        result["reason"] = "Нет новостей Steam"
        return result
    
    result["valid"] = True
    
    # Вычисляем score: 1 новость = 10 баллов, 2+ = 20
    if steam_news_posts_7d >= 2:
        result["score"] = 20
        result["signal_strength"] = "strong"
        result["reason"] = f"Вышло {steam_news_posts_7d} обновлений за 7 дней"
    else:
        result["score"] = 10
        result["signal_strength"] = "medium"
        result["reason"] = f"Вышло обновление за 7 дней"
    
    # Бонус за velocity (рост новостей)
    if steam_news_velocity and steam_news_velocity > 0:
        velocity_bonus = min(5, steam_news_velocity * 2.0)
        result["score"] = min(20, result["score"] + int(velocity_bonus))
        result["reason"] += f", рост новостей +{steam_news_velocity}"
    
    return result
