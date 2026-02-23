"""
Insight Generator
Generates light, smart humor lines for high-score events.
Controlled humor layer - only for score >= 70 and specific event types.
"""
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)


# Insight lines by event type
INSIGHT_LINES = {
    "release": [
        "Steam снова напоминает, кто здесь главный рынок.",
        "Ранний доступ продолжает доказывать свою эффективность.",
        "Ещё один релиз, который может изменить правила игры.",
        "Индустрия не стоит на месте — это видно по каждому релизу.",
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
    ],
    "discount": [
        "Скидки — это не просто снижение цены, это стратегия.",
        "Распродажи продолжают привлекать внимание геймеров.",
        "Снижение цены может открыть игру для новой аудитории.",
        "Скидки показывают, что разработчики думают о игроках.",
    ],
    "patch_major": [
        "Обновления — это признак активной поддержки игры.",
        "Разработчики продолжают улучшать свои проекты.",
        "Каждое крупное обновление — это новый шанс для игры.",
        "Поддержка после релиза — это то, что отличает хорошие игры.",
    ],
}


def generate_insight_line(
    event_type: str,
    score: int,
    title: Optional[str] = None,
    context: Optional[str] = None
) -> Optional[str]:
    """
    Generate light, smart humor line for ALL events.
    
    Rules:
    - For ALL events (no score threshold)
    - For all event types
    - 1 line, max 120 characters
    - No sarcasm
    - No toxicity
    - Light, smart humor
    - More neutral for low scores, more impactful for high scores
    
    Args:
        event_type: Event type
        score: Significance score
        title: Event title (for context, not used yet)
        context: Additional context (not used yet)
    
    Returns:
        Insight line or None if no lines available
    """
    # Get insight lines for this event type
    lines = INSIGHT_LINES.get(event_type, [])
    if not lines:
        return None
    
    # Select line based on score
    # Low scores (32-54): more neutral, informative (first 1-2 lines)
    # Medium scores (55-69): light humor (middle lines)
    # High scores (70+): more impactful, smart humor (all lines)
    
    if score >= 70:
        # High score: use full range of lines
        line_index = (score - 70) % len(lines)
    elif score >= 55:
        # Medium score: use middle lines (lighter humor)
        mid_start = len(lines) // 3
        mid_end = (len(lines) * 2) // 3
        mid_range = max(1, mid_end - mid_start)
        line_index = mid_start + ((score - 55) % mid_range)
    else:
        # Low score: use first lines (most neutral)
        # Use first 1-2 lines for very low scores
        num_neutral = min(2, len(lines))
        line_index = (score - 32) % num_neutral if num_neutral > 0 else 0
    
    # Ensure index is valid
    line_index = min(line_index, len(lines) - 1)
    
    insight = lines[line_index]
    
    # Ensure max length
    if len(insight) > 120:
        insight = insight[:117] + "..."
    
    return insight
