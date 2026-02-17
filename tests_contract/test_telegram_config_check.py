"""
Contract tests for Telegram Config Check
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from apps.intel.services.publishers.telegram_publisher import TelegramPublisher
import httpx


@patch('apps.intel.services.publishers.telegram_publisher.httpx')
def test_telegram_check_calls_getme(mock_httpx):
    """Test that check_telegram_access calls getMe API"""
    mock_db = Mock()
    publisher = TelegramPublisher(mock_db)
    publisher.bot_token = "test_token"
    publisher.chat_id = "test_chat_id"
    publisher.base_url = "https://api.telegram.org/bottest_token"
    
    # Mock successful getMe response
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "ok": True,
        "result": {
            "id": 123456,
            "username": "test_bot",
            "first_name": "Test Bot"
        }
    }
    mock_response.raise_for_status = Mock()
    
    mock_client = MagicMock()
    mock_client.__enter__ = Mock(return_value=mock_client)
    mock_client.__exit__ = Mock(return_value=False)
    mock_client.get.return_value = mock_response
    mock_httpx.Client.return_value = mock_client
    
    # Mock successful getChat response
    mock_chat_response = MagicMock()
    mock_chat_response.json.return_value = {
        "ok": True,
        "result": {
            "id": -1001234567890,
            "title": "Test Channel",
            "type": "channel"
        }
    }
    mock_chat_response.raise_for_status = Mock()
    mock_client.post.return_value = mock_chat_response
    
    ok, error, details = publisher.check_telegram_access()
    
    assert ok == True
    assert error == ""
    assert "bot_username" in details
    assert "chat_title" in details
    
    # Verify getMe was called
    mock_client.get.assert_called_once()
    assert "getMe" in mock_client.get.call_args[0][0]


@patch('apps.intel.services.publishers.telegram_publisher.httpx')
def test_telegram_check_handles_invalid_token(mock_httpx):
    """Test that check_telegram_access handles invalid token"""
    mock_db = Mock()
    publisher = TelegramPublisher(mock_db)
    publisher.bot_token = "invalid_token"
    publisher.chat_id = "test_chat_id"
    publisher.base_url = "https://api.telegram.org/botinvalid_token"
    
    # Mock failed getMe response
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "ok": False,
        "description": "Unauthorized"
    }
    mock_response.raise_for_status = Mock()
    
    mock_client = MagicMock()
    mock_client.__enter__ = Mock(return_value=mock_client)
    mock_client.__exit__ = Mock(return_value=False)
    mock_client.get.return_value = mock_response
    mock_httpx.Client.return_value = mock_client
    
    ok, error, details = publisher.check_telegram_access()
    
    assert ok == False
    assert "invalid" in error.lower() or "unauthorized" in error.lower()
    # Token should not be exposed
    assert "invalid_token" not in error


@patch('apps.intel.services.publishers.telegram_publisher.httpx')
def test_telegram_check_handles_invalid_chat(mock_httpx):
    """Test that check_telegram_access handles invalid chat_id"""
    mock_db = Mock()
    publisher = TelegramPublisher(mock_db)
    publisher.bot_token = "test_token"
    publisher.chat_id = "invalid_chat_id"
    publisher.base_url = "https://api.telegram.org/bottest_token"
    
    # Mock successful getMe
    mock_me_response = MagicMock()
    mock_me_response.json.return_value = {
        "ok": True,
        "result": {"id": 123, "username": "test_bot"}
    }
    mock_me_response.raise_for_status = Mock()
    
    # Mock failed getChat
    mock_chat_response = MagicMock()
    mock_chat_response.json.return_value = {
        "ok": False,
        "description": "Chat not found"
    }
    mock_chat_response.raise_for_status = Mock()
    
    mock_client = MagicMock()
    mock_client.__enter__ = Mock(return_value=mock_client)
    mock_client.__exit__ = Mock(return_value=False)
    mock_client.get.return_value = mock_me_response
    mock_client.post.return_value = mock_chat_response
    mock_httpx.Client.return_value = mock_client
    
    ok, error, details = publisher.check_telegram_access()
    
    assert ok == False
    assert "chat" in error.lower() or "not found" in error.lower()


def test_telegram_check_handles_missing_config():
    """Test that check_telegram_access handles missing config"""
    mock_db = Mock()
    publisher = TelegramPublisher(mock_db)
    publisher.bot_token = None
    publisher.chat_id = None
    
    ok, error, details = publisher.check_telegram_access()
    
    assert ok == False
    assert "not configured" in error.lower()
