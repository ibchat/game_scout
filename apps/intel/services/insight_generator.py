"""
Insight Generator
Generates light, smart humor lines for events.
Uses context-aware selection and rotation for variety.
"""
import logging
import hashlib
import re
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)


# Insight lines by event type
INSIGHT_LINES = {
    "release": [
        "Steam снова напоминает, кто здесь главный рынок.",
        "Ранний доступ продолжает доказывать свою эффективность.",
        "Ещё один релиз, который может изменить правила игры.",
        "Индустрия не стоит на месте — это видно по каждому релизу.",
        "Новые игры — это всегда повод для обсуждения.",
        "Релиз на Steam — это уже событие само по себе.",
        "Каждый релиз добавляет что-то новое в экосистему.",
        "Steam продолжает быть главной площадкой для релизов.",
    ],
    "funding": [
        "Инвесторы по-прежнему верят, что следующий хит уже где-то рядом.",
        "Деньги продолжают течь в игровую индустрию — и это хорошо.",
        "Финансирование растёт, значит, рынок видит потенциал.",
        "Капитал ищет новые возможности — и находит их в играх.",
    ],
    "controversy": [
        "Интернет, как всегда, не смог пройти мимо.",
        "Скандалы в игровой индустрии — это уже почти традиция.",
        "Обсуждения разгораются, но индустрия продолжает работать.",
        "Шум в соцсетях не всегда отражает реальность рынка.",
    ],
    "market_trend": [
        "Рынок показывает, куда дует ветер.",
        "Тренды меняются, но некоторые вещи остаются постоянными.",
        "Индустрия адаптируется — это видно по каждому тренду.",
        "Изменения на рынке всегда интереснее, чем кажется на первый взгляд.",
    ],
    "publisher_deal": [
        "Сделки продолжают формировать ландшафт индустрии.",
        "Партнёрства — это двигатель роста в игровой индустрии.",
        "Ещё одна сделка, которая может изменить баланс сил.",
        "Индустрия движется через стратегические альянсы.",
    ],
    "other": [
        "Steam продолжает удивлять разнообразием новостей.",
        "Индустрия не перестаёт генерировать интересные события.",
        "Каждая новость — это часть большой картины рынка.",
        "Steam-экосистема показывает свою динамичность.",
        "Новости приходят, рынок реагирует — всё как обычно.",
        "Ещё один день в мире игровой индустрии.",
        "Steam остаётся центром игрового мира.",
        "Интересно, что будет дальше.",
        "Рынок игр не стоит на месте — это видно каждый день.",
        "Steam продолжает доказывать, что он главная платформа.",
        "Каждое событие добавляет новый штрих к картине индустрии.",
        "Игровая индустрия в движении — и это хорошо.",
    ],
    "discount": [
        "Скидки — это не просто снижение цены, это стратегия.",
        "Распродажи продолжают привлекать внимание геймеров.",
        "Снижение цены может открыть игру для новой аудитории.",
        "Скидки показывают, что разработчики думают о игроках.",
        "Распродажа — это шанс для игроков и для разработчиков.",
        "Скидки создают ажиотаж, и это работает.",
        "Снижение цены — это способ привлечь новых игроков.",
        "Распродажи стали частью игровой культуры.",
    ],
    "patch_major": [
        "Обновления — это признак активной поддержки игры.",
        "Разработчики продолжают улучшать свои проекты.",
        "Каждое крупное обновление — это новый шанс для игры.",
        "Поддержка после релиза — это то, что отличает хорошие игры.",
    ],
}


