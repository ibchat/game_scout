"""
Contract tests for translation to Russian
"""
import pytest
from apps.intel.services.translator import translate_to_ru, message_is_russian, detect_language


def test_detect_language_russian():
    """Test Russian language detection"""
    text = "Это русский текст"
    lang = detect_language(text)
    assert lang == "ru"


def test_detect_language_english():
    """Test English language detection"""
    text = "This is English text"
    lang = detect_language(text)
    assert lang == "en"


def test_message_is_russian_true():
    """Test Russian message check"""
    text = "Это сообщение на русском языке"
    assert message_is_russian(text) is True


def test_message_is_russian_false():
    """Test non-Russian message check"""
    text = "This is an English message"
    assert message_is_russian(text) is False


def test_translate_to_ru_already_russian():
    """Test translation when already Russian"""
    text = "Это уже русский текст"
    translated = translate_to_ru(text, "ru")
    assert translated == text  # Should return as-is


def test_translate_to_ru_english():
    """Test translation from English to Russian"""
    text = "New game released"
    translated = translate_to_ru(text, "en")
    # Should be translated (may use LLM, so just check it's not empty)
    assert translated is not None
    assert len(translated) > 0
