"""
Contract tests for policy engine
"""
import pytest
from pathlib import Path
from apps.intel.policy.policy_engine import load_policy, validate_source_url, get_policy_hash


def test_policy_file_exists():
    """Test that intel_policy.yaml exists"""
    policy_path = Path("apps/intel/policy/intel_policy.yaml")
    assert policy_path.exists(), "intel_policy.yaml not found"


def test_policy_can_be_loaded():
    """Test that policy can be loaded without errors"""
    policy = load_policy()
    assert policy is not None, "Policy should not be None"
    assert isinstance(policy, dict), "Policy should be a dictionary"


def test_policy_has_version():
    """Test that policy has version field"""
    policy = load_policy()
    assert "version" in policy, "Policy should have 'version' field"


def test_validate_source_url_returns_tuple():
    """Test that validate_source_url returns (decision, reason) tuple"""
    result = validate_source_url("https://store.steampowered.com")
    assert isinstance(result, tuple), "validate_source_url should return tuple"
    assert len(result) == 2, "validate_source_url should return (decision, reason)"


def test_validate_source_url_decision_values():
    """Test that validate_source_url returns valid decision values"""
    result = validate_source_url("https://store.steampowered.com")
    decision, reason = result
    assert decision in ["allow", "deny"], f"Decision should be 'allow' or 'deny', got '{decision}'"
    assert isinstance(reason, str), "Reason should be a string"


def test_get_policy_hash_returns_string():
    """Test that get_policy_hash returns a string or None"""
    hash_value = get_policy_hash()
    assert hash_value is None or isinstance(hash_value, str), "Policy hash should be string or None"
