"""
Contract tests for Intel health endpoint
"""
import pytest
import httpx
from dev_supervisor.http_utils import check_intel_health, http_get


def test_http_get_function_exists():
    """Test that http_get function exists and is callable"""
    assert callable(http_get), "http_get should be callable"


def test_check_intel_health_function_exists():
    """Test that check_intel_health function exists and is callable"""
    assert callable(check_intel_health), "check_intel_health should be callable"


def test_http_get_returns_dict():
    """Test that http_get returns a dictionary with expected keys"""
    # This test may fail if network is not available, which is OK
    result = http_get("https://httpbin.org/status/200", timeout=5)
    
    assert isinstance(result, dict), "http_get should return dict"
    assert "status_code" in result, "Result should have 'status_code' key"
    assert "text" in result, "Result should have 'text' key"
    assert "error" in result, "Result should have 'error' key"


def test_check_intel_health_returns_dict():
    """Test that check_intel_health returns a dictionary with expected keys"""
    # This test may fail if API is not running, which is OK for contract test
    result = check_intel_health()
    
    assert isinstance(result, dict), "check_intel_health should return dict"
    assert "ok" in result, "Result should have 'ok' key"
    assert "policy_loaded" in result, "Result should have 'policy_loaded' key"
    assert "policy_version" in result, "Result should have 'policy_version' key"
    assert "error" in result, "Result should have 'error' key"


@pytest.mark.skipif(True, reason="Requires running API container")
def test_intel_health_endpoint_accessible():
    """Test that Intel health endpoint is accessible (requires running API)"""
    result = check_intel_health()
    
    # If API is running, these should be True
    if not result["error"]:
        assert result["ok"] is not None, "Health check should return ok status"
        assert isinstance(result["policy_loaded"], bool), "policy_loaded should be bool"


@pytest.mark.skipif(True, reason="Requires running API container")
def test_intel_health_endpoint_has_policy_fields():
    """Test that Intel health endpoint returns policy_loaded and policy_version (requires running API)"""
    result = check_intel_health()
    
    # If API is running and Intel is enabled
    if not result["error"] and result["ok"]:
        assert isinstance(result["policy_loaded"], bool), "policy_loaded should be bool"
        # policy_version can be None or string
        assert result["policy_version"] is None or isinstance(result["policy_version"], str), \
            "policy_version should be None or string"
