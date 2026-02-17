"""
Contract tests for Intel collectors
"""
import pytest
from apps.intel.services.collectors.base_collector import BaseIntelCollector
from apps.intel.services.collectors.rss_collector import RSSCollector
from apps.intel.services.collectors.steam_news_collector import SteamNewsCollector
from apps.intel.services.collectors.reddit_rss_collector import RedditRSSCollector


def test_base_collector_has_required_methods():
    """Test that BaseIntelCollector has all required methods"""
    required_methods = ['validate_url', 'fetch_url', 'save_raw_item', 'collect']
    
    for method_name in required_methods:
        assert hasattr(BaseIntelCollector, method_name), f"BaseIntelCollector missing '{method_name}' method"
        assert callable(getattr(BaseIntelCollector, method_name)), f"BaseIntelCollector '{method_name}' is not callable"


def test_rss_collector_has_collect_method():
    """Test that RSSCollector has collect method"""
    assert hasattr(RSSCollector, 'collect'), "RSSCollector missing 'collect' method"
    assert callable(getattr(RSSCollector, 'collect')), "RSSCollector 'collect' is not callable"


def test_steam_news_collector_has_collect_method():
    """Test that SteamNewsCollector has collect method"""
    assert hasattr(SteamNewsCollector, 'collect'), "SteamNewsCollector missing 'collect' method"
    assert callable(getattr(SteamNewsCollector, 'collect')), "SteamNewsCollector 'collect' is not callable"


def test_reddit_rss_collector_has_collect_method():
    """Test that RedditRSSCollector has collect method"""
    assert hasattr(RedditRSSCollector, 'collect'), "RedditRSSCollector missing 'collect' method"
    assert callable(getattr(RedditRSSCollector, 'collect')), "RedditRSSCollector 'collect' is not callable"


def test_collectors_require_db_session():
    """Test that collectors require db session in __init__"""
    from sqlalchemy.orm import Session
    from unittest.mock import Mock
    
    # Mock db session
    mock_db = Mock(spec=Session)
    
    # Should be able to instantiate with db
    rss_collector = RSSCollector(db=mock_db)
    assert rss_collector is not None
    assert rss_collector.db == mock_db
    
    steam_collector = SteamNewsCollector(db=mock_db)
    assert steam_collector is not None
    
    reddit_collector = RedditRSSCollector(db=mock_db)
    assert reddit_collector is not None


def test_collectors_have_collect_source_method():
    """Test that collectors have collect_source method"""
    from sqlalchemy.orm import Session
    from unittest.mock import Mock
    
    mock_db = Mock(spec=Session)
    
    rss_collector = RSSCollector(db=mock_db)
    assert hasattr(rss_collector, 'collect_source'), "RSSCollector should have collect_source method"
    assert callable(getattr(rss_collector, 'collect_source')), "collect_source should be callable"


def test_collectors_inherit_from_base():
    """Test that collectors inherit from BaseIntelCollector"""
    assert issubclass(RSSCollector, BaseIntelCollector), "RSSCollector should inherit from BaseIntelCollector"
    assert issubclass(SteamNewsCollector, BaseIntelCollector), "SteamNewsCollector should inherit from BaseIntelCollector"
    assert issubclass(RedditRSSCollector, RSSCollector), "RedditRSSCollector should inherit from RSSCollector"
