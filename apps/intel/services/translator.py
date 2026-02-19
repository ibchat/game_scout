"""
Translation Service for Intel
Ensures all content is translated to Russian before publication.
Uses free translation service (LibreTranslate) by default.
"""
import os
import logging
from typing import Optional, Tuple, Dict

logger = logging.getLogger(__name__)

# Try to use free translation first, fallback to LLM if needed
try:
    from apps.intel.services.translation.free_translate import (
        translate_to_ru as free_translate_to_ru,
        detect_language as free_detect_language,
        check_translation_service,
        TranslationError as FreeTranslationError
    )
    FREE_TRANSLATION_AVAILABLE = True
except ImportError:
    FREE_TRANSLATION_AVAILABLE = False
    logger.warning("Free translation module not available, will use LLM fallback")


def detect_language(text: str) -> str:
    """
    Simple language detection (heuristic).
    Delegates to free translation service if available.
    """
    if FREE_TRANSLATION_AVAILABLE:
        return free_detect_language(text)
    
    # Fallback heuristic
    if not text:
        return 'other'
    
    cyrillic_count = sum(1 for char in text if '\u0400' <= char <= '\u04FF')
    total_chars = len([c for c in text if c.isalpha()])
    
    if total_chars > 0:
        cyrillic_ratio = cyrillic_count / total_chars
        if cyrillic_ratio > 0.3:
            return 'ru'
        elif cyrillic_ratio < 0.1:
            return 'en'
    
    return 'other'


def translate_to_ru(text: str, source_lang: Optional[str] = None) -> str:
    """
    Translate text to Russian using free translation service (LibreTranslate).
    Falls back to LLM if free service unavailable.
    
    STRICT RULE: If translation unavailable → raises TranslationError
    This ensures we never publish non-Russian content.
    
    Args:
        text: Text to translate
        source_lang: Source language (optional, will detect if not provided)
    
    Returns:
        Translated text (Russian)
    
    Raises:
        TranslationError: If translation service not available or fails
    """
    if not text:
        return ""
    
    # Detect language if not provided
    if not source_lang:
        source_lang = detect_language(text)
    
    # If already Russian, return as-is
    if source_lang == 'ru':
        return text
    
    # Try free translation first (LibreTranslate)
    if FREE_TRANSLATION_AVAILABLE:
        try:
            translated, meta = free_translate_to_ru(text, source_lang)
            logger.info(f"Free translation: {source_lang}→ru via {meta.get('provider')} ({meta.get('elapsed_ms', 0)}ms)")
            return translated
        except FreeTranslationError as e:
            logger.warning(f"Free translation failed: {e}, falling back to LLM")
            # Fall through to LLM fallback
    
    # Fallback to LLM if free translation unavailable or failed
    from apps.worker.llm.client import get_llm_client
    
    llm_client = get_llm_client()
    if not llm_client:
        provider = os.getenv("TRANSLATION_PROVIDER", "libretranslate").lower()
        if provider == "libretranslate":
            error_msg = "Translation service not available (LibreTranslate unreachable and LLM not configured)"
        else:
            provider = os.getenv("LLM_PROVIDER", "anthropic").lower()
            if provider == "openai":
                error_msg = "Translation service not configured (OPENAI_API_KEY not set)"
            else:
                error_msg = "Translation service not configured (ANTHROPIC_API_KEY not set)"
        logger.error(error_msg)
        raise TranslationError(error_msg)
    
    # Prepare translation prompt
    prompt = f"""Ты профессиональный переводчик. Переведи следующий текст на русский язык.

Правила перевода:
- Сохраняй технические термины (Steam, appid, etc.)
- Сохраняй названия игр и компаний
- Используй деловой стиль, без эмоций
- Не добавляй информацию, которой нет в оригинале
- Если данных недостаточно, пиши "нет данных"
- Переводи только факты, без комментариев

Текст для перевода:
{text[:2000]}

Переведи только текст, без дополнительных комментариев:"""
    
    try:
        response = llm_client.generate(
            prompt=prompt,
            max_tokens=2000,
            temperature=0.2  # Low temperature for consistent translation
        )
        
        if response and response.strip():
            translated = response.strip()
            logger.info(f"LLM translation: {source_lang}→ru (length: {len(text)} → {len(translated)})")
            return translated
        else:
            error_msg = "LLM translation returned empty response"
            logger.error(error_msg)
            raise TranslationError(error_msg)
            
    except Exception as e:
        error_msg = f"Translation failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise TranslationError(error_msg)


class TranslationError(Exception):
    """Raised when translation service is unavailable or fails."""
    pass


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
