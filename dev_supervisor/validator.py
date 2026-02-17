"""
Validator - Checks Intel contracts and structure
"""
import importlib
import inspect
from pathlib import Path
from typing import List, Optional

from dev_supervisor.config import config
from dev_supervisor.report import SupervisorResult, StageStatus


def validate_intel_contracts() -> SupervisorResult:
    """
    Validate Intel module contracts:
    - RSSCollector has collect method
    - BaseIntelCollector has correct methods
    - Policy engine loads without error
    - intel_policy.yaml is valid
    """
    errors: List[str] = []
    warnings: List[str] = []
    
    # Check 1: RSSCollector has collect method
    try:
        from apps.intel.services.collectors.rss_collector import RSSCollector
        if not hasattr(RSSCollector, 'collect'):
            errors.append("RSSCollector missing 'collect' method")
        elif not callable(getattr(RSSCollector, 'collect')):
            errors.append("RSSCollector 'collect' is not callable")
    except ImportError as e:
        errors.append(f"Failed to import RSSCollector: {str(e)}")
    except Exception as e:
        errors.append(f"Error checking RSSCollector: {str(e)}")
    
    # Check 2: BaseIntelCollector has correct methods
    try:
        from apps.intel.services.collectors.base_collector import BaseIntelCollector
        required_methods = ['validate_url', 'fetch_url', 'save_raw_item', 'collect']
        for method_name in required_methods:
            if not hasattr(BaseIntelCollector, method_name):
                errors.append(f"BaseIntelCollector missing '{method_name}' method")
            elif not callable(getattr(BaseIntelCollector, method_name)):
                errors.append(f"BaseIntelCollector '{method_name}' is not callable")
    except ImportError as e:
        errors.append(f"Failed to import BaseIntelCollector: {str(e)}")
    except Exception as e:
        errors.append(f"Error checking BaseIntelCollector: {str(e)}")
    
    # Check 3: Policy engine loads without error
    try:
        from apps.intel.policy.policy_engine import load_policy, validate_source_url
        policy = load_policy()
        if not policy:
            warnings.append("Policy engine loaded but returned empty policy")
        # Test validate_source_url
        test_result = validate_source_url("https://store.steampowered.com")
        if not isinstance(test_result, tuple) or len(test_result) != 2:
            errors.append("validate_source_url does not return (decision, reason) tuple")
    except ImportError as e:
        errors.append(f"Failed to import policy_engine: {str(e)}")
    except Exception as e:
        errors.append(f"Policy engine load failed: {str(e)}")
    
    # Check 4: intel_policy.yaml exists and is valid YAML
    policy_path = Path("apps/intel/policy/intel_policy.yaml")
    if not policy_path.exists():
        errors.append("intel_policy.yaml not found")
    else:
        try:
            import yaml
            with open(policy_path, 'r', encoding='utf-8') as f:
                yaml.safe_load(f)
        except ImportError:
            warnings.append("PyYAML not available, cannot validate YAML syntax")
        except yaml.YAMLError as e:
            errors.append(f"intel_policy.yaml is invalid YAML: {str(e)}")
        except Exception as e:
            errors.append(f"Error reading intel_policy.yaml: {str(e)}")
    
    # Check 5: Intel models are importable
    try:
        from apps.intel.db.models import IntelSource, IntelRawItem, IntelEvent
    except ImportError as e:
        errors.append(f"Failed to import Intel models: {str(e)}")
    except Exception as e:
        errors.append(f"Error importing Intel models: {str(e)}")
    
    status = StageStatus.FAIL if errors else (StageStatus.WARN if warnings else StageStatus.OK)
    
    return SupervisorResult(
        stage="contract_validation",
        status=status,
        errors=errors,
        warnings=warnings,
        details={
            "checks_performed": 5
        }
    )
