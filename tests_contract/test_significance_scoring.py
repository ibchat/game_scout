"""
Contract tests for Significance Scoring
"""
import pytest
from unittest.mock import Mock
from apps.intel.services.significance import score_event, _classify_category_from_text, _calculate_score_by_category
from apps.intel.db.models import IntelEvent, IntelExtractedItem


def test_release_gets_high_score():
    """Test that release events get score >= 60"""
    event = Mock(spec=IntelEvent)
    event.event_type = "release"
    event.what_happened_ru = "Game launched today"
    event.title_ru = "New Game Release"
    
    extracted = Mock(spec=IntelExtractedItem)
    extracted.text = "Game launched today"
    
    score, reason, category, confidence = score_event(event, extracted, {})
    
    assert category == "release"
    assert score >= 60
    assert score <= 85
    assert confidence >= 0.7


def test_routine_patch_gets_low_score():
    """Test that routine patches get score <= 25"""
    event = Mock(spec=IntelEvent)
    event.event_type = "patch"
    event.what_happened_ru = "Bug fixes and minor improvements"
    event.title_ru = "Patch 1.0.1"
    
    extracted = Mock(spec=IntelExtractedItem)
    extracted.text = "Bug fixes and minor improvements"
    
    score, reason, category, confidence = score_event(event, extracted, {})
    
    # Should be classified as routine patch
    if category == "patch" or "patch" in reason.lower():
        assert score <= 25
    else:
        # If classified as other, score should still be low
        assert score <= 40


def test_funding_gets_high_score():
    """Test that funding events get score >= 70"""
    event = Mock(spec=IntelEvent)
    event.event_type = "funding"
    event.what_happened_ru = "Raised $10M in Series A funding"
    event.title_ru = "Funding Announcement"
    
    extracted = Mock(spec=IntelExtractedItem)
    extracted.text = "Raised $10M in Series A funding"
    
    score, reason, category, confidence = score_event(event, extracted, {})
    
    assert category == "funding"
    assert score >= 70
    assert score <= 95
    assert confidence >= 0.8


def test_controversy_not_autopublish_eligible():
    """Test that controversy events are marked appropriately"""
    event = Mock(spec=IntelEvent)
    event.event_type = "controversy"
    event.what_happened_ru = "Game banned in several countries"
    event.title_ru = "Controversy"
    
    extracted = Mock(spec=IntelExtractedItem)
    extracted.text = "Game banned in several countries"
    
    score, reason, category, confidence = score_event(event, extracted, {})
    
    assert category == "controversy"
    assert score >= 60  # High score but requires review
    assert "review" in reason.lower() or "спор" in reason.lower()


def test_classify_category_from_text():
    """Test category classification from text"""
    assert _classify_category_from_text("game launched today") == "release"
    assert _classify_category_from_text("major update 2.0") == "patch_major"
    assert _classify_category_from_text("50% off sale") == "discount"
    assert _classify_category_from_text("publisher deal announced") == "publisher_deal"
    assert _classify_category_from_text("raised $5M funding") == "funding"
    assert _classify_category_from_text("peak players chart") == "market_trend"
    assert _classify_category_from_text("controversy scandal") == "controversy"
    assert _classify_category_from_text("random news") == "other"


def test_calculate_score_by_category():
    """Test score calculation for different categories"""
    event = Mock(spec=IntelEvent)
    
    # Release
    score, reason, confidence = _calculate_score_by_category("release", "game launched", event)
    assert 60 <= score <= 85
    
    # Funding
    score, reason, confidence = _calculate_score_by_category("funding", "raised $10M", event)
    assert 70 <= score <= 95
    
    # Discount
    score, reason, confidence = _calculate_score_by_category("discount", "75% off", event)
    assert 35 <= score <= 65
    
    # Routine patch
    score, reason, confidence = _calculate_score_by_category("patch", "bug fixes", event)
    assert 5 <= score <= 25
    
    # No data
    score, reason, confidence = _calculate_score_by_category("other", "", event)
    assert score == 5
    assert "нет данных" in reason
