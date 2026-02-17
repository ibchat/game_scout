"""
Contract tests for Steam relevance filter
"""
import pytest
from apps.intel.services.steam_mention_detector import detect_steam_relevance, extract_steam_appid


def test_detect_steam_relevance_with_steam_keyword():
    """Test detection with 'Steam' keyword"""
    text = "New game released on Steam"
    is_relevant, reason = detect_steam_relevance(text)
    assert is_relevant is True
    assert reason is not None
    assert "steam" in reason.lower()


def test_detect_steam_relevance_with_store_url():
    """Test detection with Steam store URL"""
    text = "Check out https://store.steampowered.com/app/123456/GameName"
    is_relevant, reason = detect_steam_relevance(text)
    assert is_relevant is True
    assert "url" in reason.lower() or "appid" in reason.lower()


def test_detect_steam_relevance_with_appid():
    """Test detection with appid pattern"""
    text = "Game appid: 123456 is now available"
    is_relevant, reason = detect_steam_relevance(text)
    assert is_relevant is True


def test_detect_steam_relevance_not_relevant():
    """Test detection with non-Steam content"""
    text = "This is a general gaming news article"
    is_relevant, reason = detect_steam_relevance(text)
    assert is_relevant is False
    assert reason is None


def test_extract_steam_appid_from_url():
    """Test appid extraction from Steam URL"""
    text = "https://store.steampowered.com/app/123456/GameName"
    appid = extract_steam_appid(text)
    assert appid == 123456


def test_extract_steam_appid_from_text():
    """Test appid extraction from text pattern"""
    text = "Steam appid: 789012"
    appid = extract_steam_appid(text)
    assert appid == 789012


def test_extract_steam_appid_not_found():
    """Test appid extraction when not present"""
    text = "General gaming news"
    appid = extract_steam_appid(text)
    assert appid is None
