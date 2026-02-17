"""
Orchestrator Smoke Test - Basic smoke test for Intel orchestrator
"""
import sys
from pathlib import Path
from typing import List
from unittest.mock import Mock, patch

from dev_supervisor.config import config
from dev_supervisor.report import SupervisorResult, StageStatus
from dev_supervisor.http_utils import check_intel_health


def run_orchestrator_smoke() -> SupervisorResult:
    """
    Smoke test for Intel orchestrator:
    1. Check IntelSource model is accessible
    2. Check intel_raw_items table exists (via model)
    3. Check collectors can be instantiated
    No external network calls.
    """
    errors: List[str] = []
    warnings: List[str] = []
    
    # Check 1: IntelSource model is importable
    try:
        from apps.intel.db.models import IntelSource, IntelRawItem
    except ImportError as e:
        errors.append(f"Failed to import Intel models: {str(e)}")
        return SupervisorResult(
            stage="orchestrator_smoke",
            status=StageStatus.FAIL,
            errors=errors,
            warnings=warnings
        )
    except Exception as e:
        errors.append(f"Error importing Intel models: {str(e)}")
        return SupervisorResult(
            stage="orchestrator_smoke",
            status=StageStatus.FAIL,
            errors=errors,
            warnings=warnings
        )
    
    # Check 2: Models have correct structure
    try:
        # Check IntelSource has required fields
        source_fields = ['id', 'type', 'name', 'url', 'is_enabled']
        for field in source_fields:
            if not hasattr(IntelSource, field):
                errors.append(f"IntelSource missing field: {field}")
        
        # Check IntelRawItem has required fields
        raw_item_fields = ['id', 'source_id', 'url', 'title', 'fetched_at']
        for field in raw_item_fields:
            if not hasattr(IntelRawItem, field):
                errors.append(f"IntelRawItem missing field: {field}")
    except Exception as e:
        errors.append(f"Error checking model structure: {str(e)}")
    
    # Check 3: Collectors can be instantiated
    try:
        from apps.intel.services.collectors.rss_collector import RSSCollector
        from apps.intel.services.collectors.steam_news_collector import SteamNewsCollector
        from apps.intel.services.collectors.reddit_rss_collector import RedditRSSCollector
        
        # Try to instantiate (should not fail)
        rss_collector = RSSCollector()
        steam_collector = SteamNewsCollector()
        reddit_collector = RedditRSSCollector()
        
        # Check they have collect method
        if not hasattr(rss_collector, 'collect'):
            errors.append("RSSCollector instance missing 'collect' method")
        if not hasattr(steam_collector, 'collect'):
            errors.append("SteamNewsCollector instance missing 'collect' method")
        if not hasattr(reddit_collector, 'collect'):
            errors.append("RedditRSSCollector instance missing 'collect' method")
            
    except ImportError as e:
        errors.append(f"Failed to import collectors: {str(e)}")
    except Exception as e:
        errors.append(f"Error instantiating collectors: {str(e)}")
    
    # Check 4: Policy engine can be loaded
    try:
        from apps.intel.policy.policy_engine import load_policy
        policy = load_policy()
        if not policy:
            warnings.append("Policy loaded but is empty")
    except Exception as e:
        errors.append(f"Policy engine load failed: {str(e)}")
    
    # Check 5: Intel health endpoint (if API is running)
    # This check is optional - only if we can reach the API
    health_result = check_intel_health()
    if health_result["error"]:
        # API not running is a warning, not error
        warnings.append(f"Intel health endpoint not reachable: {health_result['error']}")
    else:
        if not health_result["ok"]:
            warnings.append("Intel health endpoint returned not OK")
        if not health_result["policy_loaded"]:
            warnings.append("Intel health endpoint reports policy not loaded")
    
    status = StageStatus.FAIL if errors else (StageStatus.WARN if warnings else StageStatus.OK)
    
    return SupervisorResult(
        stage="orchestrator_smoke",
        status=status,
        errors=errors,
        warnings=warnings,
        details={
            "models_checked": True,
            "collectors_checked": True,
            "policy_checked": True,
            "health_check": health_result
        }
    )
