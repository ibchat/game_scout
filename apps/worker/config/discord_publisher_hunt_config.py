"""
Discord Publisher Hunt Configuration v1
Список Discord серверов и каналов для поиска проектов, ищущих издателя.
V1 ограничение: не более 20 серверов, не более 10 каналов на сервер.
"""
from typing import Dict, List

# ============================================================================
# DISCORD SERVERS & CHANNELS (V1)
# ============================================================================

DISCORD_SERVERS: Dict[str, Dict[str, any]] = {
    # Реальный Discord сервер Game Scout
    "1467902660610101441": {
        "name": "Game Scout",
        "channels": [],  # Пусто = сканируем все доступные текстовые каналы
        "channel_names": []  # Пусто = сканируем все доступные текстовые каналы
    }
}

# ============================================================================
# PUBLISHER-SEEKING PHRASES (обязательный словарь)
# ============================================================================

PUBLISHER_SEEKING_PHRASES: List[str] = [
    "looking for publisher",
    "seeking publisher",
    "need a publisher",
    "publisher wanted",
    "looking for publishing partner",
    "seeking publishing partner",
    "publisher pitch",
    "open to publishers",
    "looking for funding partner",
    "publisher discussions"
]

# ============================================================================
# NEGATIVE PHRASES (жёсткое исключение)
# ============================================================================

NEGATIVE_PHRASES: List[str] = [
    "already have a publisher",
    "signed with publisher",
    "published by",
    "our publisher is",
    "working with publisher"
]

# ============================================================================
# CHANNEL TYPE WEIGHTS (для confidence)
# ============================================================================

CHANNEL_TYPE_WEIGHTS: Dict[str, float] = {
    "publishing": 1.0,  # Высокий приоритет
    "funding": 0.9,
    "collaboration": 0.8,
    "showcase": 0.6,
    "feedback": 0.5
}

# ============================================================================
# MESSAGE AUTHOR ROLE WEIGHTS (для confidence)
# ============================================================================

AUTHOR_ROLE_WEIGHTS: Dict[str, float] = {
    "dev": 1.0,  # Разработчик
    "mod": 0.8,  # Модератор
    "member": 0.6  # Обычный участник
}
