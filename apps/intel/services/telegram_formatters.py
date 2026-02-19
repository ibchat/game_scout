"""
Telegram Message Formatters
Formats Intel events for Telegram with categories, importance badges, and country tags.
"""
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


# Event type -> Telegram tag and Russian label mapping
EVENT_TYPE_MAP = {
    "release": {
        "tag": "#Release",
        "label_ru": "Релиз"
    },
    "funding": {
        "tag": "#Funding",
        "label_ru": "Инвестиции"
    },
    "publisher_deal": {
        "tag": "#Deal",
        "label_ru": "Сделка"
    },
    "market_trend": {
        "tag": "#Trend",
        "label_ru": "Тренд"
    },
    "discount": {
        "tag": "#Discount",
        "label_ru": "Скидка"
    },
    "controversy": {
        "tag": "#Controversy",
        "label_ru": "Скандал"
    },
    "patch_major": {
        "tag": "#Update",
        "label_ru": "Обновление"
    },
    "early_access": {
        "tag": "#EarlyAccess",
        "label_ru": "Early Access"
    },
    "review_spike": {
        "tag": "#Reviews",
        "label_ru": "Отзывы"
    },
    "influencer_spike": {
        "tag": "#Influencer",
        "label_ru": "Инфлюенсеры"
    },
    "other": {
        "tag": "#Other",
        "label_ru": "Прочее"
    }
}


def map_event_type(event_type: str) -> Dict[str, str]:
    """
    Map event type to Telegram tag and Russian label.
    
    Args:
        event_type: Event type string
    
    Returns:
        Dict with tag and label_ru
    """
    return EVENT_TYPE_MAP.get(
        event_type,
        {
            "tag": f"#{event_type.capitalize()}",
            "label_ru": event_type
        }
    )


def importance_badge(score: int) -> Dict[str, Any]:
    """
    Get importance badge based on significance score.
    Updated mapping: 85-100: 🔥, 70-84: 🚀, 55-69: ✅, 40-54: 👀
    
    Args:
        score: Significance score (0-100)
    
    Returns:
        Dict with emoji, label, and score_range
    """
    if score >= 85:
        return {
            "emoji": "🔥",
            "label": "КРИТИЧНО",
            "score_range": "85-100"
        }
    elif score >= 70:
        return {
            "emoji": "🚀",
            "label": "ВАЖНО",
            "score_range": "70-84"
        }
    elif score >= 55:
        return {
            "emoji": "✅",
            "label": "СИГНАЛ",
            "score_range": "55-69"
        }
    elif score >= 40:
        return {
            "emoji": "👀",
            "label": "ИНФО",
            "score_range": "40-54"
        }
    else:
        # Should not be published (below threshold)
        return {
            "emoji": "",
            "label": "НИЗКИЙ",
            "score_range": f"<40 ({score})"
        }


def format_telegram_message(
    event: Any,
    brief: Dict[str, Any],
    country_info: Dict[str, Any],
    importance_info: Dict[str, Any]
) -> str:
    """
    Format Intel event as structured Telegram message.
    
    Format:
    {country_emoji} {country_code} | {category_tag}
    {importance_emoji} {importance_label} (Score: {score})
    
    {title}
    
    Кратко:
    {executive_summary}
    
    Что произошло:
    {what_happened}
    
    Почему это важно:
    {why_it_matters}
    
    Ключевые факты:
    {key_points}
    
    Источник:
    {source_url}
    
    Args:
        event: IntelEvent object
        brief: Business brief dict
        country_info: Country detection result
        importance_info: Importance badge result
    
    Returns:
        Formatted Telegram message string
    """
    # Get category info
    event_type = brief.get("signal_type") or (event.event_type if hasattr(event, 'event_type') else "other")
    category_info = map_event_type(event_type)
    
    # Get fields from brief
    title = brief.get("title", "")
    executive_summary = brief.get("executive_summary", "")
    what_happened = brief.get("what_happened", "")
    why_it_matters = brief.get("why_it_matters", "")
    key_points = brief.get("key_points", [])
    insight_line = brief.get("insight_line")  # Light humor for high-score events
    source_url = brief.get("source_url", "")
    
    # Fallback to event fields if brief is incomplete
    if not title and hasattr(event, 'title_ru'):
        title = event.title_ru or ""
    if not what_happened and hasattr(event, 'what_happened_ru'):
        what_happened = event.what_happened_ru or ""
    if not why_it_matters and hasattr(event, 'why_it_matters_ru'):
        why_it_matters = event.why_it_matters_ru or ""
    if not source_url and hasattr(event, 'sources') and event.sources:
        if isinstance(event.sources, list) and event.sources:
            source_url = event.sources[0]
        else:
            source_url = str(event.sources)
    
    # Get score
    score = event.significance_score if hasattr(event, 'significance_score') else 0
    
    # Build message parts
    message_parts = []
    
    # NEW FORMAT (G): First line with emoji, category, and title
    title_line = f"{importance_info['emoji']} [{category_info['label_ru']}] {title}"
    message_parts.append(title_line)
    
    # Short summary immediately after title (1 sentence)
    if executive_summary:
        message_parts.append(executive_summary)
        message_parts.append("")  # Empty line
    
    # Tags line: Country/Locale tags • Steam • SignalType
    tags_parts = [f"🌍 {country_info.get('country_name_ru', 'Global')}"]
    tags_parts.append("🧩 Steam")
    tags_parts.append(f"🧷 {category_info['label_ru']}")
    message_parts.append(" • ".join(tags_parts))
    message_parts.append("")  # Empty line
    
    # What happened
    if what_happened:
        message_parts.append("Что произошло:")
        message_parts.append(what_happened)
        message_parts.append("")  # Empty line
    
    # Why it matters
    if why_it_matters and why_it_matters != "нет данных":
        message_parts.append("Почему это важно:")
        message_parts.append(why_it_matters)
        message_parts.append("")  # Empty line
    
    # Key points
    if key_points:
        message_parts.append("Ключевые факты:")
        for point in key_points[:6]:  # Max 6 points
            message_parts.append(f"• {point}")
        message_parts.append("")  # Empty line
    
    # Insight line (light humor for high-score events)
    if insight_line:
        message_parts.append("Инсайт:")
        message_parts.append(insight_line)
        message_parts.append("")  # Empty line
    
    # Source URL
    if source_url:
        message_parts.append("Источник:")
        message_parts.append(source_url)
    else:
        message_parts.append("Источник: нет данных")
    
    message = "\n".join(message_parts)
    
    # Truncate if too long (Telegram limit ~4096 chars, but we use 3500 from policy)
    max_chars = 3500
    if len(message) > max_chars:
        message = message[:max_chars - 3] + "..."
    
    return message
