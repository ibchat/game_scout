"""
Deals / Publisher Intent API Router
Отдельный слой для определения намерений издателей.
Не зависит от TrendsBrain или Emerging engine.
"""
from typing import List, Dict, Any, Optional, Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, date, timedelta
import logging
import uuid
import math
import re

from apps.api.deps import get_db_session
from apps.worker.analysis.db_introspection import detect_steam_review_app_id_column
from apps.worker.analysis.deal_intent_scorer import (
    analyze_deal_intent,
    detect_intent_keywords,
    check_intent_freshness_gate,
    check_success_penalty_gate,
    calculate_verdict
)
from apps.worker.config.deal_intent_reasons_ru import translate_reasons_list, translate_reason_to_ru
from apps.worker.config.deal_intent_config import BEHAVIORAL_INTENT_SOURCES

logger = logging.getLogger(__name__)

# Константы типов издательского интереса (коды)
PUBLISHER_TYPE_SCOUT_FUND = "scout_fund"
PUBLISHER_TYPE_GENRE_PUBLISHER = "genre_publisher"
PUBLISHER_TYPE_MARKETING_PUBLISHER = "marketing_publisher"
PUBLISHER_TYPE_TURNAROUND_PUBLISHER = "turnaround_publisher"
PUBLISHER_TYPE_OPERATOR_PUBLISHER = "operator_publisher"
PUBLISHER_TYPE_INFLUENCER_PARTNER = "influencer_partner"

# Маппинг code → RU label (для API остаётся русский)
PUBLISHER_TYPE_LABEL_RU = {
    PUBLISHER_TYPE_SCOUT_FUND: "Скаут/фонд",
    PUBLISHER_TYPE_GENRE_PUBLISHER: "Паблишер по жанру",
    PUBLISHER_TYPE_MARKETING_PUBLISHER: "Маркетинговый издатель (performance / UA)",
    PUBLISHER_TYPE_TURNAROUND_PUBLISHER: "Паблишер \"спасатель\" (late-stage turnaround)",
    PUBLISHER_TYPE_OPERATOR_PUBLISHER: "Паблишер-оператор (live ops / контент)",
    PUBLISHER_TYPE_INFLUENCER_PARTNER: "Инфлюенсер/партнёр (дистрибуция)"
}


def map_publisher_status_label(status_code: str) -> str:
    """
    Возвращает человекочитаемый текст для publisher_status_code.
    """
    mapping = {
        "has_publisher": "Есть издатель",
        "self_published": "Самоиздание",
        "unknown": "Неизвестно"
    }
    return mapping.get(status_code, "Неизвестно")


def compute_publisher_status(publishers: Any) -> Literal["has_publisher", "self_published", "unknown"]:
    """
    Вычисляет publisher_status на основе steam_app_cache.publishers.
    Единственный источник истины для статуса издателя.
    
    Правила:
    - NULL → unknown (данные не загружены)
    - [] → self_published (явно без издателя)
    - [непустой массив] → has_publisher (есть издатель)
    """
    if publishers is None:
        return "unknown"
    
    # Если это JSONB массив или список Python
    if isinstance(publishers, list):
        if len(publishers) == 0:
            return "self_published"
        else:
            return "has_publisher"
    
    # Если это строка (JSON), пытаемся распарсить
    if isinstance(publishers, str):
        try:
            import json
            parsed = json.loads(publishers)
            if isinstance(parsed, list):
                if len(parsed) == 0:
                    return "self_published"
                else:
                    return "has_publisher"
        except:
            pass
    
    # По умолчанию unknown
    return "unknown"


def build_publisher_interest(
    archetype: str,
    app_data: Dict[str, Any],
    scores: Dict[str, Any],
    temporal_context: str
) -> Dict[str, Any]:
    """
    Формирует publisher_interest на основе архетипа.
    Чистая функция, не влияет на gates, scores, verdict.
    """
    intent_score = scores.get("intent_score", 0)
    quality_score = scores.get("quality_score", 0)
    stage = app_data.get("stage", "")
    publisher_status = app_data.get("publisher_status", "unknown")
    has_publisher = publisher_status == "has_publisher"
    
    who_might_care = []
    why_now = []
    risk_flags = []
    next_actions = []
    
    # Добавляем фразу о свежести сигналов, если applicable
    fresh_signal_note = ""
    if temporal_context == "recent_interest":
        fresh_signal_note = "Сигналы свежие — контактировать сейчас. "
    
    # C1: Если publisher_status == has_publisher → ОБЯЗАТЕЛЬНО добавить risk_flag
    if has_publisher:
        risk_flags.append("У игры уже есть издатель — запрос может означать co-pub, маркетинг, или рестарт релиза")
    
    if archetype == "early_publisher_search":
        # Формируем коды по правилам из TZ_BRAIN_EVOLUTION.md п.6.2
        who_might_care_codes = [
            PUBLISHER_TYPE_SCOUT_FUND,
            PUBLISHER_TYPE_GENRE_PUBLISHER,
            PUBLISHER_TYPE_MARKETING_PUBLISHER
        ]
        # Преобразуем коды в RU labels
        who_might_care = [PUBLISHER_TYPE_LABEL_RU[code] for code in who_might_care_codes]
        
        why_now = [
            fresh_signal_note + f"Команда ищет {'издательского партнёра / co-publishing / маркетингового партнёра' if has_publisher else 'партнёра'} до масштабирования — дешевле и быстрее договориться сейчас.",
            "Можно повлиять на позиционирование/маркетинг до выхода."
        ]
        
        if quality_score == 0:
            risk_flags.append("Нет подтверждения качества по метрикам — нужен быстрый аудит демо/вишлистов/конверсий.")
        
        next_actions = [
            "Запросить питч-дек + бюджет + план производства.",
            "Попросить билд/демо и список KPI (вишлисты, конверсия, удержание)."
        ]
    
    elif archetype == "late_pivot_after_release":
        # Формируем коды по правилам из TZ_BRAIN_EVOLUTION.md п.6.2
        who_might_care_codes = [
            PUBLISHER_TYPE_TURNAROUND_PUBLISHER,
            PUBLISHER_TYPE_MARKETING_PUBLISHER,
            PUBLISHER_TYPE_OPERATOR_PUBLISHER
        ]
        # Преобразуем коды в RU labels
        who_might_care = [PUBLISHER_TYPE_LABEL_RU[code] for code in who_might_care_codes]
        
        why_now = [
            fresh_signal_note + f"Есть свежий запрос на {'издательского партнёра / co-publishing / маркетингового партнёра / спасение релиза' if has_publisher else 'издателя'} после релиза — значит, команда готова к изменениям.",
            "Окно для перезапуска/скидок/ивентов сейчас самое короткое."
        ]
        
        risk_flags.append("После релиза сложнее менять продукт, нужен чёткий план перезапуска.")
        
        next_actions = [
            "Проверить причины слабых продаж: страница/трейлер/цена/теги/онбординг.",
            "Сделать план '90 дней': скидки + инфлюенсеры + обновления."
        ]
    
    elif archetype == "weak_signal_exploration":
        # Формируем коды по правилам из TZ_BRAIN_EVOLUTION.md п.6.2
        who_might_care_codes = [
            PUBLISHER_TYPE_SCOUT_FUND,
            PUBLISHER_TYPE_GENRE_PUBLISHER
        ]
        # Преобразуем коды в RU labels
        who_might_care = [PUBLISHER_TYPE_LABEL_RU[code] for code in who_might_care_codes]
        
        why_now = [
            "Сигналы устарели — интерес может быть неактуален; нужна перепроверка."
        ]
        
        risk_flags.append("Сигналы старые (>90 дней) — возможно, уже нашли партнёра или бросили проект.")
        
        next_actions = [
            "Перепроверить актуальность: сайт/соцсети/страница Steam, запросить статус."
        ]
    
    elif archetype == "opportunistic_outreach":
        # Формируем коды по правилам из TZ_BRAIN_EVOLUTION.md п.6.2
        who_might_care_codes = [
            PUBLISHER_TYPE_INFLUENCER_PARTNER,
            PUBLISHER_TYPE_MARKETING_PUBLISHER
        ]
        # Преобразуем коды в RU labels
        who_might_care = [PUBLISHER_TYPE_LABEL_RU[code] for code in who_might_care_codes]
        
        why_now = [
            fresh_signal_note + "Есть признаки интереса, но контекст размыт — можно дешево проверить контакт."
        ]
        
        risk_flags.append("Непонятна стадия/готовность/качество — риск пустой коммуникации.")
        
        next_actions = [
            "Сделать короткий outreach: 3 вопроса (статус, билд, KPI) + запрос материалов."
        ]
    
    elif archetype == "unclear_intent":
        # Формируем коды по правилам из TZ_BRAIN_EVOLUTION.md п.6.2
        # scout_fund только если intent_score > 0, иначе пусто
        who_might_care_codes = []
        if intent_score > 0:
            who_might_care_codes = [PUBLISHER_TYPE_SCOUT_FUND]
        # Преобразуем коды в RU labels
        who_might_care = [PUBLISHER_TYPE_LABEL_RU[code] for code in who_might_care_codes]
        
        why_now = [
            "Данных недостаточно для интерпретации намерения."
        ]
        
        risk_flags.append("Нет сигналов или дат — нельзя делать выводы.")
        
        next_actions = [
            "Сначала собрать внешние сигналы / обновить источники."
        ]
    
    elif archetype == "high_intent_low_quality":
        # Формируем коды по правилам из TZ_BRAIN_EVOLUTION.md п.6.2
        who_might_care_codes = [
            PUBLISHER_TYPE_MARKETING_PUBLISHER,
            PUBLISHER_TYPE_INFLUENCER_PARTNER
        ]
        # Преобразуем коды в RU labels
        who_might_care = [PUBLISHER_TYPE_LABEL_RU[code] for code in who_might_care_codes]
        
        why_now = [
            fresh_signal_note + f"Команда явно ищет {'издательского партнёра / co-publishing / маркетингового партнёра' if has_publisher else 'издателя'}, но качество не подтверждено метриками — подходит под быстрый тест."
        ]
        
        risk_flags.append("Высокий риск: качество/потенциал не доказаны.")
        
        next_actions = [
            "Только быстрый скрининг (15–30 минут): страница Steam, трейлер, демо, первые отзывы/метрики."
        ]
    
    else:
        # Fallback для неизвестных архетипов
        who_might_care = []
        why_now = ["Архетип не определён."]
        risk_flags = []
        next_actions = []
    
    # Формируем who_might_care_codes для фильтрации (Vector #3)
    who_might_care_codes = []
    if archetype == "early_publisher_search":
        who_might_care_codes = [
            PUBLISHER_TYPE_SCOUT_FUND,
            PUBLISHER_TYPE_GENRE_PUBLISHER,
            PUBLISHER_TYPE_MARKETING_PUBLISHER
        ]
    elif archetype == "late_pivot_after_release":
        who_might_care_codes = [
            PUBLISHER_TYPE_TURNAROUND_PUBLISHER,
            PUBLISHER_TYPE_MARKETING_PUBLISHER,
            PUBLISHER_TYPE_OPERATOR_PUBLISHER
        ]
    elif archetype == "weak_signal_exploration":
        who_might_care_codes = [
            PUBLISHER_TYPE_SCOUT_FUND,
            PUBLISHER_TYPE_GENRE_PUBLISHER
        ]
    elif archetype == "opportunistic_outreach":
        who_might_care_codes = [
            PUBLISHER_TYPE_INFLUENCER_PARTNER,
            PUBLISHER_TYPE_MARKETING_PUBLISHER
        ]
    elif archetype == "unclear_intent":
        if intent_score > 0:
            who_might_care_codes = [PUBLISHER_TYPE_SCOUT_FUND]
    elif archetype == "high_intent_low_quality":
        who_might_care_codes = [
            PUBLISHER_TYPE_MARKETING_PUBLISHER,
            PUBLISHER_TYPE_INFLUENCER_PARTNER
        ]
    
    return {
        "who_might_care": who_might_care,
        "who_might_care_codes": who_might_care_codes,  # Vector #3
        "why_now": why_now,
        "risk_flags": risk_flags,
        "next_actions": next_actions
    }


