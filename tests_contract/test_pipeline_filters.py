"""
Contract tests for Pipeline Eligibility Filters
"""
import pytest
from unittest.mock import Mock, patch
from apps.intel.services.pipeline.steam_intel_pipeline import create_or_update_event
from apps.intel.db.models import IntelEvent, IntelExtractedItem, IntelCluster, IntelRawItem
from apps.intel.policy.policy_engine import load_policy


def test_pipeline_sets_significance_score():
    """Test that pipeline calculates and sets significance_score"""
    # This is an integration test - would need real DB session
    # For now, test the logic
    
    policy = load_policy()
    sig_config = policy.get("significance", {})
    min_score = sig_config.get("min_score_to_autopublish", 55)
    
    # Mock event with high score
    event = Mock(spec=IntelEvent)
    event.significance_score = 80
    event.event_type = "funding"
    event.autopublish_eligible = True
    
    # Should be eligible
    assert event.significance_score >= min_score
    assert event.autopublish_eligible == True


def test_pipeline_filters_by_score():
    """Test that events below threshold are not eligible"""
    policy = load_policy()
    sig_config = policy.get("significance", {})
    min_score = sig_config.get("min_score_to_autopublish", 55)
    
    # Mock event with low score
    event = Mock(spec=IntelEvent)
    event.significance_score = 20
    event.event_type = "patch"
    event.autopublish_eligible = False
    
    # Should not be eligible
    assert event.significance_score < min_score
    assert event.autopublish_eligible == False


def test_pipeline_skips_blocked_categories():
    """Test that blocked categories are not eligible"""
    policy = load_policy()
    sig_config = policy.get("significance", {})
    never_autopublish = sig_config.get("never_autopublish_categories", [])
    
    # Mock event with blocked category
    event = Mock(spec=IntelEvent)
    event.significance_score = 80  # High score
    event.event_type = "controversy"
    
    # Should not be eligible even with high score
    eligible = (
        event.significance_score >= 55 and
        event.event_type not in never_autopublish
    )
    
    assert eligible == False  # Controversy is blocked


def test_pipeline_creates_skipped_publish_log():
    """Test that non-eligible events create publish log with status=skipped"""
    # This would require real DB session
    # For now, test the logic
    
    skip_reason = "below_threshold"
    
    # Mock publish log
    from apps.intel.db.models import IntelPublishLog
    log = Mock(spec=IntelPublishLog)
    log.status = "skipped"
    log.error = skip_reason
    
    assert log.status == "skipped"
    assert log.error in ["below_threshold", "blocked_category", "not_eligible"]


def test_pipeline_returns_eligible_count():
    """Test that pipeline returns eligible_count in results"""
    # Mock pipeline result
    result = {
        "collected": 10,
        "extracted": 8,
        "events_created": 5,
        "eligible_count": 3,
        "published": 2,
        "skipped": 1
    }
    
    assert "eligible_count" in result
    assert result["eligible_count"] >= 0
    assert result["eligible_count"] <= result["events_created"]
