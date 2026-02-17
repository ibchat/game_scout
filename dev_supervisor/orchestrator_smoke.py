"""
Orchestrator Smoke Test - Basic smoke test for Intel orchestrator
"""
import sys
import os
import subprocess
from pathlib import Path
from typing import List
from unittest.mock import Mock, patch

from dev_supervisor.config import config
from dev_supervisor.report import SupervisorResult, StageStatus
from dev_supervisor.http_utils import check_intel_health


def _is_inside_container() -> bool:
    """Check if running inside Docker container"""
    return os.path.exists("/.dockerenv") or os.getenv("IN_DOCKER") == "1"


def run_orchestrator_smoke() -> SupervisorResult:
    """
    Smoke test for Intel orchestrator:
    1. Check IntelSource model is accessible
    2. Check intel_raw_items table exists (via model)
    3. Check collectors can be instantiated
    4. Run actual RSS collection smoke test inside Docker
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
    
    # Check 3: Collectors can be imported and have correct interface
    try:
        from apps.intel.services.collectors.rss_collector import RSSCollector
        from apps.intel.services.collectors.steam_news_collector import SteamNewsCollector
        from apps.intel.services.collectors.reddit_rss_collector import RedditRSSCollector
        from sqlalchemy.orm import Session
        from unittest.mock import Mock
        
        # Check collectors have required methods (without instantiating, as they need db)
        if not hasattr(RSSCollector, 'collect'):
            errors.append("RSSCollector missing 'collect' method")
        if not hasattr(RSSCollector, 'collect_source'):
            errors.append("RSSCollector missing 'collect_source' method")
        if not hasattr(SteamNewsCollector, 'collect'):
            errors.append("SteamNewsCollector missing 'collect' method")
        if not hasattr(RedditRSSCollector, 'collect'):
            errors.append("RedditRSSCollector missing 'collect' method")
        
        # Try to instantiate with mock db to verify __init__ signature
        mock_db = Mock(spec=Session)
        try:
            rss_collector = RSSCollector(db=mock_db)
            if not hasattr(rss_collector, 'db'):
                errors.append("RSSCollector instance missing 'db' attribute")
        except TypeError as e:
            errors.append(f"RSSCollector.__init__ signature incorrect: {str(e)}")
            
    except ImportError as e:
        errors.append(f"Failed to import collectors: {str(e)}")
    except Exception as e:
        errors.append(f"Error checking collectors: {str(e)}")
    
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
    # Use correct endpoint path: /api/v1/intel/health (not /intel/health)
    if _is_inside_container():
        # Inside container: use localhost
        health_result = check_intel_health("http://localhost:8000")
    else:
        # On host: try localhost (may not work if API not exposed)
        health_result = check_intel_health("http://localhost:8000")
    
    if health_result["error"]:
        # API not running is a warning, not error
        warnings.append(f"Intel health endpoint not reachable: {health_result['error']}")
    else:
        if not health_result["ok"]:
            warnings.append("Intel health endpoint returned not OK")
        if not health_result["policy_loaded"]:
            warnings.append("Intel health endpoint reports policy not loaded")
    
    # Check 6: Run actual RSS collection smoke test
    smoke_script = Path("scripts/intel_smoke_collect_rss.py")
    if smoke_script.exists():
        if _is_inside_container():
            # Inside container: run directly
            try:
                smoke_result = subprocess.run(
                    [sys.executable, "scripts/intel_smoke_collect_rss.py"],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                if smoke_result.returncode == 0:
                    # Parse output for COLLECTED/TOTAL
                    output = smoke_result.stdout
                    if "COLLECTED:" in output and "TOTAL:" in output:
                        # Extract numbers
                        import re
                        collected_match = re.search(r"COLLECTED:\s*(\d+)", output)
                        total_match = re.search(r"TOTAL:\s*(\d+)", output)
                        if collected_match and total_match:
                            collected = int(collected_match.group(1))
                            total = int(total_match.group(1))
                            if total > 0:
                                # Success
                                pass  # No error
                            else:
                                errors.append("Smoke test: TOTAL is 0, no items in database")
                        else:
                            warnings.append("Smoke test: Could not parse COLLECTED/TOTAL from output")
                    else:
                        warnings.append("Smoke test: Output format unexpected")
                else:
                    errors.append(f"Smoke test failed with exit code {smoke_result.returncode}")
                    if smoke_result.stderr:
                        errors.append(f"Smoke test error: {smoke_result.stderr[:200]}")
            except subprocess.TimeoutExpired:
                errors.append("Smoke test timed out after 120 seconds")
            except Exception as e:
                warnings.append(f"Could not run smoke test: {str(e)}")
        else:
            # On host: run via docker compose
            try:
                service_check = subprocess.run(
                    ["docker", "compose", "ps", config.DOCKER_SERVICE_API, "--format", "json"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if service_check.returncode == 0:
                    # Run smoke test
                    try:
                        smoke_result = subprocess.run(
                            ["docker", "compose", "exec", "-T", config.DOCKER_SERVICE_API,
                             "python", "scripts/intel_smoke_collect_rss.py"],
                            capture_output=True,
                            text=True,
                            timeout=120
                        )
                        if smoke_result.returncode == 0:
                            # Parse output for COLLECTED/TOTAL
                            output = smoke_result.stdout
                            if "COLLECTED:" in output and "TOTAL:" in output:
                                # Extract numbers
                                import re
                                collected_match = re.search(r"COLLECTED:\s*(\d+)", output)
                                total_match = re.search(r"TOTAL:\s*(\d+)", output)
                                if collected_match and total_match:
                                    collected = int(collected_match.group(1))
                                    total = int(total_match.group(1))
                                    if total > 0:
                                        # Success
                                        pass  # No error
                                    else:
                                        errors.append("Smoke test: TOTAL is 0, no items in database")
                                else:
                                    warnings.append("Smoke test: Could not parse COLLECTED/TOTAL from output")
                            else:
                                warnings.append("Smoke test: Output format unexpected")
                        else:
                            errors.append(f"Smoke test failed with exit code {smoke_result.returncode}")
                            if smoke_result.stderr:
                                errors.append(f"Smoke test error: {smoke_result.stderr[:200]}")
                    except subprocess.TimeoutExpired:
                        errors.append("Smoke test timed out after 120 seconds")
                    except Exception as e:
                        warnings.append(f"Could not run smoke test in Docker: {str(e)}")
                else:
                    warnings.append("Docker service not running, skipping smoke test execution")
            except (FileNotFoundError, subprocess.TimeoutExpired):
                warnings.append("Docker not found, skipping smoke test execution")
            except Exception as e:
                warnings.append(f"Could not check Docker service: {str(e)}")
    else:
        warnings.append(f"Smoke script not found: {smoke_script}")
    
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
