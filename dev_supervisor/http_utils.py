"""
HTTP utilities for Dev Supervisor
Provides Python-based HTTP client (no curl dependency)
"""
import logging
from typing import Optional, Dict, Any
import httpx

logger = logging.getLogger(__name__)


def http_get(url: str, timeout: int = 10) -> Dict[str, Any]:
    """
    Make HTTP GET request using httpx (no curl dependency).
    Returns: {"status_code": int, "json": dict, "text": str, "error": str or None}
    """
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(url)
            result = {
                "status_code": response.status_code,
                "text": response.text,
                "error": None
            }
            
            # Try to parse JSON
            try:
                result["json"] = response.json()
            except:
                result["json"] = None
            
            return result
    except httpx.TimeoutException as e:
        return {
            "status_code": 0,
            "text": "",
            "json": None,
            "error": f"Timeout after {timeout}s: {str(e)}"
        }
    except httpx.HTTPError as e:
        return {
            "status_code": 0,
            "text": "",
            "json": None,
            "error": f"HTTP error: {str(e)}"
        }
    except Exception as e:
        return {
            "status_code": 0,
            "text": "",
            "json": None,
            "error": f"Unexpected error: {str(e)}"
        }


def check_intel_health(base_url: str = "http://localhost:8000") -> Dict[str, Any]:
    """
    Check Intel health endpoint.
    Returns: {"ok": bool, "policy_loaded": bool, "policy_version": str or None, "error": str or None}
    """
    url = f"{base_url}/intel/health"
    
    result = http_get(url, timeout=5)
    
    if result["error"]:
        return {
            "ok": False,
            "policy_loaded": False,
            "policy_version": None,
            "error": result["error"]
        }
    
    if result["status_code"] != 200:
        return {
            "ok": False,
            "policy_loaded": False,
            "policy_version": None,
            "error": f"HTTP {result['status_code']}"
        }
    
    json_data = result.get("json")
    if not json_data:
        return {
            "ok": False,
            "policy_loaded": False,
            "policy_version": None,
            "error": "Response is not JSON"
        }
    
    return {
        "ok": json_data.get("enabled", False),
        "policy_loaded": json_data.get("policy_loaded", False),
        "policy_version": json_data.get("policy_version"),
        "policy_hash": json_data.get("policy_hash"),
        "error": None
    }
