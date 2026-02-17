"""
Translation Service for Intel
Ensures all content is translated to Russian before publication.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def detect_language(text: str) -> str:
    """
    Simple language detection (heuristic).
    
    Args:
        text: Text to analyze
    
    Returns:
        Language code: 'ru', 'en', or 'other'
    """
    if not text:
        return 'other'
    
    # Simple heuristic: check for Cyrillic characters
    cyrillic_count = sum(1 for char in text if '\u0400' <= char <= '\u04FF')
    total_chars = len([c for c in text if c.isalpha()])
    
    if total_chars > 0:
        cyrillic_ratio = cyrillic_count / total_chars
        if cyrillic_ratio > 0.3:  # More than 30% Cyrillic
            return 'ru'
        elif cyrillic_ratio < 0.1:  # Less than 10% Cyrillic
            return 'en'
    
    return 'other'


def translate_to_ru(text: str, source_lang: Optional[str] = None) -> str:
    """
    Translate text to Russian.
    
    Uses LLM if available, otherwise returns text as-is with warning.
    
    Args:
        text: Text to translate
        source_lang: Source language (optional, will detect if not provided)
    
    Returns:
        Translated text (Russian)
    """
    if not text:
        return ""
    
    # Detect language if not provided
    if not source_lang:
        source_lang = detect_language(text)
    
    # If already Russian, return as-is
    if source_lang == 'ru':
        return text
    
    # Try to use LLM for translation
    try:
        from apps.worker.llm.client import LLMClient
        from apps.intel.policy.policy_brief import get_policy_brief_for_llm
        
        client = LLMClient()
        policy_brief = get_policy_brief_for_llm()
        
        prompt = f"""Ты профессиональный переводчик. Переведи следующий текст на русский язык.

Правила перевода:
- Сохраняй технические термины (Steam, appid, etc.)
- Сохраняй названия игр и компаний
- Используй деловой стиль
- Не добавляй информацию, которой нет в оригинале
- Если данных недостаточно, пиши "нет данных"

Текст для перевода:
{text}

Переведи только текст, без дополнительных комментариев:"""
        
        response = client.generate(
            prompt=prompt,
            system_prompt=policy_brief,
            model="claude-3-5-haiku-20241022",
            max_tokens=2000
        )
        
        if response and response.strip():
            logger.info(f"Translated text from {source_lang} to ru (length: {len(text)} -> {len(response)})")
            return response.strip()
        else:
            logger.warning(f"LLM translation returned empty, using original text")
            return text
            
    except Exception as e:
        logger.warning(f"Failed to translate via LLM: {e}, using original text")
        return text


def message_is_russian(text: str) -> bool:
    """
    Check if message is in Russian.
    
    Args:
        text: Text to check
    
    Returns:
        True if text appears to be in Russian
    """
    if not text:
        return False
    
    detected = detect_language(text)
    return detected == 'ru'
