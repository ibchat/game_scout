"""
Deal Intent Scorer
Вычисляет intent_score и quality_score для игр.
Детерминированная логика без фантазий.
"""
import logging
import math
from typing import Dict, Any, List, Optional
from datetime import date, datetime
import re

from apps.worker.config.deal_intent_config import (
    INTENT_KEYWORDS,
    BEHAVIORAL_INTENT_KEYWORDS,
    BEHAVIORAL_INTENT_SOURCES,
    BEHAVIORAL_INTENT_WEIGHTS,
    STRUCTURAL_INTENT_WEIGHTS,
    TEMPORAL_BOOST_WEIGHTS,
    FRESHNESS_THRESHOLDS,
    INTENT_WEIGHTS,  # Legacy для обратной совместимости
    KNOWN_PUBLISHERS,
    QUALITY_THRESHOLDS,
    QUALITY_WEIGHTS,
    INTENT_SCORE_MIN,
    INTENT_SCORE_MAX,
    QUALITY_SCORE_MIN,
    QUALITY_SCORE_MAX,
    BEHAVIORAL_INTENT_MAX_SCORE_WITHOUT_SIGNALS,
    VERDICTS
)

logger = logging.getLogger(__name__)


def detect_intent_keywords(text: str) -> Dict[str, bool]:
    """
    Обнаруживает intent keywords в тексте.
    
    Args:
        text: Текст для анализа (lowercase)
        
    Returns:
        Dict с флагами найденных интентов
    """
    if not text:
        return {}
    
    text_lower = text.lower()
    detected = {}
    
    for intent_type, keywords in INTENT_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in text_lower:
                detected[intent_type] = True
                break
    
    return detected


