"""
Smoke tests for Intel orchestrator
"""
import pytest
from apps.intel.db.models import IntelSource, IntelRawItem, IntelEvent
from apps.intel.services.collectors.rss_collector import RSSCollector
from apps.intel.policy.policy_engine import load_policy


def test_intel_models_are_importable():
    """Test that Intel models can be imported"""
    assert IntelSource is not None
    assert IntelRawItem is not None
    assert IntelEvent is not None


def test_intel_source_has_required_fields():
    """Test that IntelSource has required fields"""
    required_fields = ['id', 'type', 'name', 'url', 'is_enabled']
    for field in required_fields:
        assert hasattr(IntelSource, field), f"IntelSource missing field: {field}"


def test_intel_raw_item_has_required_fields():
    """Test that IntelRawItem has required fields"""
    required_fields = ['id', 'source_id', 'url', 'title', 'fetched_at']
    for field in required_fields:
        assert hasattr(IntelRawItem, field), f"IntelRawItem missing field: {field}"


def test_collectors_can_be_instantiated():
    """Test that collectors can be instantiated"""
    from unittest.mock import Mock
    from sqlalchemy.orm import Session
    
    # Collectors require db session
    mock_db = Mock(spec=Session)
    collector = RSSCollector(db=mock_db)
    assert collector is not None
    assert hasattr(collector, 'collect')
    assert hasattr(collector, 'collect_source')
    assert hasattr(collector, 'db')


def test_policy_engine_loads():
    """Test that policy engine can load policy"""
    policy = load_policy()
    assert policy is not None
    assert isinstance(policy, dict)
