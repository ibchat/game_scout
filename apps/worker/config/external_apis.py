"""
External APIs Configuration
Единый источник конфигурации для внешних API ключей.
Single Source of Truth для всех API ключей в проекте.
"""
import os
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# ============================================================================
# YouTube API Key
# ============================================================================

def get_youtube_api_key() -> Optional[str]:
    """
    Получить YouTube API ключ из переменных окружения.
    Поддерживает алиасы: YOUTUBE_API_KEY -> GOOGLE_API_KEY (fallback)
    
    Returns:
        str | None: API ключ или None если не найден
    """
    # Приоритет 1: YOUTUBE_API_KEY
    key = os.getenv("YOUTUBE_API_KEY")
    if key and key.strip() and key != "your_youtube_api_key_here":
        return key.strip()
    
    # Fallback: GOOGLE_API_KEY (если используется общий ключ)
    key = os.getenv("GOOGLE_API_KEY")
    if key and key.strip() and key != "your_google_api_key_here":
        logger.debug("Using GOOGLE_API_KEY as fallback for YouTube API")
        return key.strip()
    
    return None


def get_youtube_mock_mode() -> bool:
    """
    Проверить, включён ли mock режим для YouTube API.
    
    Returns:
        bool: True если YOUTUBE_MOCK_MODE="true", иначе False
    """
    mock_mode = os.getenv("YOUTUBE_MOCK_MODE", "false").lower()
    return mock_mode == "true"


def assert_youtube_key() -> Tuple[bool, str]:
    """
    Проверить наличие и валидность YouTube API ключа.
    
    Returns:
        Tuple[bool, str]: (ok: bool, reason: str)
        - ok=True если ключ найден и валиден
        - ok=False если ключ отсутствует или невалиден
        - reason содержит понятное объяснение
    """
    key = get_youtube_api_key()
    
    if not key:
        return (False, "YouTube API ключ не найден (проверьте YOUTUBE_API_KEY или GOOGLE_API_KEY)")
    
    if len(key) < 20:
        return (False, f"YouTube API ключ слишком короткий ({len(key)} символов, ожидается >= 20)")
    
    # Маскируем ключ для логирования (первые 4 символа + ***)
    masked = f"{key[:4]}***" if len(key) > 4 else "***"
    return (True, f"YouTube API ключ найден ({masked})")


# Экспортируем константу для удобства импорта
YOUTUBE_API_KEY = get_youtube_api_key()
YOUTUBE_MOCK_MODE = get_youtube_mock_mode()
