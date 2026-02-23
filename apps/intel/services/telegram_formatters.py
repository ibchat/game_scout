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
    title = brief.get("title", "").strip() if brief.get("title") else ""
    executive_summary = brief.get("executive_summary", "").strip() if brief.get("executive_summary") else ""
    what_happened = brief.get("what_happened", "").strip() if brief.get("what_happened") else ""
    why_it_matters = brief.get("why_it_matters", "").strip() if brief.get("why_it_matters") else ""
    key_points = brief.get("key_points", [])
    insight_line = brief.get("insight_line", "").strip() if brief.get("insight_line") else ""
    source_url = brief.get("source_url", "").strip() if brief.get("source_url") else ""
    
    # Fallback to event fields if brief is incomplete
    if not title and hasattr(event, 'title_ru'):
        title = (event.title_ru or "").strip()
    if not what_happened and hasattr(event, 'what_happened_ru'):
        what_happened = (event.what_happened_ru or "").strip()
    if not why_it_matters and hasattr(event, 'why_it_matters_ru'):
        why_it_matters = (event.why_it_matters_ru or "").strip()
    if not source_url and hasattr(event, 'sources') and event.sources:
        if isinstance(event.sources, list) and event.sources:
            source_url = str(event.sources[0]).strip()
        else:
            source_url = str(event.sources).strip()
    
    # Clean up empty or meaningless fields
    if title in ["нет данных", "Нет данных", "N/A", ""]:
        title = "Новость Steam"
    if what_happened in ["нет данных", "Нет данных", "N/A", ""]:
        what_happened = ""
    if why_it_matters in ["нет данных", "Нет данных", "N/A", ""]:
        why_it_matters = ""
    if executive_summary in ["нет данных", "Нет данных", "N/A", ""]:
        executive_summary = ""
    
    # Filter out empty key points
    key_points = [kp.strip() for kp in key_points if kp and kp.strip() and kp.strip() not in ["нет данных", "Нет данных", "N/A"]]
    
    # Get score
    score = event.significance_score if hasattr(event, 'significance_score') else 0
    
    # Build message parts - PROFESSIONAL EDITORIAL FORMAT
    message_parts = []
    
    # Clean and normalize title - remove duplicates, fix grammar
    if not title or len(title) < 3:
        title = "Новость Steam"
    
    # Remove duplicate words/phrases from title
    import re
    title_words = title.split()
    title_clean = []
    prev_word = ""
    for word in title_words:
        if word.lower() != prev_word.lower():
            title_clean.append(word)
            prev_word = word
    title = " ".join(title_clean)
    
    # Title line - NO EMOJI, NO BRACKETS, clean title only
    message_parts.append(title)
    message_parts.append("")  # Empty line after title
    
    # Main content - use what_happened or executive_summary (whichever is better)
    # Remove HTML first and clean "нет данных"
    what_happened_clean = ""
    if what_happened and what_happened not in ["нет данных", "Нет данных", "N/A", ""]:
        what_happened_clean = re.sub(r'<[^>]+>', '', what_happened).strip()
    
    executive_summary_clean = ""
    if executive_summary and executive_summary not in ["нет данных", "Нет данных", "N/A", ""]:
        executive_summary_clean = re.sub(r'<[^>]+>', '', executive_summary).strip()
    
    main_content = ""
    main_words = set()
    title_words_set = set(re.sub(r'[^\w\s]', '', title.lower()).split())
    
    # Prefer what_happened if it's meaningful and not duplicate
    if what_happened_clean and len(what_happened_clean) > 20:
        # Check if what_happened is not just a duplicate of title
        what_words_set = set(re.sub(r'[^\w\s]', '', what_happened_clean.lower()).split())
        overlap = len(title_words_set & what_words_set) / max(len(title_words_set), 1) if title_words_set else 0
        if overlap < 0.75:  # Less than 75% overlap (more lenient)
            main_content = what_happened_clean
            main_words = what_words_set
        elif executive_summary_clean and len(executive_summary_clean) > 20:
            # Fallback to executive_summary if what_happened is too similar to title
            main_content = executive_summary_clean
            main_words = set(re.sub(r'[^\w\s]', '', executive_summary_clean.lower()).split())
    elif executive_summary_clean and len(executive_summary_clean) > 20:
        # Use executive_summary if what_happened is not available
        main_content = executive_summary_clean
        main_words = set(re.sub(r'[^\w\s]', '', executive_summary_clean.lower()).split())
    
    # Clean main content - remove duplicates, fix grammar, remove HTML entities
    if main_content:
        # Remove HTML entities
        main_content = main_content.replace('&nbsp;', ' ')
        main_content = main_content.replace('&amp;', '&')
        main_content = main_content.replace('&lt;', '<')
        main_content = main_content.replace('&gt;', '>')
        main_content = main_content.replace('&quot;', '"')
        
        # Remove duplicate sentences
        sentences = re.split(r'[.!?]\s+', main_content)
        seen = set()
        unique_sentences = []
        for sent in sentences:
            sent_clean = sent.strip()
            if sent_clean:
                sent_normalized = re.sub(r'[^\w\s]', '', sent_clean.lower())
                sent_normalized = re.sub(r'\s+', ' ', sent_normalized).strip()
                if sent_normalized and sent_normalized not in seen:
                    unique_sentences.append(sent_clean)
                    seen.add(sent_normalized)
        
        if unique_sentences:
            main_content = ". ".join(unique_sentences)
            if main_content and not main_content.endswith(('.', '!', '?')):
                main_content += "."
            
            # Final cleanup - remove extra spaces
            main_content = re.sub(r'\s+', ' ', main_content).strip()
            
            message_parts.append(main_content)
            message_parts.append("")  # Empty line
    
    # Why it matters - only if adds value and not duplicate
    if why_it_matters and len(why_it_matters) > 20:
        why_it_matters_clean = re.sub(r'<[^>]+>', '', why_it_matters).strip()
        if why_it_matters_clean and len(why_it_matters_clean) > 20:
            # Check if it's not duplicate of main content
            why_words = set(re.sub(r'[^\w\s]', '', why_it_matters_clean.lower()).split())
            overlap = len(main_words & why_words) / max(len(why_words), 1) if main_words and why_words else 0
            if overlap < 0.6:  # Less than 60% overlap
                message_parts.append(why_it_matters_clean)
                message_parts.append("")  # Empty line
    
    # Key points - only meaningful, non-duplicate points, NO HTML
    meaningful_points = []
    seen_points = set()
    for point in key_points[:5]:  # Max 5 points
        if point and len(point) > 15:
            # Remove HTML tags from point
            point_clean = re.sub(r'<[^>]+>', '', point).strip()
            point_clean = re.sub(r'\s+', ' ', point_clean).strip()
            
            if len(point_clean) > 15:
                point_lower = point_clean.lower()
                # Check if not duplicate of title or main content
                if point_lower not in seen_points:
                    # Check overlap with existing content
                    point_words = set(re.sub(r'[^\w\s]', '', point_lower).split())
                    title_overlap = len(point_words & title_words_set) / max(len(point_words), 1) if title_words_set else 0
                    main_overlap = len(point_words & main_words) / max(len(point_words), 1) if main_content and main_words else 0
                    if title_overlap < 0.7 and main_overlap < 0.7:
                        meaningful_points.append(point_clean)
                        seen_points.add(point_lower)
    
    if meaningful_points:
        message_parts.append("Ключевые факты:")
        for point in meaningful_points:
            message_parts.append(f"• {point}")
        message_parts.append("")  # Empty line
    
    # Insight line - only for high-score events, only if meaningful
    if insight_line and len(insight_line) > 15 and score >= 70:
        message_parts.append(insight_line)
        message_parts.append("")  # Empty line
    
    # Source URL - always at the end, clean format
    if source_url and source_url.startswith(('http://', 'https://')):
        message_parts.append(source_url)
    else:
        # Try to get from event if not in brief
        if hasattr(event, 'sources') and event.sources:
            if isinstance(event.sources, list) and event.sources:
                source_url = str(event.sources[0]).strip()
                if source_url.startswith(('http://', 'https://')):
                    message_parts.append(source_url)
            else:
                source_url = str(event.sources).strip()
                if source_url.startswith(('http://', 'https://')):
                    message_parts.append(source_url)
    
    message = "\n".join(message_parts)
    
    # Truncate if too long (Telegram limit ~4096 chars, but we use 3500 from policy)
    max_chars = 3500
    if len(message) > max_chars:
        message = message[:max_chars - 3] + "..."
    
    return message