def calculate_intent_score(
    app_data: Dict[str, Any],
    signals: List[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Вычисляет intent_score v3 для игры (3-слойная архитектура).
    
    Args:
        app_data: Данные игры из steam_app_cache / steam_review_daily
        signals: Список внешних сигналов (deal_intent_signal)
        
    Returns:
        {
            "intent_score": int (0-100),
            "intent_reasons": List[str],
            "matched_signals": int,
            "behavioral_intent_score": int,
            "structural_intent_score": int,
            "temporal_boost_score": int
        }
    """
    signals = signals or []
    behavioral_score = 0
    structural_score = 0
    temporal_score = 0
    reasons = []
    matched_signals_count = 0
    
    # ========================================================================
    # СЛОЙ 1: BEHAVIORAL INTENT (ОБЯЗАТЕЛЬНЫЙ, главный слой)
    # ========================================================================
    behavioral_reasons = []
    now = datetime.utcnow()
    freshness_days = FRESHNESS_THRESHOLDS.get("external_signal_days", 60)
    
    for signal in signals:
        signal_text = signal.get("text", "") or ""
        signal_source = (signal.get("source", "") or "").lower()
        published_at = signal.get("published_at")
        created_at = signal.get("created_at")
        
        # Проверяем свежесть сигнала
        signal_date = published_at or created_at
        is_fresh = False
        if signal_date:
            if isinstance(signal_date, str):
                try:
                    signal_date = datetime.fromisoformat(signal_date.replace('Z', '+00:00'))
                except:
                    signal_date = None
            if signal_date:
                days_ago = (now - signal_date.replace(tzinfo=None)).days
                is_fresh = days_ago <= freshness_days
        
        # Проверяем источник (должен быть в списке Behavioral Intent источников)
        if signal_source not in BEHAVIORAL_INTENT_SOURCES:
            continue
        
        if not signal_text:
            continue
        
        # Обнаруживаем Behavioral Intent keywords
        detected = detect_intent_keywords(signal_text)
        if detected:
            matched_signals_count += 1
            for intent_type in detected.keys():
                weight = BEHAVIORAL_INTENT_WEIGHTS.get(intent_type, 0)
                if weight > 0:
                    behavioral_score += weight
                    freshness_label = f" ({days_ago} дней назад)" if is_fresh and signal_date else ""
                    behavioral_reasons.append(f"{intent_type}: found in {signal_source}{freshness_label}")
    
    reasons.extend(behavioral_reasons)
    
    # ========================================================================
    # СЛОЙ 2: STRUCTURAL INTENT (вспомогательный)
    # ========================================================================
    structural_reasons = []
    
    # 2.1 Publisher status
    publisher_name = (app_data.get("publisher_name") or "").lower()
    developer_name = (app_data.get("developer_name") or "").lower()
    stage = app_data.get("stage", "").lower()
    
    if not publisher_name or publisher_name == "":
        structural_score += STRUCTURAL_INTENT_WEIGHTS.get("no_publisher_on_steam", 0)
        structural_reasons.append("no_publisher_on_steam")
    elif publisher_name == developer_name:
        if stage in ("demo", "coming_soon"):
            structural_score += STRUCTURAL_INTENT_WEIGHTS.get("self_published_early", 0)
            structural_reasons.append("self_published_early")
        else:
            structural_score += STRUCTURAL_INTENT_WEIGHTS.get("self_published", 0)
            structural_reasons.append("self_published")
    else:
        # Проверяем known publishers (penalty)
        for known_pub in KNOWN_PUBLISHERS:
            if known_pub.lower() in publisher_name:
                structural_score += STRUCTURAL_INTENT_WEIGHTS.get("known_publisher_penalty", 0)
                structural_reasons.append("known_publisher_penalty")
                break
        # Если publisher есть но не известный - небольшой минус
        if "known_publisher_penalty" not in structural_reasons:
            structural_score += STRUCTURAL_INTENT_WEIGHTS.get("has_publisher", 0)
            structural_reasons.append("has_publisher")
    
    # 2.2 Stage bonus
    release_date = app_data.get("release_date")
    release_date_obj = None
    
    if release_date:
        try:
            if isinstance(release_date, str):
                release_date_obj = datetime.fromisoformat(release_date.replace('Z', '+00:00')).date()
            elif isinstance(release_date, date):
                release_date_obj = release_date
        except Exception:
            pass
    
    if stage == "demo":
        structural_score += STRUCTURAL_INTENT_WEIGHTS.get("stage_demo", 0)
        structural_reasons.append("stage_demo")
    elif stage == "coming_soon":
        structural_score += STRUCTURAL_INTENT_WEIGHTS.get("stage_coming_soon", 0)
        structural_reasons.append("stage_coming_soon")
    elif stage == "early_access":
        if release_date_obj:
            age_months = (date.today() - release_date_obj).days / 30.0
            if age_months < 6:
                structural_score += STRUCTURAL_INTENT_WEIGHTS.get("stage_early_access_fresh", 0)
                structural_reasons.append("stage_early_access_fresh")
            else:
                structural_score += STRUCTURAL_INTENT_WEIGHTS.get("stage_early_access", 0)
                structural_reasons.append("stage_early_access")
        else:
            structural_score += STRUCTURAL_INTENT_WEIGHTS.get("stage_early_access", 0)
            structural_reasons.append("stage_early_access")
    elif stage == "released":
        if release_date_obj:
            age_months = (date.today() - release_date_obj).days / 30.0
            if age_months <= 3:
                structural_score += STRUCTURAL_INTENT_WEIGHTS.get("stage_released_fresh", 0)
                structural_reasons.append("stage_released_fresh")
            elif age_months <= 12:
                structural_score += STRUCTURAL_INTENT_WEIGHTS.get("stage_released_fresh", 0)  # Используем тот же вес
                structural_reasons.append("stage_released")
            else:
                structural_score += STRUCTURAL_INTENT_WEIGHTS.get("old_release_penalty", 0)
                structural_reasons.append("stage_penalty_released")
        else:
            structural_score += STRUCTURAL_INTENT_WEIGHTS.get("old_release_penalty", 0)
            structural_reasons.append("stage_released_unknown")
    
    # 2.3 External links
    external_links = app_data.get("external_links") or {}
    has_website = bool(app_data.get("website")) or bool(external_links.get("website"))
    has_discord = bool(app_data.get("discord")) or bool(external_links.get("discord"))
    
    if has_website:
        structural_score += STRUCTURAL_INTENT_WEIGHTS.get("has_website", 0)
        structural_reasons.append("has_website")
    if has_discord:
        structural_score += STRUCTURAL_INTENT_WEIGHTS.get("has_discord", 0)
        structural_reasons.append("has_discord")
    
    reasons.extend(structural_reasons)
    
    # ========================================================================
    # СЛОЙ 3: TEMPORAL BOOST (временной слой)
    # ========================================================================
    temporal_reasons = []
    
    # 3.1 Fresh Steam page (< 6 месяцев)
    # Проверяем через trends_seed_apps.created_at или steam_app_cache.created_at
    steam_page_created = app_data.get("steam_page_created_at") or app_data.get("created_at")
    if steam_page_created:
        try:
            if isinstance(steam_page_created, str):
                steam_page_created = datetime.fromisoformat(steam_page_created.replace('Z', '+00:00'))
            if isinstance(steam_page_created, datetime):
                months_ago = (now - steam_page_created.replace(tzinfo=None)).days / 30.0
                if months_ago < FRESHNESS_THRESHOLDS.get("steam_page_months", 6):
                    temporal_score += TEMPORAL_BOOST_WEIGHTS.get("fresh_steam_page", 0)
                    temporal_reasons.append(f"fresh_steam_page: {int(months_ago)} месяцев")
        except Exception:
            pass
    
    # 3.2 Recent signal (< 60 дней) - уже учтено в Behavioral Intent, но добавляем boost
    if matched_signals_count > 0:
        # Проверяем самый свежий сигнал
        freshest_signal = None
        for signal in signals:
            signal_date = signal.get("published_at") or signal.get("created_at")
            if signal_date:
                if isinstance(signal_date, str):
                    try:
                        signal_date = datetime.fromisoformat(signal_date.replace('Z', '+00:00'))
                    except:
                        continue
                if not freshest_signal or signal_date > freshest_signal:
                    freshest_signal = signal_date
        
        if freshest_signal:
            days_ago = (now - freshest_signal.replace(tzinfo=None)).days
            if days_ago <= freshness_days:
                temporal_score += TEMPORAL_BOOST_WEIGHTS.get("recent_signal", 0)
                temporal_reasons.append(f"recent_signal: {days_ago} дней назад")
    
    # 3.3 Recent festival (< 90 дней) - пока пропускаем, так как нет данных о фестивалях
    # TODO: добавить когда будет источник данных о фестивалях
    
    # 3.4 Recent announcement - проверяем через signals с типом "announcement"
    for signal in signals:
        signal_type = (signal.get("signal_type") or "").lower()
        if "announcement" in signal_type or "announce" in signal_type:
            signal_date = signal.get("published_at") or signal.get("created_at")
            if signal_date:
                if isinstance(signal_date, str):
                    try:
                        signal_date = datetime.fromisoformat(signal_date.replace('Z', '+00:00'))
                    except:
                        continue
                days_ago = (now - signal_date.replace(tzinfo=None)).days
                if days_ago <= 30:  # Анонс за последний месяц
                    temporal_score += TEMPORAL_BOOST_WEIGHTS.get("recent_announcement", 0)
                    temporal_reasons.append(f"recent_announcement: {days_ago} дней назад")
                    break
    
    reasons.extend(temporal_reasons)
    
    # ========================================================================
    # ОБЪЕДИНЕНИЕ СЛОЁВ И ОГРАНИЧЕНИЯ
    # ========================================================================
    total_score = behavioral_score + structural_score + temporal_score
    
    # ВАЖНО: Если Behavioral Intent = 0, максимальный Intent Score ограничен
    if behavioral_score == 0:
        total_score = min(total_score, BEHAVIORAL_INTENT_MAX_SCORE_WITHOUT_SIGNALS)
        if total_score > BEHAVIORAL_INTENT_MAX_SCORE_WITHOUT_SIGNALS:
            reasons.append(f"behavioral_intent_zero: ограничен до {BEHAVIORAL_INTENT_MAX_SCORE_WITHOUT_SIGNALS}")
    
    # Clamp score
    total_score = max(INTENT_SCORE_MIN, min(INTENT_SCORE_MAX, int(total_score)))
    
    # Обеспечиваем минимум 4 причины в breakdown
    if len(reasons) < 4:
        has_demo = app_data.get("has_demo", False)
        all_reviews = app_data.get("all_reviews_count") or 0
        if not has_demo and stage != "demo":
            reasons.append("no_demo")
        if not has_website and not has_discord:
            reasons.append("no_contacts")
        if all_reviews == 0:
            reasons.append("zero_reviews")
        elif all_reviews < 10:
            reasons.append("very_few_reviews")
    
    # Логирование для отладки
    logger.debug(
        f"Intent score v3 calculation: app_id={app_data.get('app_id', 'unknown')}, "
        f"total={total_score}, behavioral={int(behavioral_score)}, "
        f"structural={int(structural_score)}, temporal={int(temporal_score)}, "
        f"reasons={len(reasons)}"
    )
    
    return {
        "intent_score": total_score,
        "intent_reasons": reasons,
        "matched_signals": matched_signals_count,
        "behavioral_intent_score": int(behavioral_score),
        "structural_intent_score": int(structural_score),
        "temporal_boost_score": int(temporal_score)
    }
    
    # 2. Проверяем publisher status (v2.0: дифференцированная оценка)
    publisher_name = (app_data.get("publisher_name") or "").lower()
    developer_name = (app_data.get("developer_name") or "").lower()
    
    # Нет publisher на Steam = потенциальный intent
    if not publisher_name or publisher_name == "":
        score += 18  # Увеличено для разнообразия
        reasons.append("no_publisher_on_steam")
    elif publisher_name == developer_name:
        # Self-published - разные веса в зависимости от стадии
        stage = app_data.get("stage", "").lower()
        if stage in ("demo", "coming_soon"):
            score += 20  # Self-published + ранняя стадия = больше intent
            reasons.append("self_published_early")
        else:
            score += 12  # Self-published но уже released
            reasons.append("self_published")
    else:
        # Проверяем known publishers (penalty)
        for known_pub in KNOWN_PUBLISHERS:
            if known_pub.lower() in publisher_name:
                score += INTENT_WEIGHTS.get("known_publisher_penalty", 0)
                reasons.append("known_publisher_penalty")
                break
        # Если publisher есть но не известный - небольшой минус
        if score == 0:  # Не было penalty
            score -= 3
            reasons.append("has_publisher")
    
    # 3. Stage bonus (v2.0: более дифференцированная шкала)
    stage = app_data.get("stage", "").lower()
    release_date = app_data.get("release_date")
    release_date_obj = None
    
    if release_date:
        try:
            if isinstance(release_date, str):
                release_date_obj = datetime.fromisoformat(release_date.replace('Z', '+00:00')).date()
            elif isinstance(release_date, date):
                release_date_obj = release_date
        except Exception:
            pass
    
    if stage == "demo":
        score += 22  # Demo = лучше для сделки (увеличено)
        reasons.append("stage_demo")
    elif stage == "coming_soon":
        score += 18  # Скоро релиз = окно для издателя (увеличено)
        reasons.append("stage_coming_soon")
    elif stage == "early_access":
        # EA - бонус зависит от возраста
        if release_date_obj:
            age_months = (date.today() - release_date_obj).days / 30.0
            if age_months < 6:
                score += 15  # Свежий EA
                reasons.append("stage_early_access_fresh")
            elif age_months < 18:
                score += 10  # Средний EA
                reasons.append("stage_early_access")
            else:
                score += 5  # Старый EA
                reasons.append("stage_early_access_old")
        else:
            score += 10
            reasons.append("stage_early_access")
    elif stage == "released":
        # Released - штраф зависит от возраста
        if release_date_obj:
            age_months = (date.today() - release_date_obj).days / 30.0
            if age_months <= 3:
                score += 8  # Очень свежий релиз
                reasons.append("stage_released_fresh")
            elif age_months <= 12:
                score += 3  # Свежий релиз
                reasons.append("stage_released")
            elif age_months <= 24:
                score -= 5  # Средний релиз
                reasons.append("stage_released_medium")
            else:
                score -= 15  # Старый релиз = большой штраф
                reasons.append("stage_penalty_released")
        else:
            score -= 5
            reasons.append("stage_released_unknown")
    
    # 4. Old release penalty (релизы старше 4 лет)
    release_date = app_data.get("release_date")
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
                if age_years > 4:
                    score += INTENT_WEIGHTS.get("old_release_penalty", 0)
                    reasons.append("old_release_penalty")
        except Exception as e:
            logger.warning(f"Failed to parse release_date: {e}")
    
    # 5. External links bonus (если есть контакты: website или discord в steam_app_cache)
    # Проверяем наличие website или discord в данных
    steam_url = app_data.get("steam_url") or ""
    # Если есть внешние ссылки в external_links или website/discord в данных
    external_links = app_data.get("external_links") or {}
    has_website = bool(app_data.get("website")) or bool(external_links.get("website")) or bool(steam_url and "steampowered.com" not in steam_url.lower())
    has_discord = bool(app_data.get("discord")) or bool(external_links.get("discord")) or any("discord" in str(link).lower() for link in (external_links.values() if isinstance(external_links, dict) else []))
    
    if has_website:
        score += 5
        reasons.append("has_website")
    if has_discord:
        score += 5
        reasons.append("has_discord")
    
    # 6. Reviews growth bonus (v2.0: более гранулярная шкала)
    recent_reviews_30d = app_data.get("recent_reviews_count_30d") or app_data.get("reviews_30d") or 0
    all_reviews = app_data.get("all_reviews_count") or 0
    
    if recent_reviews_30d > 0:
        # Более дифференцированная шкала для разных уровней активности
        if recent_reviews_30d >= 200:
            growth_bonus = 25  # Очень высокая активность
        elif recent_reviews_30d >= 100:
            growth_bonus = 20
        elif recent_reviews_30d >= 50:
            growth_bonus = 15
        elif recent_reviews_30d >= 20:
            growth_bonus = 12
        elif recent_reviews_30d >= 10:
            growth_bonus = 8
        elif recent_reviews_30d >= 5:
            growth_bonus = 5
        else:
            growth_bonus = 3
        score += growth_bonus
        reasons.append(f"reviews_30d_{recent_reviews_30d}")
    else:
        # Marketing weakness proxy: мало отзывов = нужна помощь
        if all_reviews == 0:
            score += 4  # Нет отзывов = нужен маркетинг
            reasons.append("no_reviews_need_marketing")
        elif all_reviews < 10:
            score += 3  # Очень мало отзывов
            reasons.append("low_reviews_need_marketing")
        elif all_reviews < 50:
            score += 2  # Мало отзывов
            reasons.append("few_reviews")
        elif all_reviews >= 1000:
            # Много отзывов но нет активности - странно, возможно уже успешная
            score -= 2
            reasons.append("many_reviews_no_activity")
    
    # 7. Has demo bonus (v2.0: комбинация с stage)
    has_demo = app_data.get("has_demo", False)
    if has_demo:
        if stage in ("demo", "coming_soon"):
            score += 6  # Demo + ранняя стадия = больше intent
            reasons.append("has_demo_early_stage")
        else:
            score += 4  # Demo но уже released
            reasons.append("has_demo")
    
    # 8. Price indicator (v2.0: более дифференцированная оценка)
    price_eur = app_data.get("price_eur") or app_data.get("price") or 0
    if price_eur == 0:
        score += 4  # Бесплатная игра = больше потенциал для издателя
        reasons.append("free_game")
    elif price_eur > 0 and price_eur < 5:
        score += 3  # Очень дешёвая
        reasons.append("very_low_price")
    elif price_eur >= 5 and price_eur < 10:
        score += 2  # Дешёвая
        reasons.append("low_price")
    elif price_eur >= 10 and price_eur < 20:
        score += 1  # Средняя цена
        reasons.append("medium_price")
    # Дорогие игры (>20) не получают бонус
    
    # 9. Marketing weakness proxy: низкая активность при наличии контента
    if has_demo and recent_reviews_30d == 0 and all_reviews < 50:
        score += 5  # Есть demo но нет активности = нужен маркетинг
        reasons.append("demo_no_traction")
    
    # Clamp score
    score = max(INTENT_SCORE_MIN, min(INTENT_SCORE_MAX, score))
    
    # ВАЖНО: НЕ обнуляем score если нет сигналов - учитываем publisher status, stage и другие факторы
    
    # v2.0: Обеспечиваем минимум 4 причины в breakdown
    # Если причин меньше 4, добавляем информационные факторы
    if len(reasons) < 4:
        # Добавляем факторы на основе данных
        if not has_demo and stage != "demo":
            reasons.append("no_demo")
        if not has_website and not has_discord:
            reasons.append("no_contacts")
        if all_reviews == 0:
            reasons.append("zero_reviews")
        elif all_reviews < 10:
            reasons.append("very_few_reviews")
    
    # Возвращаем все причины (не ограничиваем для breakdown)
    top_reasons = reasons
    
    # Логирование для отладки (согласно ТЗ)
    logger.debug(f"Intent score calculation: app_id={app_data.get('app_id', 'unknown')}, score={int(score)}, reasons={top_reasons}")
    
    return {
        "intent_score": int(score),
        "intent_reasons": top_reasons,
        "matched_signals": matched_signals_count
    }


def calculate_quality_score(app_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Вычисляет quality_score v3 для игры (готовность к издателю, не успешность).
    
    Args:
        app_data: Данные игры из steam_app_cache / steam_review_daily
        
    Returns:
        {
            "quality_score": int (0-100),
            "quality_reasons": List[str]
        }
    """
    score = 0
    reasons = []
    
    # 1. Visual Quality (0..20) - готовность к презентации
    # Проверяем наличие капсул, трейлера, скриншотов
    has_trailer = bool(app_data.get("trailer_url")) or bool(app_data.get("header_image"))
    has_capsule = bool(app_data.get("capsule_image_url")) or bool(app_data.get("header_image"))
    
    visual_score = 0
    if has_trailer and has_capsule:
        visual_score = QUALITY_WEIGHTS.get("visual_quality", 20)
        reasons.append("visual_quality: есть трейлер и капсула")
    elif has_trailer or has_capsule:
        visual_score = QUALITY_WEIGHTS.get("visual_quality", 20) // 2
        reasons.append("visual_quality: есть трейлер или капсула")
    else:
        reasons.append("visual_quality: нет трейлера и капсулы")
    
    score += visual_score
    
    # 2. Clear USP (0..15) - чёткость уникального предложения
    # Проверяем через наличие описания, тегов, жанров
    description = app_data.get("short_description") or app_data.get("description") or ""
    tags = app_data.get("tags") or []
    genres = app_data.get("genres") or []
    
    usp_score = 0
    if description and len(description) > 50:  # Есть описание
        if tags or genres:  # Есть теги/жанры
            usp_score = QUALITY_WEIGHTS.get("clear_usp", 15)
            reasons.append("clear_usp: есть описание и теги")
        else:
            usp_score = QUALITY_WEIGHTS.get("clear_usp", 15) // 2
            reasons.append("clear_usp: есть описание, нет тегов")
    else:
        reasons.append("clear_usp: нет описания")
    
    score += usp_score
    
    # 3. Demo Reviews (0..15) - отзывы демо (если есть)
    has_demo = app_data.get("has_demo", False)
    demo_reviews = 0
    if has_demo:
        # Если есть демо, проверяем отзывы (предполагаем что часть отзывов относится к демо)
        all_reviews = app_data.get("all_reviews_count") or 0
        if all_reviews > 0:
            demo_reviews = min(all_reviews, 100)  # Ограничиваем для оценки
            demo_score = QUALITY_WEIGHTS.get("demo_reviews", 15)
            reasons.append(f"demo_reviews: есть демо, {all_reviews} отзывов")
        else:
            demo_score = QUALITY_WEIGHTS.get("demo_reviews", 15) // 2
            reasons.append("demo_reviews: есть демо, нет отзывов")
        score += demo_score
    
    # 4. Update Tempo (0..12) - темп апдейтов
    # Проверяем через последнее обновление (если есть)
    last_update = app_data.get("last_update_date") or app_data.get("updated_at")
    update_tempo_score = 0
    if last_update:
        try:
            if isinstance(last_update, str):
                last_update = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
            if isinstance(last_update, datetime):
                days_since_update = (datetime.utcnow() - last_update.replace(tzinfo=None)).days
                if days_since_update <= 30:
                    update_tempo_score = QUALITY_WEIGHTS.get("update_tempo", 12)
                    reasons.append(f"update_tempo: обновление {days_since_update} дней назад")
                elif days_since_update <= 90:
                    update_tempo_score = QUALITY_WEIGHTS.get("update_tempo", 12) // 2
                    reasons.append(f"update_tempo: обновление {days_since_update} дней назад (старое)")
        except Exception:
            pass
    
    if update_tempo_score == 0:
        reasons.append("update_tempo: нет данных об обновлениях")
    
    score += update_tempo_score
    
    # 5. Team Activity (0..10) - активность команды
    # Проверяем через внешние ссылки (Discord, Twitter, сайт)
    external_links = app_data.get("external_links") or {}
    has_discord = bool(app_data.get("discord")) or bool(external_links.get("discord"))
    has_website = bool(app_data.get("website")) or bool(external_links.get("website"))
    
    team_activity_score = 0
    if has_discord and has_website:
        team_activity_score = QUALITY_WEIGHTS.get("team_activity", 10)
        reasons.append("team_activity: есть Discord и сайт")
    elif has_discord or has_website:
        team_activity_score = QUALITY_WEIGHTS.get("team_activity", 10) // 2
        reasons.append("team_activity: есть Discord или сайт")
    else:
        reasons.append("team_activity: нет внешних каналов")
    
    score += team_activity_score
    
    # 6. Adequate Scale (0..8) - адекватный масштаб (не AAA)
    # Проверяем через цену, теги, жанры
    price_eur = app_data.get("price_eur") or app_data.get("price") or 0
    adequate_scale_score = 0
    if price_eur > 0 and price_eur < 30:  # Не дорогая игра
        adequate_scale_score = QUALITY_WEIGHTS.get("adequate_scale", 8)
        reasons.append(f"adequate_scale: цена {price_eur}€ (не AAA)")
    elif price_eur == 0:  # Бесплатная
        adequate_scale_score = QUALITY_WEIGHTS.get("adequate_scale", 8) // 2
        reasons.append("adequate_scale: бесплатная игра")
    else:
        reasons.append(f"adequate_scale: цена {price_eur}€ (возможно AAA)")
    
    score += adequate_scale_score
    
    # 7. Positive Ratio (0..20) - готовность к масштабированию
    positive_ratio = app_data.get("positive_ratio") or app_data.get("all_positive_percent")
    if positive_ratio:
        if isinstance(positive_ratio, (int, float)):
            if positive_ratio >= 100:
                positive_ratio = positive_ratio / 100.0
        elif positive_ratio > 1.0:
            positive_ratio = positive_ratio / 100.0
        
        # Шкала для готовности к масштабированию
        if positive_ratio >= 0.85:
            ratio_score = QUALITY_WEIGHTS.get("positive_ratio", 20)
        elif positive_ratio >= 0.75:
            ratio_score = QUALITY_WEIGHTS.get("positive_ratio", 20) * 3 // 4
        elif positive_ratio >= 0.65:
            ratio_score = QUALITY_WEIGHTS.get("positive_ratio", 20) // 2
        else:
            ratio_score = QUALITY_WEIGHTS.get("positive_ratio", 20) // 4
        
        score += ratio_score
        reasons.append(f"positive_ratio: {int(positive_ratio*100)}%")
    
    # 8. Reviews 30d (0..15) - активность отзывов за 30 дней
    recent_reviews_30d = app_data.get("recent_reviews_count_30d") or app_data.get("reviews_30d") or 0
    if recent_reviews_30d > 0:
        # Логарифмическая шкала
        log_reviews = math.log10(recent_reviews_30d + 1)
        reviews_score = min(QUALITY_WEIGHTS.get("reviews_30d", 15), int(log_reviews * 5))
        score += reviews_score
        reasons.append(f"reviews_30d: {recent_reviews_30d} отзывов")
    
    # 9. Has Demo (0..10) - есть демо
    if has_demo:
        score += QUALITY_WEIGHTS.get("has_demo", 10)
        reasons.append("has_demo: есть демо")
    
    # Clamp score
    score = max(QUALITY_SCORE_MIN, min(QUALITY_SCORE_MAX, score))
    
    # Логирование для отладки
    logger.debug(f"Quality score v3 calculation: app_id={app_data.get('app_id', 'unknown')}, score={int(score)}, reasons={len(reasons)}")
    
    return {
        "quality_score": int(score),
        "quality_reasons": reasons
    }


def check_intent_freshness_gate(
    app_data: Dict[str, Any],
    signals: List[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Проверяет Intent Freshness Gate v3.
    Игра проходит gate, ТОЛЬКО ЕСЛИ есть ХОТЯ БЫ ОДНО:
    - Страница Steam создана/опубликована < 6 месяцев
    - Внешний сигнал намерения < 60 дней
    - Статус demo / coming soon / early access
    - Участие в фестивале < 90 дней
    
    Args:
        app_data: Данные игры
        signals: Внешние сигналы
        
    Returns:
        {
            "passes": bool,
            "reason": str,
            "freshness_factors": List[str]
        }
    """
    signals = signals or []
    freshness_factors = []
    now = datetime.utcnow()
    
    # 1. Страница Steam создана/опубликована < 6 месяцев
    steam_page_created = app_data.get("steam_page_created_at") or app_data.get("created_at")
    if steam_page_created:
        try:
            if isinstance(steam_page_created, str):
                steam_page_created = datetime.fromisoformat(steam_page_created.replace('Z', '+00:00'))
            if isinstance(steam_page_created, datetime):
                months_ago = (now - steam_page_created.replace(tzinfo=None)).days / 30.0
                if months_ago < FRESHNESS_THRESHOLDS.get("steam_page_months", 6):
                    freshness_factors.append(f"steam_page_fresh: {int(months_ago)} месяцев")
        except Exception:
            pass
    
    # 2. Внешний сигнал намерения < 60 дней
    freshness_days = FRESHNESS_THRESHOLDS.get("external_signal_days", 60)
    for signal in signals:
        signal_source = (signal.get("source", "") or "").lower()
        if signal_source not in BEHAVIORAL_INTENT_SOURCES:
            continue
        
        signal_date = signal.get("published_at") or signal.get("created_at")
        if signal_date:
            try:
                if isinstance(signal_date, str):
                    signal_date = datetime.fromisoformat(signal_date.replace('Z', '+00:00'))
                if isinstance(signal_date, datetime):
                    days_ago = (now - signal_date.replace(tzinfo=None)).days
                    if days_ago <= freshness_days:
                        freshness_factors.append(f"external_signal_fresh: {signal_source} ({days_ago} дней назад)")
                        break
            except Exception:
                continue
    
    # 3. Статус demo / coming soon / early access
    stage = (app_data.get("stage") or "").lower()
    if stage in ("demo", "coming_soon", "early_access"):
        freshness_factors.append(f"stage_fresh: {stage}")
    
    # 4. Участие в фестивале < 90 дней - пока пропускаем, так как нет данных
    
    passes = len(freshness_factors) > 0
    reason = "passes" if passes else "Нет актуального намерения"
    
    return {
        "passes": passes,
        "reason": reason,
        "freshness_factors": freshness_factors
    }


def check_success_penalty_gate(
    app_data: Dict[str, Any],
    intent_score: int
) -> Dict[str, Any]:
    """
    Проверяет Success Penalty Gate v3.
    Если игра выпущена > 18-24 месяцев и имеет высокие метрики успеха,
    Intent Score умножается на 0.1-0.3.
    
    Args:
        app_data: Данные игры
        intent_score: Текущий Intent Score
        
    Returns:
        {
            "penalty_applied": bool,
            "penalty_multiplier": float,
            "final_intent_score": int,
            "reason": str
        }
    """
    release_date = app_data.get("release_date")
    release_date_obj = None
    
    if release_date:
        try:
            if isinstance(release_date, str):
                release_date_obj = datetime.fromisoformat(release_date.replace('Z', '+00:00')).date()
            elif isinstance(release_date, date):
                release_date_obj = release_date
        except Exception:
            pass
    
    if not release_date_obj:
        return {
            "penalty_applied": False,
            "penalty_multiplier": 1.0,
            "final_intent_score": intent_score,
            "reason": "Нет данных о дате релиза"
        }
    
    age_months = (date.today() - release_date_obj).days / 30.0
    success_penalty_months = FRESHNESS_THRESHOLDS.get("success_penalty_months", 18)
    
    if age_months <= success_penalty_months:
        return {
            "penalty_applied": False,
            "penalty_multiplier": 1.0,
            "final_intent_score": intent_score,
            "reason": f"Игра свежая ({int(age_months)} месяцев)"
        }
    
    # Проверяем признаки успеха
    all_reviews = app_data.get("all_reviews_count") or 0
    recent_reviews_30d = app_data.get("recent_reviews_count_30d") or app_data.get("reviews_30d") or 0
    positive_ratio = app_data.get("positive_ratio") or app_data.get("all_positive_percent") or 0
    
    if isinstance(positive_ratio, (int, float)):
        if positive_ratio >= 100:
            positive_ratio = positive_ratio / 100.0
    elif positive_ratio > 1.0:
        positive_ratio = positive_ratio / 100.0
    
    # Признаки успеха
    is_successful = (
        all_reviews >= QUALITY_THRESHOLDS.get("success_penalty_reviews", 2000) or
        recent_reviews_30d >= QUALITY_THRESHOLDS.get("success_penalty_reviews_30d", 200) or
        (positive_ratio >= QUALITY_THRESHOLDS.get("success_penalty_positive_ratio", 0.90) and
         all_reviews >= QUALITY_THRESHOLDS.get("success_penalty_reviews_for_ratio", 1000))
    )
    
    if not is_successful:
        return {
            "penalty_applied": False,
            "penalty_multiplier": 1.0,
            "final_intent_score": intent_score,
            "reason": "Нет признаков успеха"
        }
    
    # Применяем penalty в зависимости от возраста
    if age_months >= 24:
        penalty_multiplier = 0.1  # Очень старый успешный релиз
    elif age_months >= 18:
        penalty_multiplier = 0.3  # Старый успешный релиз
    else:
        penalty_multiplier = 0.5  # Средний успешный релиз
    
    final_score = int(intent_score * penalty_multiplier)
    
    return {
        "penalty_applied": True,
        "penalty_multiplier": penalty_multiplier,
        "final_intent_score": final_score,
        "reason": f"Success Penalty: {int(age_months)} месяцев, успешная игра"
    }


def calculate_verdict(
    intent_score: int,
    behavioral_intent_score: int,
    freshness_gate: Dict[str, Any],
    success_penalty: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Вычисляет вердикт для игры на основе Intent Score и gates.
    
    Args:
        intent_score: Intent Score (после penalty)
        behavioral_intent_score: Behavioral Intent Score
        freshness_gate: Результат проверки Intent Freshness Gate
        success_penalty: Результат проверки Success Penalty Gate
        
    Returns:
        {
            "verdict_code": str,
            "verdict_label_ru": str
        }
    """
    final_intent_score = success_penalty.get("final_intent_score", intent_score)
    has_behavioral = behavioral_intent_score > 0
    has_freshness = freshness_gate.get("passes", False)
    has_success_penalty = success_penalty.get("penalty_applied", False)
    
    # Определяем вердикт по приоритету
    if has_success_penalty and final_intent_score < 10:
        verdict_code = "successful_not_target"
    elif final_intent_score >= VERDICTS["actively_seeking"]["min_intent_score"] and has_behavioral and has_freshness:
        verdict_code = "actively_seeking"
    elif final_intent_score >= VERDICTS["early_request"]["min_intent_score"] and has_freshness:
        verdict_code = "early_request"
    elif final_intent_score >= VERDICTS["possible_deal"]["min_intent_score"]:
        verdict_code = "possible_deal"
    elif has_success_penalty:
        verdict_code = "successful_not_target"
    else:
        verdict_code = "no_intent_signs"
    
    verdict_config = VERDICTS.get(verdict_code, VERDICTS["no_intent_signs"])
    
    return {
        "verdict_code": verdict_code,
        "verdict_label_ru": verdict_config["label_ru"]
    }


def analyze_deal_intent(
    app_data: Dict[str, Any],
    signals: List[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Полный анализ deal intent v3 для игры.
    
    Args:
        app_data: Данные игры
        signals: Внешние сигналы
        
    Returns:
        {
            "intent_score": int,
            "intent_reasons": List[str],
            "quality_score": int,
            "quality_reasons": List[str],
            "matched_signals": int,
            "behavioral_intent_score": int,
            "structural_intent_score": int,
            "temporal_boost_score": int,
            "freshness_gate": Dict,
            "success_penalty": Dict,
            "verdict": Dict
        }
    """
    signals = signals or []
    
    # Вычисляем Intent Score (3 слоя)
    intent_result = calculate_intent_score(app_data, signals)
    intent_score = intent_result["intent_score"]
    
    # Проверяем Intent Freshness Gate
    freshness_gate = check_intent_freshness_gate(app_data, signals)
    
    # Проверяем Success Penalty Gate
    success_penalty = check_success_penalty_gate(app_data, intent_score)
    
    # Вычисляем вердикт
    verdict = calculate_verdict(
        intent_score,
        intent_result.get("behavioral_intent_score", 0),
        freshness_gate,
        success_penalty
    )
    
    # Вычисляем Quality Score
    quality_result = calculate_quality_score(app_data)
    
    return {
        **intent_result,
        **quality_result,
        "freshness_gate": freshness_gate,
        "success_penalty": success_penalty,
        "verdict": verdict,
        "final_intent_score": success_penalty.get("final_intent_score", intent_score)
    }
