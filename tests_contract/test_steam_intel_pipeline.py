"""
Contract tests for Steam Intel Pipeline
"""
import pytest
from unittest.mock import Mock, patch
from apps.intel.services.business_brief_generator import classify_signal_type, detect_language
from apps.intel.services.pipeline.steam_intel_pipeline import extract_from_raw_item, create_or_update_event
from apps.intel.db.models import IntelRawItem, IntelExtractedItem, IntelEvent


def test_classify_signal_type():
    """Test rules-based signal classification"""
    assert classify_signal_type("Game launched today") == "release"
    assert classify_signal_type("Major update 2.0 released") == "patch_major"
    assert classify_signal_type("50% off sale") == "discount"
    assert classify_signal_type("Publisher deal announced") == "publisher_deal"
    assert classify_signal_type("Raised $5M funding") == "funding"
    assert classify_signal_type("Peak players chart") == "market_trend"
    assert classify_signal_type("Random news") == "other"


def test_detect_language():
    """Test language detection"""
    assert detect_language("Привет мир") == "ru"
    assert detect_language("Hello world") == "en"
    assert detect_language("Game released") == "en"
    assert detect_language("Игра выпущена") == "ru"


def test_no_duplicate_publish():
    """Test that duplicate publishes are prevented"""
    # This will be tested via integration test with actual DB
    # For now, just verify the logic exists
    from apps.intel.services.publishers.telegram_publisher import TelegramPublisher
    
    # Mock DB session
    mock_db = Mock()
    mock_db.query.return_value.filter.return_value.first.return_value = None  # No existing publish
    
    publisher = TelegramPublisher(mock_db)
    
    # Mock event
    mock_event = Mock()
    mock_event.id = "test-id"
    
    # Should not be duplicate
    is_duplicate = publisher._check_duplicate(mock_event)
    assert is_duplicate == False


def test_rate_limit():
    """Test rate limit enforcement"""
    from apps.intel.services.publishers.telegram_publisher import TelegramPublisher
    from datetime import datetime, timedelta
    
    mock_db = Mock()
    
    # Mock: 6 publishes in last hour (exceeds limit of 5)
    mock_query = Mock()
    mock_query.filter.return_value.count.return_value = 6
    mock_db.query.return_value = mock_query
    
    publisher = TelegramPublisher(mock_db)
    can_publish, error = publisher._check_rate_limits()
    
    assert can_publish == False
    assert "Rate limit" in error


def test_telegram_format_contains_source_url():
    """Test that Telegram message format includes source URL"""
    from apps.intel.services.publishers.telegram_publisher import TelegramPublisher
    
    mock_db = Mock()
    publisher = TelegramPublisher(mock_db)
    
    # Mock event with source
    mock_event = Mock()
    mock_event.title_ru = "Test Title"
    mock_event.what_happened_ru = "Test happened"
    mock_event.why_it_matters_ru = "Test matters"
    mock_event.sources = ["https://store.steampowered.com/news/123"]
    
    brief = {
        "title": "Test Title",
        "what_happened": "Test happened",
        "why_it_matters": "Test matters",
        "key_points": ["Point 1"],
        "source_url": "https://store.steampowered.com/news/123"
    }
    
    message = publisher._format_message(mock_event, brief)
    
    assert "Источник:" in message
    assert "https://store.steampowered.com" in message