def build_thesis_explain(
    thesis_data: Dict[str, Any],
    publisher_interest: Dict[str, Any],
    publisher_status_code: str,
    signals: List[Dict[str, Any]],
    app_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Формирует thesis_explain — структурированный блок объяснения для UI.
    Vector #1: Explainability UI.
    """
    # headline = thesis.thesis
    headline = thesis_data.get("thesis", "Недостаточно данных")
    
    # why = комбинация supporting_facts + 1 фраза из publisher_interest.why_now (не более 6)
    why = []
    supporting_facts = thesis_data.get("supporting_facts", [])
    why.extend(supporting_facts[:5])  # Максимум 5 из supporting_facts
    
    why_now_list = publisher_interest.get("why_now", [])
    if why_now_list and len(why) < 6:
        why.append(why_now_list[0])  # Первая фраза из why_now
    
    # signals = последние 1–3 сигнала (по свежести, days_ago asc)
    signals_list = []
    # Вычисляем days_ago для каждого сигнала
    signals_with_days = []
    for sig in signals:
        published_at = sig.get("published_at") or sig.get("created_at")
        if published_at:
            if isinstance(published_at, datetime):
                delta = (datetime.now(published_at.tzinfo) if published_at.tzinfo else datetime.utcnow()) - published_at
            elif isinstance(published_at, str):
                try:
                    pub_dt = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                    delta = datetime.now(pub_dt.tzinfo) - pub_dt if pub_dt.tzinfo else datetime.utcnow() - pub_dt
                except:
                    delta = None
            else:
                delta = None
            
            days_ago = int(delta.total_seconds() / 86400) if delta else None
        else:
            days_ago = None
        
        signals_with_days.append((sig, days_ago))
    
    # Сортируем по days_ago (asc, свежие первыми), затем берем первые 3
    sorted_signals = sorted(
        signals_with_days,
        key=lambda x: (x[1] if x[1] is not None else 999999, x[0].get("published_at") or x[0].get("created_at") or datetime.min)
    )[:3]
    
    for sig, days_ago in sorted_signals:
        signal_text = sig.get("text", "") or ""
        # Очищаем от [SYNTHETIC] и обрезаем до 140 символов
        snippet = signal_text.replace("[SYNTHETIC]", "").strip()
        if len(snippet) > 140:
            snippet = snippet[:137] + "..."
        
        signals_list.append({
            "source": sig.get("source", "unknown"),
            "type": sig.get("signal_type", "unknown"),
            "days_ago": days_ago,
            "snippet": snippet
        })
    
    # publisher_context
    publisher_context = {
        "publisher_status_code": publisher_status_code,
        "publisher_status_ru": map_publisher_status_label(publisher_status_code),
        "note": ""
    }
    if publisher_status_code == "has_publisher":
        publisher_context["note"] = "У игры уже есть издатель: запрос может означать co-publishing, маркетинг или спасение релиза."
    elif publisher_status_code == "self_published":
        publisher_context["note"] = "Издателя на Steam нет: запрос трактуем как классический поиск издателя."
    else:  # unknown
        publisher_context["note"] = "По Steam нет надёжного сигнала об издателе: трактуем осторожно."
    
    # confidence_breakdown (из внутреннего поля)
    confidence_breakdown = thesis_data.get("_confidence_breakdown", [])
    
    # next_step зависит от temporal_context
    temporal_context = thesis_data.get("temporal_context", "unknown")
    if temporal_context == "recent_interest":
        next_step = "Контактировать сейчас, пока сигнал свежий. Запросить питчдек и демо."
    else:
        next_step = "Собрать больше подтверждений (вишлисты/конверсии/демо), затем контакт."
    
    return {
        "headline": headline,
        "why": why,
        "signals": signals_list,
        "publisher_context": publisher_context,
        "confidence_breakdown": confidence_breakdown,
        "next_step": next_step
    }


def build_deal_thesis(
    app_data: Dict[str, Any],
    signals: List[Dict[str, Any]],
    scores: Dict[str, Any],
    gates: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Формирует DealThesis — объяснение, почему объект интересен или неинтересен сейчас.
    Чистая функция, не влияет на gates, scores, verdict.
    """
    # Единые пороги для архетипизации
    FRESH_DAYS = 60
    WEAK_DAYS = 90
    
    supporting_facts = []
    counter_facts = []
    thesis = ""
    temporal_context = ""
    
    # Анализируем behavioral_intent сигналы
    behavioral_signals = []
    for signal in signals:
        signal_text = signal.get("text", "") or ""
        if signal_text:
            detected = detect_intent_keywords(signal_text)
            if detected:
                signal_date = signal.get("published_at") or signal.get("created_at")
                days_ago = None
                if signal_date:
                    try:
                        if isinstance(signal_date, str):
                            signal_date = datetime.fromisoformat(signal_date.replace('Z', '+00:00'))
                        if isinstance(signal_date, datetime):
                            days_ago = (datetime.utcnow() - signal_date.replace(tzinfo=None)).days
                    except:
                        pass
                
                if days_ago is not None:
                    behavioral_signals.append({
                        "days_ago": days_ago,
                        "source": signal.get("source", "unknown"),
                        "text": signal_text[:100]
                    })
    
    # Определяем temporal_context
    stage = app_data.get("stage", "")
    release_date = app_data.get("release_date")
    is_released = stage == "released"
    publisher_status = app_data.get("publisher_status", "unknown")  # Получаем publisher_status из app_data
    
    if behavioral_signals:
        valid_signals = [s for s in behavioral_signals if s.get("days_ago") is not None]
        if valid_signals:
            latest_signal_days = min(s["days_ago"] for s in valid_signals)
            if latest_signal_days is not None:
                if latest_signal_days <= FRESH_DAYS:
                    temporal_context = "recent_interest"
                elif latest_signal_days <= 180:
                    temporal_context = "cooling_down"
                else:
                    temporal_context = "stale"
            else:
                temporal_context = "unknown"
        else:
            temporal_context = "unknown"
    else:
        if is_released:
            temporal_context = "post_release"
        else:
            temporal_context = "pre_release_window"
    
    # Формируем thesis на основе правил с учетом publisher_status
    # Если publisher_status == has_publisher И есть behavioral_intent → трактовать как "ищут партнёра/маркетинг"
    has_publisher = publisher_status == "has_publisher"
    intent_verb = "ищет издательского партнёра" if has_publisher else "ищет издателя"
    
    if behavioral_signals:
        # Фильтруем только сигналы с валидным days_ago
        valid_signals = [s for s in behavioral_signals if s.get("days_ago") is not None]
        if valid_signals:
            latest_days = min(s["days_ago"] for s in valid_signals)
            if latest_days is not None:
                if latest_days < 14:
                    thesis = f"Активный поиск {'партнёра' if has_publisher else 'издателя'}"
                    supporting_facts.append(f"Свежие сигналы поиска {'партнёра' if has_publisher else 'издателя'} ({latest_days} дней назад)")
                elif latest_days <= FRESH_DAYS:
                    thesis = f"Недавнее намерение найти {'партнёра' if has_publisher else 'издателя'}"
                    supporting_facts.append(f"Сигналы поиска {'партнёра' if has_publisher else 'издателя'} ({latest_days} дней назад)")
                elif latest_days > WEAK_DAYS:
                    thesis = "Устаревшее намерение, слабое продолжение"
                    counter_facts.append(f"Последний сигнал был {latest_days} дней назад")
        else:
            thesis = f"Есть сигналы поиска {'партнёра' if has_publisher else 'издателя'}, но даты не определены"
            supporting_facts.append("Обнаружены behavioral intent сигналы")
    else:
        thesis = f"Нет явных признаков активного поиска {'партнёра' if has_publisher else 'издателя'}"
        counter_facts.append("Отсутствуют behavioral intent сигналы")
    
    # Дополнительные факты на основе stage и intent
    if behavioral_signals:
        valid_signals = [s for s in behavioral_signals if s.get("days_ago") is not None]
        if valid_signals:
            latest_days = min(s["days_ago"] for s in valid_signals)
            if latest_days is not None and is_released and latest_days <= FRESH_DAYS:
                thesis = f"Поздний поворот: {intent_verb} после релиза"
                supporting_facts.append(f"Игра уже выпущена, но есть свежие сигналы поиска {'партнёра' if has_publisher else 'издателя'}")
    
    if stage in ["demo", "coming_soon"] and behavioral_signals:
        thesis = f"Ранний поиск {'партнёра' if has_publisher else 'издателя'}, хорошее соответствие"
        supporting_facts.append(f"Стадия {stage} с признаками поиска {'партнёра' if has_publisher else 'издателя'}")
    
    # Добавляем факты на основе scores и gates
    intent_score = scores.get("intent_score", 0)
    quality_score = scores.get("quality_score", 0)
    
    if intent_score > 0:
        supporting_facts.append(f"Intent score: {intent_score}")
    else:
        counter_facts.append("Intent score равен нулю")
    
    if quality_score > 0:
        supporting_facts.append(f"Quality score: {quality_score}")
    else:
        counter_facts.append("Quality score равен нулю")
    
    # Проверяем gates
    freshness_gate = gates.get("freshness_gate", {})
    if not freshness_gate.get("passes", False):
        counter_facts.append(f"Freshness gate не пройден: {freshness_gate.get('reason', 'неизвестно')}")
    
    success_penalty = gates.get("success_penalty", {})
    if success_penalty.get("penalty_applied", False):
        counter_facts.append("Применён success penalty (игра уже успешна)")
    
    # Вычисляем confidence по детерминированной формуле из TZ_BRAIN_EVOLUTION.md (п.7.1)
    # Vector #1: Сохраняем breakdown для thesis_explain
    confidence_breakdown = []
    
    confidence = 0.0  # Начальное значение base
    
    # Определяем latest_days для behavioral_intent
    latest_days = None
    valid_signals = [s for s in behavioral_signals if s.get("days_ago") is not None]
    if valid_signals:
        latest_days = min(s["days_ago"] for s in valid_signals)
    
    # 1. +0.3 если есть свежие behavioral_intent и latest_days <= FRESH_DAYS
    fresh_behavioral_applied = latest_days is not None and latest_days <= FRESH_DAYS
    if fresh_behavioral_applied:
        confidence += 0.3
    confidence_breakdown.append({
        "rule": "+0.3 свежий behavioral_intent ≤ 60 дней",
        "applied": fresh_behavioral_applied,
        "delta": 0.3 if fresh_behavioral_applied else 0.0
    })
    
    # 2. +0.2 если stage согласуется с архетипом (проверим после определения архетипа)
    # Временно добавляем placeholder
    confidence_breakdown.append({
        "rule": "+0.2 stage согласуется с archetype",
        "applied": False,  # Обновим после определения архетипа
        "delta": 0.0
    })
    
    # 3. +0.1 если intent_score > 0
    intent_positive_applied = intent_score > 0
    if intent_positive_applied:
        confidence += 0.1
    confidence_breakdown.append({
        "rule": "+0.1 intent_score > 0",
        "applied": intent_positive_applied,
        "delta": 0.1 if intent_positive_applied else 0.0
    })
    
    # 4. -0.2 если quality_score == 0
    quality_zero_applied = quality_score == 0
    if quality_zero_applied:
        confidence -= 0.2
    confidence_breakdown.append({
        "rule": "-0.2 quality_score == 0",
        "applied": quality_zero_applied,
        "delta": -0.2 if quality_zero_applied else 0.0
    })
    
    # 5. -0.2 если сигналы старше WEAK_DAYS
    stale_signals_applied = latest_days is not None and latest_days > WEAK_DAYS
    if stale_signals_applied:
        confidence -= 0.2
    confidence_breakdown.append({
        "rule": "-0.2 latest_days > 90",
        "applied": stale_signals_applied,
        "delta": -0.2 if stale_signals_applied else 0.0
    })
    
    # Определяем thesis_archetype на основе имеющихся данных (жёсткий приоритет правил)
    thesis_archetype = None  # Сначала не определён
    
    intent_score = scores.get("intent_score", 0)
    quality_score = scores.get("quality_score", 0)
    
    # Правило 1: late_pivot_after_release
    if behavioral_signals:
        valid_signals = [s for s in behavioral_signals if s.get("days_ago") is not None]
        if valid_signals:
            latest_days = min(s["days_ago"] for s in valid_signals)
            if latest_days is not None:
                if is_released and latest_days <= FRESH_DAYS:
                    thesis_archetype = "late_pivot_after_release"
    
    # Правило 2: early_publisher_search
    if thesis_archetype is None and behavioral_signals:
        valid_signals = [s for s in behavioral_signals if s.get("days_ago") is not None]
        if valid_signals:
            latest_days = min(s["days_ago"] for s in valid_signals)
            if latest_days is not None:
                if stage in ["demo", "coming_soon", "early_access"] and latest_days <= FRESH_DAYS:
                    thesis_archetype = "early_publisher_search"
    
    # Правило 3: weak_signal_exploration
    if thesis_archetype is None and behavioral_signals:
        valid_signals = [s for s in behavioral_signals if s.get("days_ago") is not None]
        if valid_signals:
            latest_days = min(s["days_ago"] for s in valid_signals)
            if latest_days is not None and latest_days > WEAK_DAYS:
                thesis_archetype = "weak_signal_exploration"
    
    # Правило 4: opportunistic_outreach
    if thesis_archetype is None and behavioral_signals:
        valid_signals = [s for s in behavioral_signals if s.get("days_ago") is not None]
        if valid_signals:
            # Есть сигналы, но не попали в правила 1-3
            thesis_archetype = "opportunistic_outreach"
    
    # Правило 5: unclear_intent
    if thesis_archetype is None:
        thesis_archetype = "unclear_intent"
    
    # Правило 6: high_intent_low_quality (ТОЛЬКО fallback)
    if thesis_archetype in ["unclear_intent", "weak_signal_exploration"]:
        if intent_score > 0 and quality_score == 0:
            thesis_archetype = "high_intent_low_quality"
    
    # 2. +0.2 если stage согласуется с архетипом (продолжение формулы confidence)
    stage_match_applied = False
    if thesis_archetype == "early_publisher_search" and stage in ["demo", "coming_soon"]:
        confidence += 0.2
        stage_match_applied = True
    elif thesis_archetype == "late_pivot_after_release" and stage == "released":
        confidence += 0.2
        stage_match_applied = True
    
    # Обновляем breakdown для stage match
    confidence_breakdown[1] = {
        "rule": "+0.2 stage согласуется с archetype",
        "applied": stage_match_applied,
        "delta": 0.2 if stage_match_applied else 0.0
    }
    
    # Финал: clamp(base, 0.0, 1.0)
    confidence = max(0.0, min(1.0, confidence))
    
    # Формируем publisher_interest на основе архетипа
    publisher_interest = build_publisher_interest(
        archetype=thesis_archetype,
        app_data=app_data,
        scores=scores,
        temporal_context=temporal_context
    )
    
    return {
        "thesis": thesis or "Недостаточно данных для формулировки тезиса",
        "supporting_facts": supporting_facts,
        "counter_facts": counter_facts,
        "temporal_context": temporal_context,
        "confidence": round(confidence, 2),
        "thesis_archetype": thesis_archetype,
        "publisher_interest": publisher_interest,
        "_confidence_breakdown": confidence_breakdown  # Внутреннее поле для build_thesis_explain
    }

router = APIRouter(prefix="/deals", tags=["Deals / Publisher Intent"])


def _extract_value_from_reason(reason: str, row: Dict[str, Any]) -> str:
    """Извлекает значение из reason для отображения в breakdown"""
    if "reviews_30d" in reason:
        count = row.get("recent_reviews_count_30d", 0)
        return f"{count} отзывов"
    elif "positive_ratio" in reason:
        pct = row.get("all_positive_percent", 0)
        return f"{pct}%"
    elif "stage" in reason:
        return row.get("stage", "unknown")
    elif "publisher" in reason:
        return row.get("publisher_name", "не указан")
    elif "has_demo" in reason:
        return "Да" if row.get("has_demo") else "Нет"
    elif "website" in reason or "discord" in reason:
        return "Есть"
    else:
        return "—"


# ============================================================================
# Request/Response Models
# ============================================================================

class SignalImportRequest(BaseModel):
    url: str = Field(..., description="URL источника сигнала")
    source: str = Field(..., description="Источник: twitter, linkedin, steam, etc")
    app_id: Optional[int] = Field(None, description="Steam app_id (опционально)")
    text: Optional[str] = Field(None, description="Текст сигнала (если не указан, будет извлечён из URL)")


class DiscordImportRequest(BaseModel):
    raw_text: str = Field(..., description="Текст из Discord (копипаст)")
    ts: Optional[str] = Field(None, description="ISO timestamp сообщения (опционально)")
    url: Optional[str] = Field(None, description="URL сообщения (опционально)")
    server: Optional[str] = Field(None, description="Название сервера (опционально)")
    channel: Optional[str] = Field(None, description="Название канала (опционально)")


class ActionRequest(BaseModel):
    action_type: str = Field(..., description="Тип действия: request_pitch_deck, request_steamworks, send_offer, book_call, watchlist")
    payload: Optional[Dict[str, Any]] = Field(None, description="Дополнительные данные")


# ============================================================================
# Endpoints
# ============================================================================
# ВАЖНО: Специфичные пути ДО параметризованных ({app_id})
# Порядок: /list, /diagnostics, /bootstrap, /signals/import, /{app_id}, /{app_id}/action

@router.get("/list")
async def get_deals_list(
    limit: int = Query(50, ge=1, le=200),
    min_intent_score: int = Query(0, ge=0, le=100),
    min_quality_score: int = Query(0, ge=0, le=100),
    stage: Optional[str] = Query(None, description="Фильтр по stage"),
    synthetic_only: bool = Query(False, description="Только игры с синтетическими сигналами"),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Список игр с deal intent.
    """
    try:
        # Explore Mode: при нулевых порогах отключаем строгие гейты
        explore_mode = (min_intent_score == 0 and min_quality_score == 0)
        logger.info(f"Deals list: explore_mode={explore_mode}, min_intent={min_intent_score}, min_quality={min_quality_score}")
        # Определяем реальное имя колонки app_id в steam_review_daily (один раз)
        app_id_col = detect_steam_review_app_id_column(db)
        logger.info(f"Using app_id column in steam_review_daily: {app_id_col}")
        
        # Фильтр по синтетическим сигналам (если synthetic_only=true)
        synthetic_filter = ""
        if synthetic_only:
            synthetic_filter = """
              AND EXISTS (
                SELECT 1 FROM deal_intent_signal s
                WHERE s.app_id = d.app_id
                  AND (
                    s.text ILIKE '[SYNTHETIC]%%'
                    OR s.url ILIKE '%%synthetic_%%'
                  )
              )
            """
        
        # SQL запрос для получения данных (БЕЗ фильтров по score для подсчёта total)
        # ВАЖНО: JOIN с steam_app_cache и games для получения реальных названий игр
        query = text(f"""
            SELECT 
                d.app_id,
                COALESCE(NULLIF(c.name, ''), g.title) as title,
                COALESCE(NULLIF(c.steam_url, ''), d.steam_url, 'https://store.steampowered.com/app/' || d.app_id::text || '/') as steam_url,
                d.developer_name,
                d.publisher_name,
                c.publishers AS publishers,
                COALESCE(c.release_date, d.release_date) as release_date,
                d.stage,
                d.has_demo,
                d.price_eur,
                d.intent_score,
                d.quality_score,
                d.intent_reasons,
                d.quality_reasons,
                d.updated_at,
                srd.recent_reviews_count_30d,
                srd.all_positive_percent,
                srd.all_reviews_count
            FROM deal_intent_game d
            LEFT JOIN steam_app_cache c ON c.steam_app_id = d.app_id::bigint
            LEFT JOIN games g ON g.source = 'steam' AND g.source_id = d.app_id::text
            LEFT JOIN steam_review_daily srd ON srd.{app_id_col} = d.app_id::bigint
                AND srd.day = (
                    SELECT MAX(day) FROM steam_review_daily WHERE {app_id_col} = d.app_id::bigint
                )
            WHERE 1=1
              -- Фильтр по ТЗ: название ОБЯЗАТЕЛЬНО
              AND (c.name IS NOT NULL AND c.name != '' OR g.title IS NOT NULL AND g.title != '')
              -- Фильтр по ТЗ: release_date IS NULL → исключить
              AND COALESCE(c.release_date, d.release_date) IS NOT NULL
              -- Фильтр по ТЗ: release_date >= current_date - 4 years
              AND COALESCE(c.release_date, d.release_date) >= CURRENT_DATE - INTERVAL '4 years'
              -- Фильтр по ТЗ: разрешённые стадии
              AND d.stage IN ('coming_soon', 'demo', 'early_access', 'released')
        """)
        
        # Подсчитываем total до фильтрации (в Explore Mode используем только базовую санитарию)
        total_base_where = """
            WHERE 1=1
              -- Базовая санитария: название ОБЯЗАТЕЛЬНО
              AND (c.name IS NOT NULL AND c.name != '' OR g.title IS NOT NULL AND g.title != '')
        """
        
        total_strict_filters = ""
        if not explore_mode:
            total_strict_filters = """
              -- Фильтр по ТЗ: release_date IS NULL → исключить
              AND COALESCE(c.release_date, d.release_date) IS NOT NULL
              -- Фильтр по ТЗ: release_date >= current_date - 4 years
              AND COALESCE(c.release_date, d.release_date) >= CURRENT_DATE - INTERVAL '4 years'
            """
        
        total_common = """
              -- Фильтр по ТЗ: разрешённые стадии
              AND d.stage IN ('coming_soon', 'demo', 'early_access', 'released')
        """
        
        total_query = text(f"""
            SELECT COUNT(*) as cnt
            FROM deal_intent_game d
            LEFT JOIN steam_app_cache c ON c.steam_app_id = d.app_id::bigint
            LEFT JOIN games g ON g.source = 'steam' AND g.source_id = d.app_id::text
            {total_base_where}
            {total_strict_filters}
            {total_common}
            {f"AND d.stage = :stage" if stage else ""}
            {synthetic_filter}
        """)
        total_params = {}
        if stage:
            total_params["stage"] = stage
        total_rows = db.execute(total_query, total_params).scalar() or 0
        
        logger.info("Deals before filters: total_rows=%s", total_rows)
        
        # Логируем статистику исключений по ТЗ
        excluded_no_name_query = text(f"""
            SELECT COUNT(*) as cnt
            FROM deal_intent_game d
            LEFT JOIN steam_app_cache c ON c.steam_app_id = d.app_id::bigint
            LEFT JOIN games g ON g.source = 'steam' AND g.source_id = d.app_id::text
            WHERE (c.name IS NULL OR c.name = '') AND (g.title IS NULL OR g.title = '')
        """)
        excluded_no_name = db.execute(excluded_no_name_query).scalar() or 0
        
        excluded_no_release_query = text(f"""
            SELECT COUNT(*) as cnt
            FROM deal_intent_game d
            LEFT JOIN steam_app_cache c ON c.steam_app_id = d.app_id::bigint
            WHERE COALESCE(c.release_date, d.release_date) IS NULL
        """)
        excluded_no_release = db.execute(excluded_no_release_query).scalar() or 0
        
        excluded_old_query = text(f"""
            SELECT COUNT(*) as cnt
            FROM deal_intent_game d
            LEFT JOIN steam_app_cache c ON c.steam_app_id = d.app_id::bigint
            WHERE COALESCE(c.release_date, d.release_date) IS NOT NULL
              AND COALESCE(c.release_date, d.release_date) < CURRENT_DATE - INTERVAL '4 years'
        """)
        excluded_old = db.execute(excluded_old_query).scalar() or 0
        
        logger.info("Deals filters (TZ): excluded_no_name=%s excluded_no_release=%s excluded_old=%s", 
                   excluded_no_name, excluded_no_release, excluded_old)
        
        # Применяем фильтры согласно ТЗ
        # Explore Mode: при нулевых порогах отключаем строгие гейты, оставляем только базовую санитарию
        # ВАЖНО: используем реальное имя колонки app_id_col (определено выше)
        
        # Базовые фильтры (применяются всегда)
        base_where = """
            WHERE d.intent_score >= :min_intent_score
              AND d.quality_score >= :min_quality_score
              -- Базовая санитария: название ОБЯЗАТЕЛЬНО
              AND (c.name IS NOT NULL AND c.name != '' OR g.title IS NOT NULL AND g.title != '')
        """
        
        # Строгие гейты (отключаются в Explore Mode)
        strict_gates = ""
        if not explore_mode:
            strict_gates = """
              -- Gate v2.0: Валидность - release_date не NULL
              AND COALESCE(c.release_date, d.release_date) IS NOT NULL
              -- Gate v2.0: Новизна (одно из условий)
              AND (
                -- Вариант A: свежий релиз (<= 12 месяцев)
                COALESCE(c.release_date, d.release_date) >= CURRENT_DATE - INTERVAL '12 months'
                OR
                -- Вариант B: ранняя стадия
                d.stage IN ('coming_soon', 'demo', 'early_access')
                OR
                -- Вариант C: новая страница (если есть first_seen_at в seed)
                EXISTS (
                  SELECT 1
                  FROM trends_seed_apps tsa 
                  WHERE tsa.steam_app_id = d.app_id
                    AND tsa.created_at >= CURRENT_DATE - INTERVAL '90 days'
                    AND tsa.is_active = true
                )
              )
              -- Gate v2.0: Анти-успех фильтр (отсечение "им не нужен издатель")
              AND NOT (
                -- Уже успешные игры исключаем (NULL-safe)
                (COALESCE(srd.all_reviews_count, 0) >= 2000)
                OR
                (COALESCE(srd.recent_reviews_count_30d, 0) >= 200)
                OR
                ((COALESCE(srd.all_positive_percent, 0) >= 90) AND (COALESCE(srd.all_reviews_count, 0) >= 1000))
              )
              -- Data Quality Gate: intent_score > 0 OR quality_score > 0
              AND (d.intent_score > 0 OR d.quality_score > 0)
            """
        
        # Общие фильтры (применяются всегда)
        common_filters = """
              -- Фильтр по ТЗ: разрешённые стадии
              AND d.stage IN ('coming_soon', 'demo', 'early_access', 'released')
        """
        
        query = text(f"""
            SELECT 
                d.app_id,
                COALESCE(NULLIF(c.name, ''), g.title) as title,
                COALESCE(NULLIF(c.steam_url, ''), d.steam_url, 'https://store.steampowered.com/app/' || d.app_id::text || '/') as steam_url,
                d.developer_name,
                d.publisher_name,
                c.publishers as publishers,
                COALESCE(c.release_date, d.release_date) as release_date,
                d.stage,
                d.has_demo,
                d.price_eur,
                d.intent_score,
                d.quality_score,
                d.intent_reasons,
                d.quality_reasons,
                d.updated_at,
                srd.recent_reviews_count_30d,
                srd.all_positive_percent,
                srd.all_reviews_count
            FROM deal_intent_game d
            LEFT JOIN steam_app_cache c ON c.steam_app_id = d.app_id::bigint
            LEFT JOIN games g ON g.source = 'steam' AND g.source_id = d.app_id::text
            LEFT JOIN steam_review_daily srd ON srd.{app_id_col} = d.app_id::bigint
                AND srd.day = (
                    SELECT MAX(day) FROM steam_review_daily WHERE {app_id_col} = d.app_id::bigint
                )
            {base_where}
            {strict_gates}
            {common_filters}
            {f"AND d.stage = :stage" if stage else ""}
            {synthetic_filter}
            ORDER BY d.intent_score DESC, d.quality_score DESC
            LIMIT :limit
        """)
        
        params = {
            "min_intent_score": min_intent_score,
            "min_quality_score": min_quality_score,
            "limit": limit
        }
        if stage:
            params["stage"] = stage
        
        rows = db.execute(query, params).mappings().all()
        sql_rows = len(rows)
        logger.info(f"Deals list: sql_rows={sql_rows} (after SQL filters, explore_mode={explore_mode})")
        
        # Получаем все сигналы для игр одним запросом (v3: для Intent Freshness Gate)
        app_ids = [row["app_id"] for row in rows]
        signals_by_app = {}
        if app_ids:
            signals_query = text("""
                SELECT app_id, source, url, text, signal_type, confidence, published_at, created_at
                FROM deal_intent_signal
                WHERE app_id = ANY(:app_ids)
                ORDER BY app_id, created_at DESC
            """)
            signals_rows = db.execute(signals_query, {"app_ids": app_ids}).mappings().all()
            for signal_row in signals_rows:
                app_id = signal_row["app_id"]
                if app_id not in signals_by_app:
                    signals_by_app[app_id] = []
                signals_by_app[app_id].append({
                    "source": signal_row["source"],
                    "url": signal_row["url"],
                    "text": signal_row["text"],
                    "signal_type": signal_row["signal_type"],
                    "confidence": float(signal_row["confidence"]) if signal_row["confidence"] else 0.0,
                    "published_at": signal_row["published_at"],
                    "created_at": signal_row["created_at"]
                })
        
        games = []
        excluded_count = 0
        excluded_reasons = {}
        
        # Диагностика: счетчики для каждого типа фильтра
        diagnostic = {
            "sql_rows": sql_rows,
            "after_python_filters": 0,
            "excluded_reasons": {}
        }
        
        for row in rows:
            title = row.get("title")
            release_date = row.get("release_date")
            
            # Базовая санитария: название ОБЯЗАТЕЛЬНО (применяется всегда)
            if not title or title.strip() == "":
                excluded_count += 1
                excluded_reasons["no_name"] = excluded_reasons.get("no_name", 0) + 1
                diagnostic["excluded_reasons"]["no_name"] = diagnostic["excluded_reasons"].get("no_name", 0) + 1
                logger.warning(f"Excluded app_id {row['app_id']}: no name (steam_app_cache.name and games.name both empty)")
                continue
            
            # Проверка release_date (отключается в Explore Mode)
            release_date_obj = None
            if not explore_mode:
                # Проверка по ТЗ: release_date ОБЯЗАТЕЛЬНО
                if not release_date:
                    excluded_count += 1
                    excluded_reasons["no_release_date"] = excluded_reasons.get("no_release_date", 0) + 1
                    diagnostic["excluded_reasons"]["no_release_date"] = diagnostic["excluded_reasons"].get("no_release_date", 0) + 1
                    logger.warning(f"Excluded app_id {row['app_id']}: release_date IS NULL")
                    continue
                
                # Проверка по ТЗ: release_date >= current_date - 4 years
                try:
                    if isinstance(release_date, str):
                        release_date_obj = datetime.fromisoformat(release_date.replace('Z', '+00:00')).date()
                    elif hasattr(release_date, 'date'):
                        release_date_obj = release_date.date() if hasattr(release_date, 'date') else release_date
                    else:
                        release_date_obj = release_date
                    
                    four_years_ago = date.today() - timedelta(days=365 * 4)
                    if release_date_obj < four_years_ago:
                        excluded_count += 1
                        excluded_reasons["too_old"] = excluded_reasons.get("too_old", 0) + 1
                        diagnostic["excluded_reasons"]["too_old"] = diagnostic["excluded_reasons"].get("too_old", 0) + 1
                        logger.warning(f"Excluded app_id {row['app_id']}: release_date {release_date_obj} is older than 4 years")
                        continue
                except Exception as e:
                    logger.error(f"Failed to parse release_date for app_id {row['app_id']}: {e}")
                    excluded_count += 1
                    excluded_reasons["invalid_release_date"] = excluded_reasons.get("invalid_release_date", 0) + 1
                    diagnostic["excluded_reasons"]["invalid_release_date"] = diagnostic["excluded_reasons"].get("invalid_release_date", 0) + 1
                    continue
            else:
                # В Explore Mode парсим release_date без строгих проверок
                try:
                    if release_date:
                        if isinstance(release_date, str):
                            release_date_obj = datetime.fromisoformat(release_date.replace('Z', '+00:00')).date()
                        elif hasattr(release_date, 'date'):
                            release_date_obj = release_date.date() if hasattr(release_date, 'date') else release_date
                        else:
                            release_date_obj = release_date
                except:
                    release_date_obj = None
            
            # Data Quality Gate: intent_score > 0 OR quality_score > 0 (отключается в Explore Mode)
            intent_score = row.get("intent_score") or 0
            quality_score = row.get("quality_score") or 0
            if not explore_mode and intent_score <= 0 and quality_score <= 0:
                excluded_count += 1
                excluded_reasons["zero_scores"] = excluded_reasons.get("zero_scores", 0) + 1
                diagnostic["excluded_reasons"]["zero_scores"] = diagnostic["excluded_reasons"].get("zero_scores", 0) + 1
                logger.debug(f"Excluded app_id {row['app_id']}: both intent_score and quality_score are 0")
                continue
            
            # v3.1: Intent Freshness Gate - проверяем свежесть намерения (отключается в Explore Mode)
            app_id = row["app_id"]
            signals = signals_by_app.get(app_id, [])
            
            # Подготавливаем app_data для gates
            app_data = {
                "app_id": app_id,
                "publisher_name": row.get("publisher_name"),
                "developer_name": row.get("developer_name"),
                "stage": row.get("stage"),
                "release_date": release_date_obj,
                "has_demo": row.get("has_demo", False),
                "price_eur": float(row["price_eur"]) if row["price_eur"] else None,
                "all_reviews_count": row.get("all_reviews_count", 0),
                "recent_reviews_count_30d": row.get("recent_reviews_count_30d", 0),
                "all_positive_percent": row.get("all_positive_percent", 0),
                "steam_page_created_at": None,  # TODO: получить из steam_app_cache если есть
                "created_at": None  # TODO: получить из trends_seed_apps если есть
            }
            
            # Проверяем Intent Freshness Gate (отключается в Explore Mode)
            if not explore_mode:
                freshness_gate = check_intent_freshness_gate(app_data, signals)
                if not freshness_gate.get("passes", False):
                    excluded_count += 1
                    excluded_reasons["no_freshness"] = excluded_reasons.get("no_freshness", 0) + 1
                    diagnostic["excluded_reasons"]["no_freshness"] = diagnostic["excluded_reasons"].get("no_freshness", 0) + 1
                    logger.debug(f"Excluded app_id {app_id}: Intent Freshness Gate failed - {freshness_gate.get('reason', 'unknown')}")
                    continue
            else:
                # В Explore Mode создаем фиктивный freshness_gate для совместимости
                freshness_gate = {"passes": True, "reason": "explore_mode"}
            
            # Проверяем Success Penalty Gate
            success_penalty = check_success_penalty_gate(app_data, intent_score)
            final_intent_score = success_penalty.get("final_intent_score", intent_score)
            
            # Вычисляем вердикт
            # Для вердикта нужен behavioral_intent_score, получаем его из анализа
            # Но для оптимизации используем упрощённую логику
            behavioral_intent_score = 0
            for signal in signals:
                signal_text = signal.get("text", "") or ""
                if signal_text:
                    detected = detect_intent_keywords(signal_text)
                    if detected:
                        behavioral_intent_score = 10  # Минимальный вес для наличия behavioral intent
                        break
            
            verdict = calculate_verdict(
                intent_score,
                behavioral_intent_score,
                freshness_gate,
                success_penalty
            )
            
            # Переводим reasons на русский
            intent_reasons_raw = row.get("intent_reasons") or []
            quality_reasons_raw = row.get("quality_reasons") or []
            
            # Убеждаемся что это список
            if not isinstance(intent_reasons_raw, list):
                intent_reasons_raw = []
            if not isinstance(quality_reasons_raw, list):
                quality_reasons_raw = []
            
            # Переводим на русский
            intent_reasons_ru = translate_reasons_list(intent_reasons_raw)
            quality_reasons_ru = translate_reasons_list(quality_reasons_raw)
            
            # Вычисляем publisher_status_code из steam_app_cache.publishers (единственный источник истины)
            publishers_raw = row.get("publishers")
            publisher_status_code = compute_publisher_status(publishers_raw)
            publisher_status_label = map_publisher_status_label(publisher_status_code)
            
            games.append({
                "app_id": app_id,
                "title": title,
                "name": title,  # Для обратной совместимости
                "steam_url": row["steam_url"] or f"https://store.steampowered.com/app/{app_id}/",
                "developer": row["developer_name"],
                "publisher": row["publisher_name"],
                "publisher_status_code": publisher_status_code,  # Код для программной обработки
                "publisher_status": publisher_status_label,  # Человекочитаемый текст на русском
                "stage": row["stage"],
                "has_demo": row["has_demo"] or False,
                "price_eur": float(row["price_eur"]) if row["price_eur"] else None,
                "intent_score": final_intent_score,  # v3: используем final_intent_score после penalty
                "quality_score": quality_score,
                # ТОЛЬКО русские причины в ответе списка (v3)
                "intent_reasons_ru": intent_reasons_ru,
                "quality_reasons_ru": quality_reasons_ru,
                "recent_reviews_30d": row["recent_reviews_count_30d"] or 0,
                "positive_ratio": (row["all_positive_percent"] or 0) / 100.0 if row["all_positive_percent"] else 0.0,
                "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
                "release_date": release_date_obj.isoformat() if isinstance(release_date_obj, date) else (release_date.isoformat() if hasattr(release_date, 'isoformat') else str(release_date)),
                # v3: добавляем вердикт
                "verdict": verdict.get("verdict_code"),
                "verdict_label_ru": verdict.get("verdict_label_ru")
            })
        
        diagnostic["after_python_filters"] = len(games)
        
        if excluded_count > 0:
            logger.info(f"Deals list: excluded {excluded_count} games. Reasons: {excluded_reasons}")
        
        logger.info(f"Deals list: returning {len(games)} games (excluded {excluded_count}, explore_mode={explore_mode})")
        logger.info(f"Deals list diagnostic: {diagnostic}")
        
        # Подсчитываем статистику по названиям
        missing_names = sum(1 for g in games if g.get("title", "").startswith("App "))
        missing_names_pct = round((missing_names / len(games) * 100) if games else 0, 1)
        
        logger.info("Deals list: returned %s games, missing_names=%s (%.1f%%)", len(games), missing_names, missing_names_pct)
        
        return {
            "status": "ok",
            "games": games,
            "count": len(games),
            "total_before_filters": total_rows,
            "excluded": {
                "no_name": excluded_no_name,
                "no_release_date": excluded_no_release,
                "too_old": excluded_old
            },
            "debug": {
                "excluded_in_postprocessing": excluded_count,
                "excluded_reasons": excluded_reasons,
                "diagnostic": diagnostic,
                "explore_mode": explore_mode
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get deals list: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/shortlist")
async def get_deals_shortlist(
    limit: int = Query(30, ge=1, le=200, description="Maximum number of items to return"),
    min_confidence: float = Query(0.4, ge=0.0, le=1.0, description="Minimum confidence threshold"),
    archetypes: Optional[str] = Query(None, description="Comma-separated list of archetypes to filter"),
    publisher_status: Optional[str] = Query(None, description="Filter by publisher status: has_publisher|self_published|unknown"),
    temporal_context: Optional[str] = Query(None, description="Filter by temporal context: recent_interest|stale_interest|unknown"),
    publisher_types: Optional[str] = Query(None, description="Comma-separated list of publisher types (Vector #3)"),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Auto-Shortlist endpoint (Vector #2).
    Возвращает список игр с высоким confidence, отфильтрованный по параметрам.
    """
    try:
        # Определяем реальное имя колонки app_id в steam_review_daily
        app_id_col = detect_steam_review_app_id_column(db)
        
        # Базовый запрос для получения всех кандидатов из deal_intent_game
        base_query = text(f"""
            SELECT DISTINCT
                d.app_id,
                COALESCE(NULLIF(c.name, ''), g.title) as title,
                COALESCE(NULLIF(c.steam_url, ''), d.steam_url, 'https://store.steampowered.com/app/' || d.app_id::text || '/') as steam_url,
                d.stage,
                c.publishers as publishers,
                d.intent_score,
                d.quality_score,
                COALESCE(d.updated_at, NOW()) as updated_at
            FROM deal_intent_game d
            LEFT JOIN steam_app_cache c ON c.steam_app_id = d.app_id::bigint
            LEFT JOIN games g ON g.source = 'steam' AND g.source_id = d.app_id::text
            WHERE d.app_id IS NOT NULL
        """)
        
        rows = db.execute(base_query).mappings().all()
        
        items = []
        for row in rows:
            app_id = row["app_id"]
            
            # Получаем сигналы для этого app_id
            signals_query = text("""
                SELECT id, source, url, text, signal_type, confidence, published_at, created_at
                FROM deal_intent_signal
                WHERE app_id = :app_id
                ORDER BY COALESCE(published_at, created_at) DESC
                LIMIT 10
            """)
            signals_rows = db.execute(signals_query, {"app_id": app_id}).mappings().all()
            signals = []
            for s in signals_rows:
                signals.append({
                    "source": s["source"],
                    "url": s["url"],
                    "text": s["text"],
                    "signal_type": s["signal_type"],
                    "confidence": float(s["confidence"]) if s["confidence"] else 0.0,
                    "published_at": s["published_at"],
                    "created_at": s["created_at"]
                })
            
            # Подготавливаем app_data
            publishers_raw = row.get("publishers")
            publisher_status_code = compute_publisher_status(publishers_raw)
            
            release_date = row.get("release_date")
            release_date_obj = None
            if release_date:
                try:
                    if isinstance(release_date, str):
                        release_date_obj = datetime.fromisoformat(release_date.replace('Z', '+00:00')).date()
                    elif hasattr(release_date, 'date'):
                        release_date_obj = release_date.date()
                    else:
                        release_date_obj = release_date
                except Exception:
                    pass
            
            app_data = {
                "app_id": app_id,
                "publisher_status": publisher_status_code,
                "stage": row.get("stage"),
                "release_date": release_date_obj,
                "has_demo": row.get("has_demo", False),
                "price_eur": float(row["price_eur"]) if row.get("price_eur") else None,
                "all_reviews_count": row.get("all_reviews_count", 0),
                "recent_reviews_count_30d": row.get("recent_reviews_count_30d", 0),
                "all_positive_percent": row.get("all_positive_percent", 0),
            }
            
            # Выполняем анализ для получения gates
            analysis = analyze_deal_intent(app_data, signals)
            freshness_gate = analysis.get("freshness_gate", {})
            success_penalty = analysis.get("success_penalty", {})
            
            intent_score_final = analysis.get("final_intent_score", row.get("intent_score", 0))
            quality_score = row.get("quality_score", 0)
            behavioral_intent_score = analysis.get("behavioral_intent_score", 0)
            
            # Строим thesis
            thesis_data = build_deal_thesis(
                app_data=app_data,
                signals=signals,
                scores={"intent_score": intent_score_final, "quality_score": quality_score},
                gates={"freshness_gate": freshness_gate, "success_penalty": success_penalty}
            )
            
            confidence = thesis_data.get("confidence", 0.0)
            thesis_archetype = thesis_data.get("thesis_archetype", "unclear_intent")
            temporal_context_val = thesis_data.get("temporal_context", "unknown")
            publisher_interest = thesis_data.get("publisher_interest", {})
            who_might_care_codes = publisher_interest.get("who_might_care_codes", [])
            
            # Фильтры
            if confidence < min_confidence:
                continue
            
            if archetypes:
                archetype_list = [a.strip() for a in archetypes.split(",")]
                if thesis_archetype not in archetype_list:
                    continue
            
            if publisher_status and publisher_status_code != publisher_status:
                continue
            
            if temporal_context and temporal_context_val != temporal_context:
                continue
            
            # Vector #3: Фильтр по publisher_types
            if publisher_types:
                publisher_types_list = [pt.strip() for pt in publisher_types.split(",")]
                if not set(who_might_care_codes) & set(publisher_types_list):
                    continue
            
            # Вычисляем verdict
            verdict_result = calculate_verdict(
                intent_score=intent_score_final,
                behavioral_intent_score=behavioral_intent_score,
                freshness_gate=freshness_gate,
                success_penalty=success_penalty
            )
            
            # Формируем item (по ТЗ: БЕЗ headline и why_now)
            publisher_status_label = map_publisher_status_label(publisher_status_code)
            updated_at = row.get("updated_at")
            updated_at_iso = updated_at.isoformat() if updated_at and hasattr(updated_at, 'isoformat') else (str(updated_at) if updated_at else None)
            
            items.append({
                "app_id": app_id,
                "title": row.get("title") or f"App {app_id}",
                "steam_url": row.get("steam_url") or f"https://store.steampowered.com/app/{app_id}/",
                "stage": row.get("stage", "unknown"),
                "publisher_status_code": publisher_status_code,
                "publisher_status": publisher_status_label,
                "temporal_context": temporal_context_val,
                "confidence": confidence,
                "thesis_archetype": thesis_archetype,
                "publisher_types": who_might_care_codes,  # Vector #3
                "publisher_types_ru": publisher_interest.get("who_might_care", []),  # Vector #3
                "intent_score": intent_score_final,
                "quality_score": quality_score,
                "verdict": verdict_result.get("verdict_code", "unknown"),
                "verdict_label_ru": verdict_result.get("verdict_label_ru", "Неизвестно"),
                "updated_at": updated_at_iso,
                "_intent_score_final": intent_score_final  # Для сортировки
            })
        
        # Сортировка: 1) confidence desc, 2) temporal_context recent_interest выше, 3) intent_score desc
        items.sort(key=lambda x: (
            -x["confidence"],
            0 if x["temporal_context"] == "recent_interest" else 1,
            -x["_intent_score_final"]
        ))
        
        # Удаляем служебные поля перед возвратом
        for item in items:
            item.pop("_intent_score_final", None)
        
        # Применяем limit
        items = items[:limit]
        
        return {
            "status": "ok",
            "count": len(items),
            "items": items
        }
        
    except Exception as e:
        logger.error(f"Failed to get deals shortlist: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/diagnostics")
async def get_deals_diagnostics(
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Диагностика deals системы с детальными причинами пустоты.
    """
    try:
        # Определяем реальное имя колонки app_id в steam_review_daily
        app_id_col = detect_steam_review_app_id_column(db)
        
        # Статистика
        stats_query = text("""
            SELECT 
                (SELECT COUNT(*) FROM trends_seed_apps WHERE is_active = true) as seed_total,
                (SELECT COUNT(*) FROM deal_intent_game) as snapshot_rows,
                (SELECT COUNT(*) FROM deal_intent_game WHERE intent_score > 0) as intent_gt_0,
                (SELECT COUNT(*) FROM deal_intent_game WHERE quality_score > 0) as quality_gt_0,
                (SELECT COUNT(*) FROM deal_intent_signal) as signals_total,
                (SELECT COUNT(*) FROM deal_intent_signal WHERE signal_type = 'intent_keyword') as matched_signals,
                (SELECT AVG(intent_score) FROM deal_intent_game WHERE intent_score > 0) as avg_intent_score,
                (SELECT COUNT(*) FROM deal_intent_action_log 
                 WHERE created_at >= now() - interval '24 hours') as alerts_24h
        """)
        
        stats = db.execute(stats_query).mappings().first()
        
        # Self-published count
        self_pub_query = text("""
            SELECT COUNT(*) as cnt
            FROM deal_intent_game
            WHERE publisher_name IS NULL 
               OR publisher_name = ''
               OR publisher_name = developer_name
        """)
        self_published = db.execute(self_pub_query).scalar() or 0
        
        # Причины нулевых scores
        zero_reasons_query = text("""
            SELECT 
                COUNT(*) FILTER (WHERE d.publisher_name IS NOT NULL 
                    AND d.publisher_name != '' 
                    AND d.publisher_name != d.developer_name) as has_publisher,
                COUNT(*) FILTER (WHERE NOT EXISTS (
                    SELECT 1 FROM deal_intent_signal s WHERE s.app_id = d.app_id
                )) as no_external_signals,
                COUNT(*) FILTER (WHERE d.release_date IS NOT NULL 
                    AND d.release_date < CURRENT_DATE - INTERVAL '3 years') as old_releases
            FROM deal_intent_game d
        """)
        zero_reasons = db.execute(zero_reasons_query).mappings().first()
        
        # Топ intent reasons
        reasons_query = text("""
            SELECT 
                jsonb_array_elements_text(intent_reasons) as reason,
                COUNT(*) as count
            FROM deal_intent_game
            WHERE intent_reasons IS NOT NULL
            GROUP BY reason
            ORDER BY count DESC
            LIMIT 10
        """)
        
        reasons_rows = db.execute(reasons_query).mappings().all()
        top_intent_reasons = {row["reason"]: row["count"] for row in reasons_rows}
        
        snapshot_rows = stats["snapshot_rows"] or 0
        seed_total = stats["seed_total"] or 0
        
        # Coverage percentage
        coverage_pct = round((snapshot_rows / seed_total * 100) if seed_total > 0 else 0, 1)
        
        return {
            "status": "ok",
            "seed_total": seed_total,
            "snapshot_rows": snapshot_rows,
            "coverage_pct": coverage_pct,
            "intent_gt_0": stats["intent_gt_0"] or 0,
            "quality_gt_0": stats["quality_gt_0"] or 0,
            "self_published": self_published,
            "signals_total": stats["signals_total"] or 0,
            "matched_signals": stats["matched_signals"] or 0,
            "avg_intent_score": round(float(stats["avg_intent_score"] or 0), 1),
            "top_intent_reasons": top_intent_reasons,
            "alerts_24h": stats["alerts_24h"] or 0,
            "top_zero_reasons": {
                "has_publisher": zero_reasons["has_publisher"] or 0,
                "no_external_signals": zero_reasons["no_external_signals"] or 0,
                "old_releases": zero_reasons["old_releases"] or 0
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get deals diagnostics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bootstrap")
async def bootstrap_deals(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Принудительное заполнение deal_intent_game для bootstrap.
    Берёт топ-50 игр без издателя и записывает snapshot с минимальным intent_score.
    """
    try:
        from apps.worker.tasks.deal_intent_tasks import deal_intent_snapshot_task
        
        logger.info("Deals bootstrap: starting, limit=%s", limit)
        
        # Запускаем snapshot task синхронно (выполняется в API контейнере)
        try:
            result = deal_intent_snapshot_task(limit=limit)
            logger.info("Deals bootstrap: task completed, result=%s", result)
        except Exception as task_err:
            logger.error(f"Deals bootstrap: task failed with exception: {type(task_err).__name__}: {task_err}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Task failed: {str(task_err)}")
        
        # Проверяем результат
        if result.get("status") != "ok":
            error_msg = result.get("error", "Bootstrap failed")
            logger.error(f"Deals bootstrap: task returned error status: {error_msg}")
            raise HTTPException(status_code=500, detail=error_msg)
        
        # Получаем статистику после bootstrap
        stats_query = text("""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE intent_score > 0) as intent_gt_0,
                COUNT(*) FILTER (WHERE intent_score >= 10) as intent_gt_10,
                AVG(intent_score) as avg_intent
            FROM deal_intent_game
        """)
        
        stats = db.execute(stats_query).mappings().first()
        
        return {
            "status": "ok",
            "bootstrap_result": result,
            "after_bootstrap": {
                "total_games": stats["total"] or 0,
                "intent_gt_0": stats["intent_gt_0"] or 0,
                "intent_gt_10": stats["intent_gt_10"] or 0,
                "avg_intent_score": round(float(stats["avg_intent"] or 0), 1)
            }
        }
        
    except Exception as e:
        logger.error(f"Deals bootstrap failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{app_id}/detail")
async def get_deal_detail(
    app_id: int,
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Детальная информация по игре v3.1 с 3-слойным breakdown, gates и вердиктом.
    """
    try:
        # Определяем реальное имя колонки app_id в steam_review_daily
        app_id_col = detect_steam_review_app_id_column(db)
        
        # Получаем данные из deal_intent_game с JOIN для названий и created_at
        query = text(f"""
            SELECT 
                d.*,
                COALESCE(NULLIF(c.name, ''), g.title) as title,
                COALESCE(NULLIF(c.steam_url, ''), d.steam_url) as steam_url,
                c.publishers as publishers,
                d.publisher_name,
                d.developer_name,
                COALESCE(c.release_date, d.release_date) as release_date,
                srd.recent_reviews_count_30d,
                srd.all_positive_percent,
                srd.all_reviews_count,
                tsa.created_at as seed_created_at
            FROM deal_intent_game d
            LEFT JOIN steam_app_cache c ON c.steam_app_id = d.app_id::bigint
            LEFT JOIN games g ON g.source = 'steam' AND g.source_id = d.app_id::text
            LEFT JOIN steam_review_daily srd ON srd.{app_id_col} = d.app_id::bigint
                AND srd.day = (SELECT MAX(day) FROM steam_review_daily WHERE {app_id_col} = d.app_id::bigint)
            LEFT JOIN trends_seed_apps tsa ON tsa.steam_app_id = d.app_id
            WHERE d.app_id = :app_id
            LIMIT 1
        """)
        
        row = db.execute(query, {"app_id": app_id}).mappings().first()
        
        if not row:
            raise HTTPException(status_code=404, detail=f"Game {app_id} not found in deals")
        
        # Получаем сигналы
        signals_query = text("""
            SELECT id, source, url, text, signal_type, confidence, published_at, created_at
            FROM deal_intent_signal
            WHERE app_id = :app_id
            ORDER BY COALESCE(published_at, created_at) DESC
            LIMIT 10
        """)
        
        signals_rows = db.execute(signals_query, {"app_id": app_id}).mappings().all()
        
        signals = []
        # Для расчёта behavioral_last_days
        # (минимальное количество дней с момента самого свежего behavioral-сигнала)
        # Вычисляется позже при формировании behavioral_signals_found
        for s in signals_rows:
            signals.append({
                "source": s["source"],
                "url": s["url"],
                "text": s["text"],
                "signal_type": s["signal_type"],
                "confidence": float(s["confidence"]) if s["confidence"] else 0.0,
                "published_at": s["published_at"],
                "created_at": s["created_at"]
            })
        
        # Подготавливаем app_data для анализа
        release_date = row.get("release_date")
        release_date_obj = None
        if release_date:
            try:
                if isinstance(release_date, str):
                    release_date_obj = datetime.fromisoformat(release_date.replace('Z', '+00:00')).date()
                elif hasattr(release_date, 'date'):
                    release_date_obj = release_date.date()
                else:
                    release_date_obj = release_date
            except Exception:
                pass
        
        age_days = (date.today() - release_date_obj).days if release_date_obj else None
        
        # Вычисляем publisher_status из steam_app_cache.publishers (единственный источник истины)
        publishers_raw = row.get("publishers")
        publisher_status = compute_publisher_status(publishers_raw)
        
        app_data = {
            "app_id": app_id,
            "publisher_name": row.get("publisher_name"),
            "developer_name": row.get("developer_name"),
            "publisher_status": publisher_status,  # Добавляем publisher_status в app_data
            "stage": row.get("stage"),
            "release_date": release_date_obj,
            "has_demo": row.get("has_demo", False),
            "price_eur": float(row["price_eur"]) if row["price_eur"] else None,
            "all_reviews_count": row.get("all_reviews_count", 0),
            "recent_reviews_count_30d": row.get("recent_reviews_count_30d", 0),
            "all_positive_percent": row.get("all_positive_percent", 0),
            "steam_page_created_at": row.get("seed_created_at"),
            "created_at": row.get("seed_created_at"),
            "external_links": row.get("external_links") or {}
        }
        
        # Выполняем полный анализ v3
        analysis = analyze_deal_intent(app_data, signals)
        
        intent_score_raw = row.get("intent_score") or 0
        intent_score_final = analysis.get("final_intent_score", intent_score_raw)
        quality_score = row.get("quality_score") or 0
        
        # Проверяем gates
        freshness_gate = analysis.get("freshness_gate", {})
        success_penalty = analysis.get("success_penalty", {})
        verdict = analysis.get("verdict", {})
        
        # Формируем publisher_status на русском для UI (для обратной совместимости)
        publisher_status_ru_map = {
            "has_publisher": "Есть издатель",
            "self_published": "Самоиздание",
            "unknown": "Неизвестно"
        }
        publisher_status_ru = publisher_status_ru_map.get(publisher_status, "Неизвестно")
        
        # Формируем stage на русском
        stage_ru_map = {
            "coming_soon": "Скоро релиз",
            "demo": "Демо",
            "early_access": "Ранний доступ",
            "released": "Выпущено"
        }
        stage_ru = stage_ru_map.get(row.get("stage", "").lower(), row.get("stage", "Неизвестно"))
        
        # Формируем 3-слойный intent_breakdown
        intent_breakdown = []
        behavioral_last_days: Optional[int] = None
        
        # Слой 1: Behavioral Intent
        behavioral_score = analysis.get("behavioral_intent_score", 0)
        if behavioral_score > 0:
            # Находим behavioral signals
            behavioral_signals_found = []
            for signal in signals:
                signal_text = signal.get("text", "") or ""
                if signal_text:
                    detected = detect_intent_keywords(signal_text)
                    if detected:
                        keywords = list(detected.keys())
                        signal_date = signal.get("published_at") or signal.get("created_at")
                        days_ago = None
                        if signal_date:
                            try:
                                if isinstance(signal_date, str):
                                    signal_date = datetime.fromisoformat(signal_date.replace('Z', '+00:00'))
                                if isinstance(signal_date, datetime):
                                    days_ago = (datetime.utcnow() - signal_date.replace(tzinfo=None)).days
                            except:
                                pass
                        
                        if days_ago is not None:
                            if behavioral_last_days is None or days_ago < behavioral_last_days:
                                behavioral_last_days = days_ago

                        behavioral_signals_found.append({
                            "source": signal.get("source", "unknown"),
                            "ts": signal_date.isoformat() if isinstance(signal_date, datetime) else (signal_date.isoformat() if hasattr(signal_date, 'isoformat') else None),
                            "text": signal_text[:200] if len(signal_text) > 200 else signal_text,
                            "url": signal.get("url"),
                            "matched_keywords": keywords,
                            "days_ago": days_ago
                        })
            
            if behavioral_signals_found:
                # Группируем по типам keywords
                keyword_weights = {
                    "looking_for_publisher": 40,
                    "funding": 35,
                    "pitch_deck": 30,
                    "marketing_help": 20,
                    "contact_open": 15,
                    "publisher_wanted": 25
                }
                
                for signal_data in behavioral_signals_found[:3]:  # Топ-3 сигнала
                    keywords = signal_data.get("matched_keywords", [])
                    if keywords:
                        keyword = keywords[0]
                        weight = keyword_weights.get(keyword, 20)
                        source = signal_data.get("source", "unknown")
                        days_ago = signal_data.get("days_ago")
                        
                        intent_breakdown.append({
                            "label_ru": translate_reason_to_ru(keyword),
                            "points": weight,
                            "source": source,
                            "evidence": signal_data.get("text", "")[:100] if signal_data.get("text") else None,
                            "ts": signal_data.get("ts")
                        })
        
        # Слой 2: Structural Intent
        structural_score = analysis.get("structural_intent_score", 0)
        structural_reasons = []
        intent_reasons_raw = row.get("intent_reasons") or []
        if isinstance(intent_reasons_raw, list):
            for reason in intent_reasons_raw:
                if ":" not in reason and reason not in ["no_demo", "no_contacts", "zero_reviews", "very_few_reviews"]:
                    structural_reasons.append(reason)
        
        structural_points_map = {
            "no_publisher_on_steam": 12,
            "self_published": 10,
            "self_published_early": 15,
            "stage_demo": 18,
            "stage_coming_soon": 15,
            "stage_early_access_fresh": 12,
            "stage_early_access": 8,
            "stage_released_fresh": 6,
            "has_website": 3,
            "has_discord": 3,
            "has_publisher": -3,
            "known_publisher_penalty": -20,
            "old_release_penalty": -15
        }
        
        for reason in structural_reasons[:3]:  # Топ-3 structural reasons
            base_reason = reason.split(":")[0].strip()
            points = structural_points_map.get(base_reason, 0)
            if points != 0:
                intent_breakdown.append({
                    "label_ru": translate_reason_to_ru(reason),
                    "points": points,
                    "source": "steam",
                    "evidence": f"Steam данные: {base_reason}",
                    "ts": None
                })
        
        # Слой 3: Temporal Boost
        temporal_score = analysis.get("temporal_boost_score", 0)
        if temporal_score > 0:
            freshness_factors = freshness_gate.get("freshness_factors", [])
            for factor in freshness_factors[:2]:  # Топ-2 temporal factors
                if "steam_page_fresh" in factor:
                    intent_breakdown.append({
                        "label_ru": "Свежая страница Steam",
                        "points": 8,
                        "source": "steam",
                        "evidence": factor,
                        "ts": None
                    })
                elif "external_signal_fresh" in factor:
                    intent_breakdown.append({
                        "label_ru": "Недавний сигнал намерения",
                        "points": 10,
                        "source": "external",
                        "evidence": factor,
                        "ts": None
                    })
                elif "stage_fresh" in factor:
                    intent_breakdown.append({
                        "label_ru": "Ранняя стадия разработки",
                        "points": 5,
                        "source": "steam",
                        "evidence": factor,
                        "ts": None
                    })
        
        # Обеспечиваем минимум 4 элемента
        if len(intent_breakdown) < 4:
            # Добавляем дополнительные факторы
            publisher_name = (app_data.get("publisher_name") or "").strip()
            if not publisher_name:
                intent_breakdown.append({
                    "label_ru": "Нет издателя на Steam",
                    "points": 12,
                    "source": "steam",
                    "evidence": "Steam данные: publisher_name пусто",
                    "ts": None
                })
            
            if row.get("has_demo"):
                intent_breakdown.append({
                    "label_ru": "Есть демо",
                    "points": 3,
                    "source": "steam",
                    "evidence": "Steam данные: has_demo=true",
                    "ts": None
                })
            
            if (row.get("recent_reviews_count_30d") or 0) > 0:
                intent_breakdown.append({
                    "label_ru": "Активность отзывов",
                    "points": min(15, row.get("recent_reviews_count_30d", 0) // 10),
                    "source": "steam",
                    "evidence": f"{row.get('recent_reviews_count_30d', 0)} отзывов за 30 дней",
                    "ts": None
                })
        
        # Формируем quality_breakdown (минимум 4 элемента)
        quality_breakdown = []
        quality_reasons_raw = row.get("quality_reasons") or []
        
        quality_points_map = {
            "visual_quality": 20,
            "clear_usp": 15,
            "demo_reviews": 15,
            "update_tempo": 12,
            "team_activity": 10,
            "adequate_scale": 8,
            "positive_ratio": 20,
            "reviews_30d": 15,
            "has_demo": 10
        }
        
        if isinstance(quality_reasons_raw, list):
            for reason in quality_reasons_raw:
                base_reason = reason.split(":")[0].strip()
                points = quality_points_map.get(base_reason, 0)
                if points > 0:
                    quality_breakdown.append({
                        "label_ru": translate_reason_to_ru(reason),
                        "points": points,
                        "source": "steam",
                        "evidence": _extract_value_from_reason(reason, row),
                        "ts": None
                    })
        
        # Обеспечиваем минимум 4 элемента для quality
        if len(quality_breakdown) < 4:
            # Positive ratio
            if row.get("all_positive_percent"):
                pct = row.get("all_positive_percent", 0)
                ratio_score = 0
                if pct >= 85:
                    ratio_score = 20
                elif pct >= 75:
                    ratio_score = 15
                elif pct >= 65:
                    ratio_score = 10
                else:
                    ratio_score = 5
                
                quality_breakdown.append({
                    "label_ru": "Рейтинг отзывов",
                    "points": ratio_score,
                    "source": "steam",
                    "evidence": f"{pct}% положительных",
                    "ts": None
                })
            
            # Reviews 30d
            if (row.get("recent_reviews_count_30d") or 0) > 0:
                count = row.get("recent_reviews_count_30d", 0)
                log_score = min(15, int(math.log10(count + 1) * 5))
                quality_breakdown.append({
                    "label_ru": "Активность отзывов",
                    "points": log_score,
                    "source": "steam",
                    "evidence": f"{count} отзывов за 30 дней",
                    "ts": None
                })
            
            # Has demo
            if row.get("has_demo"):
                quality_breakdown.append({
                    "label_ru": "Есть демо",
                    "points": 10,
                    "source": "steam",
                    "evidence": "Steam данные: has_demo=true",
                    "ts": None
                })
            
            # Visual quality (если есть трейлер/капсула)
            if row.get("steam_url"):
                quality_breakdown.append({
                    "label_ru": "Страница Steam",
                    "points": 5,
                    "source": "steam",
                    "evidence": "Есть страница на Steam",
                    "ts": None
                })
        
        # Формируем behavioral_signals для ответа
        behavioral_signals = []
        for signal in signals:
            signal_text = signal.get("text", "") or ""
            if signal_text:
                detected = detect_intent_keywords(signal_text)
                if detected:
                    signal_date = signal.get("published_at") or signal.get("created_at")
                    behavioral_signals.append({
                        "source": signal.get("source", "unknown"),
                        "ts": signal_date.isoformat() if signal_date and hasattr(signal_date, 'isoformat') else (str(signal_date) if signal_date else None),
                        "text": signal_text[:300] if len(signal_text) > 300 else signal_text,
                        "url": signal.get("url"),
                        "matched_keywords": list(detected.keys())
                    })
        
        # Формируем thesis_data (Vector #1)
        thesis_data = build_deal_thesis(
            app_data=app_data,
            signals=signals,
            scores={"intent_score": intent_score_final, "quality_score": quality_score},
            gates={"freshness_gate": freshness_gate, "success_penalty": success_penalty}
        )
        
        # Формируем итоговый ответ
        return {
            "app_id": app_id,
            "title": row.get("title") or f"App {app_id}",
            "steam_url": row.get("steam_url") or f"https://store.steampowered.com/app/{app_id}/",
            "stage": stage_ru,
            "publisher_status": publisher_status_ru,  # Для обратной совместимости возвращаем русский вариант
            "publisher_status_code": publisher_status,  # Добавляем код для программной обработки
            "release_date": release_date_obj.isoformat() if release_date_obj else None,
            "age_days": age_days,
            "intent_score_raw": intent_score_raw,
            "intent_score_final": intent_score_final,
            "quality_score": quality_score,
            "verdict": verdict.get("verdict_label_ru", "Неизвестно"),
            "gates": {
                "freshness_gate_passed": freshness_gate.get("passes", False),
                "freshness_gate_reason_ru": freshness_gate.get("reason", "Не проверено"),
                "success_penalty_applied": success_penalty.get("penalty_applied", False),
                "success_penalty_multiplier": success_penalty.get("penalty_multiplier", 1.0),
                "success_penalty_reason_ru": success_penalty.get("reason", "Не применён")
            },
            "intent_breakdown": intent_breakdown[:8],  # Максимум 8 элементов
            "quality_breakdown": quality_breakdown[:8],  # Максимум 8 элементов
            "behavioral_signals": behavioral_signals[:10],  # Последние 10 сигналов
            "behavioral_last_days": behavioral_last_days,
            "thesis": thesis_data,
            "thesis_explain": build_thesis_explain(
                thesis_data=thesis_data,
                publisher_interest=thesis_data.get("publisher_interest", {}),
                publisher_status_code=publisher_status,
                signals=signals,
                app_data=app_data
            )
        }
        
        # Формируем детальный breakdown для intent (минимум 4 элемента)
        intent_reasons_raw = row.get("intent_reasons") or []
        intent_breakdown = []
        
        # Маппинг reasons -> points (v2.0: обновлённые значения из scorer)
        intent_points_map = {
            "no_publisher_on_steam": 18,
            "self_published": 12,
            "self_published_early": 20,
            "has_publisher": -3,
            "stage_demo": 22,
            "stage_coming_soon": 18,
            "stage_early_access": 10,
            "stage_early_access_fresh": 15,
            "stage_early_access_old": 5,
            "stage_released_fresh": 8,
            "stage_released": 3,
            "stage_released_medium": -5,
            "stage_penalty_released": -15,
            "stage_released_unknown": -5,
            "has_website": 5,
            "has_discord": 5,
            "reviews_30d_200": 25,
            "reviews_30d_100": 20,
            "reviews_30d_50": 15,
            "reviews_30d_20": 12,
            "reviews_30d_10": 8,
            "reviews_30d_5": 5,
            "no_reviews_need_marketing": 4,
            "low_reviews_need_marketing": 3,
            "few_reviews": 2,
            "many_reviews_no_activity": -2,
            "has_demo_early_stage": 6,
            "has_demo": 4,
            "free_game": 4,
            "very_low_price": 3,
            "low_price": 2,
            "medium_price": 1,
            "demo_no_traction": 5,
            "no_demo": 0,
            "no_contacts": 0,
            "zero_reviews": 0,
            "very_few_reviews": 0,
            "old_release_penalty": -10,
            "known_publisher_penalty": -20,
        }
        
        # Добавляем breakdown из reasons
        if isinstance(intent_reasons_raw, list):
            for reason in intent_reasons_raw:
                # Извлекаем базовый ключ (убираем суффиксы типа _100, _50)
                base_reason = reason.split(":")[0].strip()  # Убираем ": found in source"
                if "_" in base_reason and base_reason.split("_")[-1].isdigit():
                    # Для reviews_30d_X берём базовый ключ
                    base_reason = "_".join(base_reason.split("_")[:-1])
                
                points = intent_points_map.get(base_reason, 0)
                if "reviews_30d" in reason and points == 0:
                    # Пытаемся извлечь число из reason
                    match = re.search(r'reviews_30d_(\d+)', reason)
                    if match:
                        count = int(match.group(1))
                        if count >= 100:
                            points = 20
                        elif count >= 50:
                            points = 15
                        elif count >= 20:
                            points = 10
                        elif count >= 10:
                            points = 7
                        else:
                            points = 5
                
                evidence = ""
                if "reviews_30d" in reason:
                    evidence = f"steam_review_daily: {row.get('recent_reviews_count_30d', 0)} отзывов за 30 дней"
                elif "stage" in reason:
                    evidence = f"steam_app_cache: stage={row.get('stage', 'unknown')}"
                elif "publisher" in reason or "self_published" in reason:
                    evidence = f"steam_app_cache: publisher={row.get('publisher_name', 'none')}"
                elif "website" in reason or "discord" in reason:
                    evidence = f"deal_intent_game: external_links"
                else:
                    evidence = "deal_intent_game"
                
                intent_breakdown.append({
                    "label": translate_reason_to_ru(reason),
                    "delta": points,
                    "value": _extract_value_from_reason(reason, row),
                    "evidence": evidence
                })
        
        # Если breakdown меньше 4 элементов, добавляем дополнительные факторы из данных
        if len(intent_breakdown) < 4:
            # Добавляем факторы на основе реальных данных
            if row.get("publisher_name"):
                intent_breakdown.append({
                    "label": "Издатель указан",
                    "delta": -5 if row.get("publisher_name") != row.get("developer_name") else 0,
                    "value": row.get("publisher_name"),
                    "evidence": "steam_app_cache"
                })
            
            if (row.get("recent_reviews_count_30d") or 0) > 0:
                intent_breakdown.append({
                    "label": "Активность отзывов",
                    "delta": min(20, int(row.get("recent_reviews_count_30d", 0) / 5)),
                    "value": f"{row.get('recent_reviews_count_30d', 0)} отзывов за 30 дней",
                    "evidence": "steam_review_daily"
                })
            
            if row.get("has_demo"):
                intent_breakdown.append({
                    "label": "Есть демо",
                    "delta": 3,
                    "value": "Да",
                    "evidence": "deal_intent_game"
                })
        
        # Ограничиваем до максимум 6, но минимум 4
        intent_breakdown = intent_breakdown[:6] if len(intent_breakdown) >= 4 else intent_breakdown
        
        # Формируем детальный breakdown для quality (минимум 4 элемента)
        quality_reasons_raw = row.get("quality_reasons") or []
        quality_breakdown = []
        
        quality_points_map = {
            "positive_ratio_95pct": 40,
            "positive_ratio_90pct": 35,
            "positive_ratio_85pct": 30,
            "positive_ratio_80pct": 25,
            "positive_ratio_75pct": 20,
            "positive_ratio_70pct": 15,
            "positive_ratio_60pct": 10,
            "has_demo": 15,
        }
        
        if isinstance(quality_reasons_raw, list):
            for reason in quality_reasons_raw:
                base_reason = reason
                points = quality_points_map.get(base_reason, 0)
                
                evidence = ""
                if "positive_ratio" in reason:
                    pct = row.get("all_positive_percent", 0)
                    evidence = f"steam_review_daily: positive_ratio={pct}%"
                elif "reviews_30d" in reason:
                    evidence = f"steam_review_daily: {row.get('recent_reviews_count_30d', 0)} отзывов"
                elif "has_demo" in reason:
                    evidence = "deal_intent_game: has_demo=true"
                else:
                    evidence = "deal_intent_game"
                
                quality_breakdown.append({
                    "label": translate_reason_to_ru(reason),
                    "delta": points,
                    "value": _extract_value_from_reason(reason, row),
                    "evidence": evidence
                })
        
        # Если breakdown меньше 4 элементов, добавляем дополнительные факторы
        if len(quality_breakdown) < 4:
            # Positive ratio
            if row.get("all_positive_percent"):
                pct = row.get("all_positive_percent", 0)
                ratio_score = 0
                if pct >= 95:
                    ratio_score = 40
                elif pct >= 90:
                    ratio_score = 35
                elif pct >= 85:
                    ratio_score = 30
                elif pct >= 80:
                    ratio_score = 25
                elif pct >= 75:
                    ratio_score = 20
                elif pct >= 70:
                    ratio_score = 15
                elif pct >= 60:
                    ratio_score = 10
                else:
                    ratio_score = 5
                
                quality_breakdown.append({
                    "label": "Рейтинг отзывов",
                    "delta": ratio_score,
                    "value": f"{pct}% положительных",
                    "evidence": "steam_review_daily"
                })
            
            # Reviews 30d
            if (row.get("recent_reviews_count_30d") or 0) > 0:
                reviews_30d = row.get("recent_reviews_count_30d", 0)
                log_reviews = math.log10(reviews_30d + 1)
                reviews_score = min(30, int(log_reviews * 10))
                
                quality_breakdown.append({
                    "label": "Активность отзывов",
                    "delta": reviews_score,
                    "value": f"{reviews_30d} отзывов за 30 дней",
                    "evidence": "steam_review_daily"
                })
            
            # Has demo
            if row.get("has_demo"):
                quality_breakdown.append({
                    "label": "Есть демо",
                    "delta": 15,
                    "value": "Да",
                    "evidence": "deal_intent_game"
                })
            
            # Total reviews
            if row.get("all_reviews_count", 0) > 0:
                quality_breakdown.append({
                    "label": "Всего отзывов",
                    "delta": 0,  # Информационный фактор
                    "value": f"{row.get('all_reviews_count', 0)}",
                    "evidence": "steam_review_daily"
                })
        
        # v2.0: Обеспечиваем минимум 4 элемента
        while len(quality_breakdown) < 4:
            if row.get("all_positive_percent") is not None and not any("рейтинг" in item.get("label", "").lower() or "positive" in item.get("label", "").lower() for item in quality_breakdown):
                pct = row.get("all_positive_percent", 0)
                quality_breakdown.append({
                    "label": "Рейтинг отзывов",
                    "delta": 0,  # Уже учтён в reasons
                    "value": f"{pct}% положительных",
                    "evidence": "steam_review_daily"
                })
            elif row.get("recent_reviews_count_30d", 0) > 0 and not any("30" in item.get("label", "") or "активность" in item.get("label", "").lower() for item in quality_breakdown):
                quality_breakdown.append({
                    "label": "Активность отзывов",
                    "delta": 0,  # Уже учтён в reasons
                    "value": f"{row.get('recent_reviews_count_30d', 0)} отзывов за 30 дней",
                    "evidence": "steam_review_daily"
                })
            elif row.get("all_reviews_count", 0) > 0 and not any("всего" in item.get("label", "").lower() or "total" in item.get("label", "").lower() for item in quality_breakdown):
                quality_breakdown.append({
                    "label": "Всего отзывов",
                    "delta": 0,
                    "value": f"{row.get('all_reviews_count', 0)}",
                    "evidence": "steam_review_daily"
                })
            elif row.get("has_demo") is not None and not any("демо" in item.get("label", "").lower() or "demo" in item.get("label", "").lower() for item in quality_breakdown):
                quality_breakdown.append({
                    "label": "Демо",
                    "delta": 15 if row.get("has_demo") else 0,
                    "value": "Да" if row.get("has_demo") else "Нет",
                    "evidence": "deal_intent_game"
                })
            else:
                # Последний резерв
                quality_breakdown.append({
                    "label": "Общая информация",
                    "delta": 0,
                    "value": f"App ID: {app_id}",
                    "evidence": "deal_intent_game"
                })
                break
        
        # Ограничиваем до максимум 6
        quality_breakdown = quality_breakdown[:6]
        
        # Определяем "почему попало в Deals"
        why_in_deals = []
        if row["intent_score"] > 0:
            why_in_deals.append(f"Намерение издателя: {row['intent_score']} баллов")
        if row["quality_score"] > 0:
            why_in_deals.append(f"Качество игры: {row['quality_score']} баллов")
        if not why_in_deals:
            why_in_deals.append("Попало в список по другим критериям")
        
        # Формируем DealThesis для старого формата ответа
        thesis_data_legacy = build_deal_thesis(
            app_data=app_data,
            signals=signals,
            scores={"intent_score": row.get("intent_score") or 0, "quality_score": row.get("quality_score") or 0},
            gates={"freshness_gate": freshness_gate, "success_penalty": success_penalty}
        )
        
        return {
            "status": "ok",
            "app_id": app_id,
            "title": row.get("title") or row.get("steam_name") or f"App {app_id}",
            "steam_url": row["steam_url"] or f"https://store.steampowered.com/app/{app_id}/",
            "developer": row["developer_name"],
            "publisher": row["publisher_name"],
            "release_date": row["release_date"].isoformat() if row["release_date"] else None,
            "stage": row["stage"],
            "has_demo": row["has_demo"] or False,
            "price_eur": float(row["price_eur"]) if row["price_eur"] else None,
            "tags": row["tags"] or {},
            "external_links": row["external_links"] or {},
            "intent_score": row["intent_score"] or 0,
            "quality_score": row["quality_score"] or 0,
            "intent_reasons": intent_reasons_raw,
            "quality_reasons": quality_reasons_raw,
            "intent_breakdown": intent_breakdown,
            "quality_breakdown": quality_breakdown,
            "why_in_deals": " | ".join(why_in_deals),
            "signals": signals,
            "signals_count": row["signals_count"] or 0,
            "recent_reviews_30d": row["recent_reviews_count_30d"] or 0,
            "positive_ratio": (row["all_positive_percent"] or 0) / 100.0 if row["all_positive_percent"] else 0.0,
            "all_reviews_count": row["all_reviews_count"] or 0,
            "sources": {
                "steam": {
                    "url": row["steam_url"] or f"https://store.steampowered.com/app/{app_id}/",
                    "reviews_count": row["all_reviews_count"] or 0,
                    "positive_ratio": (row["all_positive_percent"] or 0) / 100.0 if row["all_positive_percent"] else 0.0
                },
                "social": []  # Пока пусто, структура для будущего
            },
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
            "thesis": thesis_data_legacy
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get deal detail: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{app_id}/action")
async def create_action(
    app_id: int,
    request: ActionRequest,
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Создать действие для игры (request_pitch_deck, request_steamworks, send_offer, book_call, watchlist).
    """
    try:
        # Проверяем, что игра существует
        check_query = text("SELECT app_id FROM deal_intent_game WHERE app_id = :app_id")
        exists = db.execute(check_query, {"app_id": app_id}).scalar()
        
        if not exists:
            raise HTTPException(status_code=404, detail=f"Game {app_id} not found in deals")
        
        # Создаём запись в action_log
        insert_query = text("""
            INSERT INTO deal_intent_action_log (app_id, action_type, payload, created_at)
            VALUES (:app_id, :action_type, :payload, now())
            RETURNING id, created_at
        """)
        
        result = db.execute(
            insert_query,
            {
                "app_id": app_id,
                "action_type": request.action_type,
                "payload": request.payload or {}
            }
        ).mappings().first()
        
        db.commit()
        
        return {
            "status": "ok",
            "action_id": str(result["id"]),
            "app_id": app_id,
            "action_type": request.action_type,
            "created_at": result["created_at"].isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create action: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/signals/import")
async def import_signal(
    request: SignalImportRequest,
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Импортировать внешний сигнал (URL вручную).
    MVP: пользователь вставляет URL, система извлекает текст и прогоняет через INTENT_KEYWORDS.
    """
    try:
        # TODO: Реализовать извлечение текста из URL
        # Пока используем переданный text или заглушку
        signal_text = request.text or f"Signal from {request.source}: {request.url}"
        
        # Обнаруживаем intent keywords
        detected = detect_intent_keywords(signal_text)
        signal_type = "intent_keyword" if detected else "external_link"
        confidence = 0.8 if detected else 0.3
        
        # Создаём запись в deal_intent_signal
        insert_query = text("""
            INSERT INTO deal_intent_signal (app_id, source, url, text, signal_type, confidence, created_at)
            VALUES (:app_id, :source, :url, :text, :signal_type, :confidence, now())
            RETURNING id, created_at
        """)
        
        result = db.execute(
            insert_query,
            {
                "app_id": request.app_id,
                "source": request.source,
                "url": request.url,
                "text": signal_text,
                "signal_type": signal_type,
                "confidence": confidence
            }
        ).mappings().first()
        
        db.commit()
        
        # Если указан app_id, пересчитываем intent_score
        if request.app_id:
            try:
                _recalculate_deal_intent(db, request.app_id)
            except Exception as e:
                logger.warning(f"Failed to recalculate intent for app {request.app_id}: {e}")
        
        return {
            "status": "ok",
            "signal_id": str(result["id"]),
            "detected_intents": list(detected.keys()) if detected else [],
            "signal_type": signal_type,
            "confidence": confidence,
            "created_at": result["created_at"].isoformat()
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to import signal: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/signals/import_discord")
async def import_discord_signal(
    request: DiscordImportRequest,
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Импортировать сигнал из Discord (human-in-the-loop MVP).
    Пользователь копирует текст из Discord, система матчит keywords и извлекает Steam app_id.
    """
    try:
        from apps.worker.tasks.collect_deal_intent_signals_reddit import (
            extract_steam_app_ids,
            extract_links,
            detect_language,
            match_keywords
        )
        
        raw_text = request.raw_text.strip()
        if not raw_text:
            raise HTTPException(status_code=400, detail="raw_text не может быть пустым")
        
        # Матчим keywords
        keyword_result = match_keywords(raw_text)
        matched_keywords = keyword_result["matched_keywords"]
        intent_strength = keyword_result["intent_strength"]
        
        # Если нет keywords - возвращаем предупреждение, но не сохраняем
        if not matched_keywords or intent_strength == 0:
            return {
                "status": "no_match",
                "message": "Не найдены keywords намерения издателя в тексте",
                "matched_keywords": [],
                "extracted_app_ids": []
            }
        
        # Извлекаем Steam app_id
        extracted_app_ids = extract_steam_app_ids(raw_text, request.url or '')
        
        # Извлекаем ссылки
        extracted_links = extract_links(raw_text, request.url or '')
        
        # Определяем язык
        lang = detect_language(raw_text)
        
        # Парсим timestamp
        ts = datetime.utcnow()
        if request.ts:
            try:
                ts = datetime.fromisoformat(request.ts.replace('Z', '+00:00'))
            except:
                pass
        
        # Определяем app_id (если нашли один) или title_guess
        app_id = extracted_app_ids[0] if extracted_app_ids else None
        title_guess = None
        if not app_id:
            # Пытаемся извлечь название игры из текста (простая эвристика)
            # Ищем паттерны типа "Game Name" или "My Game"
            title_match = re.search(r'["\']([^"\']{3,50})["\']', raw_text)
            if title_match:
                title_guess = title_match.group(1)[:200]
        
        # Формируем URL (если не указан, создаём placeholder)
        signal_url = request.url or f"discord://manual/{datetime.utcnow().isoformat()}"
        
        # Сохраняем сигнал
        insert_query = text("""
            INSERT INTO deal_intent_signal (
                app_id, source, url, text, author, ts,
                matched_keywords, intent_strength, extracted_steam_app_ids,
                extracted_links, lang, title_guess, published_at, created_at
            ) VALUES (
                :app_id, 'discord_manual', :url, :text, :author, :ts,
                CAST(:matched_keywords AS jsonb), :intent_strength, 
                CAST(:extracted_app_ids AS integer[]),
                CAST(:extracted_links AS jsonb), :lang, :title_guess, :ts, NOW()
            )
            RETURNING id, created_at
        """)
        
        author_name = f"{request.server or 'Discord'}#{request.channel or 'manual'}"
        
        result = db.execute(
            insert_query,
            {
                "app_id": app_id,
                "url": signal_url,
                "text": raw_text[:5000],  # Ограничиваем длину
                "author": author_name[:200],
                "ts": ts,
                "matched_keywords": matched_keywords,
                "intent_strength": intent_strength,
                "extracted_app_ids": extracted_app_ids,
                "extracted_links": extracted_links,
                "lang": lang,
                "title_guess": title_guess
            }
        ).mappings().first()
        
        db.commit()
        
        # Если указан app_id, пересчитываем intent_score
        if app_id:
            try:
                _recalculate_deal_intent(db, app_id)
            except Exception as e:
                logger.warning(f"Failed to recalculate intent for app {app_id}: {e}")
        
        return {
            "status": "ok",
            "saved": 1,
            "signal_id": str(result["id"]),
            "matched": matched_keywords,
            "extracted_app_ids": extracted_app_ids,
            "intent_strength": intent_strength,
            "created_at": result["created_at"].isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to import Discord signal: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/signals/collect_reddit")
async def collect_reddit_signals(
    days: int = Query(90, ge=1, le=180, description="Количество дней назад для поиска постов (Vector A EXEC v1: минимум 90, лучше 180)"),
    limit_per_sub: int = Query(500, ge=1, le=1000, description="Максимум постов на сабреддит (Vector A EXEC v1: минимум 500, лучше 1000)"),
    include_comments: bool = Query(False, description="Собирать комментарии из постов (Vector A A2)"),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Запустить сбор Deal Intent Signals из Reddit (Vector A EXEC v1).
    Согласно TZ_SIGNAL_INGESTION_VECTOR_A_EXEC_V1.md.
    """
    try:
        from apps.worker.tasks.collect_deal_intent_signals_reddit import collect_deal_intent_signals_reddit_task
        
        logger.info(f"Starting Reddit Deal Intent Signals collection (Vector A EXEC v1), days={days}, limit_per_sub={limit_per_sub}, include_comments={include_comments}")
        
        # Запускаем task синхронно (выполняется в API контейнере)
        result = collect_deal_intent_signals_reddit_task(days=days, limit_per_sub=limit_per_sub, include_comments=include_comments)
        
        return {
            "status": "ok",
            "result": result
        }
        
    except Exception as e:
        logger.error(f"Failed to collect Reddit signals: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/signals/collect_steam_reviews")
async def collect_steam_reviews_signals(
    days: int = Query(180, ge=1, le=365, description="Количество дней назад для анализа review velocity (Vector A EXEC v1 A3: минимум 180)"),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Запустить сбор Deal Intent Signals из Steam Reviews (Vector A EXEC v1 A3).
    Согласно TZ_SIGNAL_INGESTION_VECTOR_A_EXEC_V1.md п.3.A3.
    """
    try:
        from apps.worker.tasks.collect_deal_intent_signals_steam_reviews import collect_deal_intent_signals_steam_reviews_task
        
        logger.info(f"Starting Steam Reviews Deal Intent Signals collection (Vector A EXEC v1 A3), days={days}")
        
        # Запускаем task синхронно (выполняется в API контейнере)
        result = collect_deal_intent_signals_steam_reviews_task(days=days)
        
        return {
            "status": "ok",
            "result": result
        }
        
    except Exception as e:
        logger.error(f"Failed to collect Steam Reviews signals: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/signals/collect_youtube")
async def collect_youtube_signals(
    days: int = Query(365, ge=1, le=365, description="Количество дней назад для поиска видео (Vector B: используем все данные)"),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Запустить сбор Deal Intent Signals из существующих YouTube данных (Vector B EXEC v1).
    Анализирует ExternalVideo (title) и ExternalCommentSample (comments).
    Согласно TZ_SIGNAL_INGESTION_VECTOR_B_EXEC_V1.md.
    """
    try:
        from apps.worker.tasks.collect_deal_intent_signals_youtube import collect_deal_intent_signals_youtube_task
        
        logger.info(f"Starting YouTube Deal Intent Signals collection (Vector B), days={days}")
        
        # Запускаем task синхронно (выполняется в API контейнере)
        result = collect_deal_intent_signals_youtube_task(days=days)
        
        if not result:
            result = {"status": "error", "error": "Task returned None"}
        
        return {
            "status": "ok",
            "result": result
        }
        
    except Exception as e:
        logger.error(f"Failed to collect YouTube signals: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _recalculate_deal_intent(db: Session, app_id: int):
    """
    Пересчитывает intent_score и quality_score для игры.
    """
    from apps.worker.analysis.db_introspection import detect_steam_review_app_id_column
    
    app_id_col = detect_steam_review_app_id_column(db)
    
    # Получаем данные игры
    query = text(f"""
        SELECT 
            seed.steam_app_id,
            COALESCE(NULLIF(c.name, ''), f.name, 'App #' || seed.steam_app_id::text) as steam_name,
            COALESCE(NULLIF(c.steam_url, ''), 'https://store.steampowered.com/app/' || seed.steam_app_id::text || '/') as steam_url,
            -- Developer: извлекаем первый элемент из JSONB массива
            CASE 
                WHEN c.developers IS NOT NULL AND jsonb_array_length(c.developers) > 0 THEN
                    c.developers->>0
                WHEN f.developers IS NOT NULL AND jsonb_array_length(f.developers) > 0 THEN
                    f.developers->>0
                ELSE NULL
            END as developer_name,
            -- Publisher: извлекаем первый элемент из JSONB массива
            CASE 
                WHEN c.publishers IS NOT NULL AND jsonb_array_length(c.publishers) > 0 THEN
                    c.publishers->>0
                WHEN f.publishers IS NOT NULL AND jsonb_array_length(f.publishers) > 0 THEN
                    f.publishers->>0
                ELSE NULL
            END as publisher_name,
            COALESCE(c.release_date, f.release_date) as release_date,
            -- Stage: определяем по release_date
            CASE 
                WHEN c.release_date IS NULL AND f.release_date IS NULL THEN 'coming_soon'
                WHEN c.release_date > CURRENT_DATE THEN 'coming_soon'
                WHEN c.release_date IS NOT NULL AND c.release_date <= CURRENT_DATE THEN 'released'
                WHEN f.release_date IS NOT NULL AND f.release_date <= CURRENT_DATE THEN 'released'
                ELSE 'released'
            END as stage,
            false as has_demo,  -- TODO: определить через tags или другие поля
            c.price_eur,
            c.tags,
            srd.all_reviews_count,
            srd.recent_reviews_count_30d,
            srd.all_positive_percent,
            srd.all_positive_percent / 100.0 as positive_ratio
        FROM trends_seed_apps seed
        LEFT JOIN steam_app_cache c ON c.steam_app_id = seed.steam_app_id::bigint
        LEFT JOIN steam_app_facts f ON f.steam_app_id = seed.steam_app_id
        LEFT JOIN steam_review_daily srd ON srd.{app_id_col} = seed.steam_app_id
            AND srd.day = (SELECT MAX(day) FROM steam_review_daily WHERE {app_id_col} = seed.steam_app_id)
        WHERE seed.steam_app_id = :app_id
          AND seed.is_active = true
    """)
    
    row = db.execute(query, {"app_id": app_id}).mappings().first()
    
    if not row:
        raise ValueError(f"Game {app_id} not found in seed apps")
    
    # Получаем сигналы
    signals_query = text("""
        SELECT source, url, text, signal_type, confidence
        FROM deal_intent_signal
        WHERE app_id = :app_id
    """)
    
    signals_rows = db.execute(signals_query, {"app_id": app_id}).mappings().all()
    signals = [dict(s) for s in signals_rows]
    
    # Анализируем
    app_data = dict(row)
    result = analyze_deal_intent(app_data, signals)
    
    # Обновляем или создаём запись
    upsert_query = text("""
        INSERT INTO deal_intent_game (
            app_id, steam_name, steam_url, developer_name, publisher_name,
            release_date, stage, has_demo, price_eur, tags,
            intent_score, quality_score, intent_reasons, quality_reasons, updated_at
        )
        VALUES (
            :app_id, :steam_name, :steam_url, :developer_name, :publisher_name,
            :release_date, :stage, :has_demo, :price_eur, :tags,
            :intent_score, :quality_score, :intent_reasons, :quality_reasons, now()
        )
        ON CONFLICT (app_id) DO UPDATE SET
            steam_name = EXCLUDED.steam_name,
            steam_url = EXCLUDED.steam_url,
            developer_name = EXCLUDED.developer_name,
            publisher_name = EXCLUDED.publisher_name,
            release_date = EXCLUDED.release_date,
            stage = EXCLUDED.stage,
            has_demo = EXCLUDED.has_demo,
            price_eur = EXCLUDED.price_eur,
            tags = EXCLUDED.tags,
            intent_score = EXCLUDED.intent_score,
            quality_score = EXCLUDED.quality_score,
            intent_reasons = EXCLUDED.intent_reasons,
            quality_reasons = EXCLUDED.quality_reasons,
            updated_at = now()
    """)
    
    db.execute(
        upsert_query,
        {
            "app_id": app_id,
            "steam_name": app_data.get("steam_name"),
            "steam_url": app_data.get("steam_url"),
            "developer_name": app_data.get("developer_name"),
            "publisher_name": app_data.get("publisher_name"),
            "release_date": app_data.get("release_date"),
            "stage": app_data.get("stage"),
            "has_demo": app_data.get("has_demo", False),
            "price_eur": app_data.get("price_eur"),
            "tags": app_data.get("tags") or {},
            "intent_score": result["intent_score"],
            "quality_score": result["quality_score"],
            "intent_reasons": result["intent_reasons"],
            "quality_reasons": result["quality_reasons"]
        }
    )
    
    db.commit()