def _extract_keywords(text: str) -> List[str]:
    """
    Extract relevant keywords from text for context matching.
    
    Args:
        text: Text to analyze
    
    Returns:
        List of relevant keywords (lowercased)
    """
    if not text:
        return []
    
    # Common gaming/Steam keywords
    gaming_keywords = [
        "steam", "deck", "valve", "game", "игра", "релиз", "release",
        "скидка", "discount", "sale", "обновление", "update", "patch",
        "инвестиции", "funding", "сделка", "deal", "тренд", "trend",
        "рынок", "market", "индустрия", "industry"
    ]
    
    text_lower = text.lower()
    found_keywords = [kw for kw in gaming_keywords if kw in text_lower]
    
    # Also extract significant words (3+ chars, not common stop words)
    words = re.findall(r'\b\w{3,}\b', text_lower)
    stop_words = {"the", "and", "for", "are", "but", "not", "you", "all", "can", "her", "was", "one", "our", "out", "day", "get", "has", "him", "his", "how", "its", "may", "new", "now", "old", "see", "two", "who", "way", "use", "her", "she", "many", "some", "time", "very", "when", "come", "here", "just", "like", "long", "make", "much", "over", "such", "take", "than", "them", "well", "were", "what", "know", "want", "been", "good", "much", "some", "time", "very", "when", "come", "here", "just", "like", "long", "make", "much", "over", "such", "take", "than", "them", "well", "were", "what", "know", "want", "been", "good"}
    significant_words = [w for w in words if w not in stop_words and len(w) >= 3][:5]
    
    return found_keywords + significant_words


def _select_contextual_line(
    lines: List[str],
    keywords: List[str],
    event_type: str,
    score: int,
    title: Optional[str] = None
) -> int:
    """
    Select line index based on context and rotation.
    
    Uses:
    1. Keywords for contextual relevance
    2. Score for appropriateness level
    3. Hash-based rotation for variety (includes title hash for more diversity)
    
    Args:
        lines: Available insight lines
        keywords: Extracted keywords from title/context
        event_type: Event type
        score: Significance score
        title: Event title (for additional rotation seed)
    
    Returns:
        Line index
    """
    if not lines:
        return 0
    
    # Create rotation seed from keywords, event type, and title hash
    # This ensures different titles get different insights even with same keywords
    keywords_part = '_'.join(sorted(keywords[:3])) if keywords else "none"
    title_hash = hashlib.md5((title or "").encode()).hexdigest()[:4] if title else "0000"
    seed_str = f"{event_type}_{keywords_part}_{title_hash}"
    seed_hash = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)
    
    # Score-based filtering: which lines are appropriate
    if score >= 70:
        # High score: all lines available
        available_range = (0, len(lines))
    elif score >= 55:
        # Medium score: middle 60% of lines
        start = len(lines) // 5
        end = (len(lines) * 4) // 5
        available_range = (start, max(start + 1, end))
    else:
        # Low score: first 40% of lines (most neutral)
        end = max(1, (len(lines) * 2) // 5)
        available_range = (0, end)
    
    start_idx, end_idx = available_range
    available_lines = list(range(start_idx, end_idx))
    
    if not available_lines:
        available_lines = [0]
    
    # Use hash for rotation within available lines
    line_index = available_lines[seed_hash % len(available_lines)]
    
    return min(line_index, len(lines) - 1)


def generate_insight_line(
    event_type: str,
    score: int,
    title: Optional[str] = None,
    context: Optional[str] = None
) -> Optional[str]:
    """
    Generate light, smart humor line for ALL events.
    Uses context-aware selection and rotation for variety.
    
    Rules:
    - For ALL events (no score threshold)
    - For all event types
    - 1 line, max 120 characters
    - No sarcasm
    - No toxicity
    - Light, smart humor
    - Context-aware: uses keywords from title
    - Rotation: hash-based selection for variety
    
    Args:
        event_type: Event type
        score: Significance score
        title: Event title (used for context matching)
        context: Additional context (optional)
    
    Returns:
        Insight line or None if no lines available
    """
    # Get insight lines for this event type
    lines = INSIGHT_LINES.get(event_type, [])
    if not lines:
        return None
    
    # Extract keywords from title for context matching
    text_for_keywords = (title or "") + (" " + context if context else "")
    keywords = _extract_keywords(text_for_keywords)
    
    # Select line using context and rotation
    line_index = _select_contextual_line(lines, keywords, event_type, score, title)
    
    insight = lines[line_index]
    
    # Ensure max length
    if len(insight) > 120:
        insight = insight[:117] + "..."
    
    return insight
