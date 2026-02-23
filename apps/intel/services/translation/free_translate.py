"""
Free Translation Service using LibreTranslate
Falls back to heuristic detection if service unavailable.
"""
import os
import time
import logging
import httpx
from typing import Optional, Tuple, Dict
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)


class TranslationError(Exception):
    """Raised when translation service is unavailable or fails."""
    pass


def detect_language(text: str) -> str:
    """
    Simple language detection (heuristic).
    Improved: detects mixed English/Russian text and treats as English (needs translation).
    
    Args:
        text: Text to analyze
    
    Returns:
        Language code: 'ru', 'en', or 'other'
    """
    if not text:
        return 'other'
    
    # Simple heuristic: check for Cyrillic and Latin characters
    cyrillic_count = sum(1 for char in text if '\u0400' <= char <= '\u04FF')
    latin_count = sum(1 for char in text if ('\u0041' <= char <= '\u005A') or ('\u0061' <= char <= '\u007A'))
    total_chars = len([c for c in text if c.isalpha()])
    
    if total_chars > 0:
        cyrillic_ratio = cyrillic_count / total_chars
        latin_ratio = latin_count / total_chars
        
        # If significant Latin (English) content, treat as English (needs translation)
        # Even if there's some Cyrillic, if Latin > 20%, it's likely mixed and needs translation
        if latin_ratio > 0.2:  # More than 20% Latin = needs translation
            return 'en'
        elif cyrillic_ratio > 0.5:  # More than 50% Cyrillic = Russian
            return 'ru'
        elif cyrillic_ratio > 0.3:  # 30-50% Cyrillic = likely Russian
            return 'ru'
        elif latin_ratio > 0.1:  # 10-20% Latin = likely English
            return 'en'
    
    return 'other'


def _detect_language_libretranslate(text: str, base_url: str, api_key: Optional[str] = None) -> Optional[str]:
    """
    Detect language using LibreTranslate API.
    
    Returns:
        Language code or None if detection fails
    """
    try:
        url = f"{base_url}/detect"
        payload = {"q": text[:500]}  # Limit text length
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        
        response = httpx.post(url, json=payload, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        if data and len(data) > 0:
            detected = data[0].get("language", "").lower()
            confidence = data[0].get("confidence", 0)
            if confidence > 0.5:  # Only trust if confidence > 50%
                return detected
    except Exception as e:
        logger.debug(f"LibreTranslate language detection failed: {e}")
    
    return None


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError))
)
def _translate_libretranslate(
    text: str,
    source_lang: str,
    target_lang: str = "ru",
    base_url: str = "http://libretranslate:5000",
    api_key: Optional[str] = None
) -> Tuple[str, Dict]:
    """
    Translate text using LibreTranslate API.
    
    Args:
        text: Text to translate
        source_lang: Source language code
        target_lang: Target language code (default: ru)
        base_url: LibreTranslate base URL
        api_key: Optional API key
    
    Returns:
        Tuple of (translated_text, meta_dict)
    
    Raises:
        TranslationError: If translation fails
    """
    start_time = time.time()
    meta = {
        "provider": "libretranslate",
        "detected_lang": source_lang,
        "confidence": None,
        "elapsed_ms": None,
        "error": None
    }
    
    try:
        url = f"{base_url}/translate"
        payload = {
            "q": text,
            "source": source_lang,
            "target": target_lang,
            "format": "text"
        }
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        
        response = httpx.post(url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        elapsed_ms = int((time.time() - start_time) * 1000)
        meta["elapsed_ms"] = elapsed_ms
        
        if "translatedText" in data:
            translated = data["translatedText"]
            logger.info(f"LibreTranslate: {source_lang}→{target_lang} ({len(text)}→{len(translated)} chars, {elapsed_ms}ms)")
            return translated, meta
        else:
            error_msg = f"LibreTranslate returned unexpected format: {data}"
            meta["error"] = error_msg
            raise TranslationError(error_msg)
            
    except httpx.RequestError as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        meta["elapsed_ms"] = elapsed_ms
        error_msg = f"LibreTranslate request failed: {str(e)}"
        meta["error"] = error_msg
        logger.error(error_msg)
        raise TranslationError(error_msg) from e
    except httpx.HTTPStatusError as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        meta["elapsed_ms"] = elapsed_ms
        error_msg = f"LibreTranslate HTTP error {e.response.status_code}: {e.response.text}"
        meta["error"] = error_msg
        logger.error(error_msg)
        raise TranslationError(error_msg) from e
    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        meta["elapsed_ms"] = elapsed_ms
        error_msg = f"LibreTranslate unexpected error: {str(e)}"
        meta["error"] = error_msg
        logger.error(error_msg, exc_info=True)
        raise TranslationError(error_msg) from e


def translate_to_ru(text: str, source_lang: Optional[str] = None) -> Tuple[str, Dict]:
    """
    Translate text to Russian using free translation service.
    
    Args:
        text: Text to translate
        source_lang: Source language (optional, will detect if not provided)
    
    Returns:
        Tuple of (translated_text, meta_dict)
        meta contains: provider, detected_lang, confidence, elapsed_ms, error(optional)
    
    Raises:
        TranslationError: If translation service is unavailable or fails
    """
    if not text:
        return "", {"provider": "none", "detected_lang": None, "confidence": None, "elapsed_ms": 0}
    
    # Get configuration
    provider = os.getenv("TRANSLATION_PROVIDER", "libretranslate").lower()
    base_url = os.getenv("LIBRETRANSLATE_URL", "http://libretranslate:5000")
    api_key = os.getenv("LIBRETRANSLATE_API_KEY", "").strip() or None
    
    # Detect language if not provided
    if not source_lang:
        # Try LibreTranslate detection first if available
        if provider == "libretranslate":
            detected = _detect_language_libretranslate(text, base_url, api_key)
            if detected:
                source_lang = detected
            else:
                # Fallback to heuristic
                source_lang = detect_language(text)
        else:
            source_lang = detect_language(text)
    
    # If already Russian, return as-is
    if source_lang == 'ru':
        return text, {
            "provider": "none",
            "detected_lang": "ru",
            "confidence": 1.0,
            "elapsed_ms": 0
        }
    
    # Translate based on provider
    if provider == "libretranslate":
        try:
            return _translate_libretranslate(text, source_lang, "ru", base_url, api_key)
        except TranslationError as e:
            # If LibreTranslate fails, we cannot proceed (strict rule)
            logger.error(f"Translation failed: {e}")
            raise
    elif provider == "marian":
        # TODO: Implement MarianMT fallback
        # For now, raise error
        raise TranslationError("MarianMT provider not yet implemented")
    else:
        raise TranslationError(f"Unknown translation provider: {provider}")


def check_translation_service() -> Tuple[bool, Optional[str]]:
    """
    Check if translation service is available.
    
    Returns:
        Tuple of (is_available, error_message)
    """
    provider = os.getenv("TRANSLATION_PROVIDER", "libretranslate").lower()
    base_url = os.getenv("LIBRETRANSLATE_URL", "http://libretranslate:5000")
    
    if provider == "libretranslate":
        try:
            # Try to reach health endpoint or languages endpoint
            url = f"{base_url}/languages"
            response = httpx.get(url, timeout=5)
            response.raise_for_status()
            return True, None
        except Exception as e:
            return False, f"LibreTranslate unreachable: {str(e)}"
    else:
        return False, f"Unknown provider: {provider}"
