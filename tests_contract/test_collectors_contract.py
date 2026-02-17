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


def test_collectors_can_be_instantiated():
    """Test that collectors can be instantiated without errors"""
    rss_collector = RSSCollector()
    assert rss_collector is not None
    
    steam_collector = SteamNewsCollector()
    assert steam_collector is not None
    
    reddit_collector = RedditRSSCollector()
    assert reddit_collector is not None


def test_collectors_inherit_from_base():
    """Test that collectors inherit from BaseIntelCollector"""
    assert issubclass(RSSCollector, BaseIntelCollector), "RSSCollector should inherit from BaseIntelCollector"
    assert issubclass(SteamNewsCollector, BaseIntelCollector), "SteamNewsCollector should inherit from BaseIntelCollector"
    assert issubclass(RedditRSSCollector, RSSCollector), "RedditRSSCollector should inherit from RSSCollector"
