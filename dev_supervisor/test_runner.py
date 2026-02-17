"""
Test Runner - Runs contract tests via pytest
"""
import subprocess
import sys
from pathlib import Path
from typing import List

from dev_supervisor.config import config
from dev_supervisor.report import SupervisorResult, StageStatus


def run_contract_tests() -> SupervisorResult:
    """
    Run contract tests using pytest.
    Returns SupervisorResult.
    """
    errors: List[str] = []
    warnings: List[str] = []
    
    tests_dir = Path(config.CONTRACT_TESTS_DIR)
    
    if not tests_dir.exists():
        warnings.append(f"Contract tests directory not found: {config.CONTRACT_TESTS_DIR}")
        return SupervisorResult(
            stage="contract_tests",
            status=StageStatus.WARN,
            errors=[],
            warnings=warnings
        )
    
    # Check if pytest is available
    try:
        pytest_check = subprocess.run(
            [sys.executable, "-m", "pytest", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if pytest_check.returncode != 0:
            warnings.append("pytest not available, skipping contract tests")
            return SupervisorResult(
                stage="contract_tests",
                status=StageStatus.WARN,
                errors=[],
                warnings=warnings
            )
    except Exception as e:
        warnings.append(f"Cannot check pytest availability: {str(e)}")
        return SupervisorResult(
            stage="contract_tests",
            status=StageStatus.WARN,
            errors=[],
            warnings=warnings
        )
    
    # Run pytest
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(tests_dir), "-v", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        output = result.stdout + result.stderr
        
        if result.returncode == 0:
            status = StageStatus.OK
        else:
            status = StageStatus.FAIL
            # Extract failed tests
            failed_lines = [line for line in output.split('\n') if 'FAILED' in line or 'ERROR' in line]
            if failed_lines:
                errors.extend(failed_lines[:10])  # First 10 failures
            else:
                errors.append(f"Tests failed with exit code {result.returncode}")
        
        return SupervisorResult(
            stage="contract_tests",
            status=status,
            errors=errors,
            warnings=warnings,
            details={
                "exit_code": result.returncode,
                "output": output[:2000]  # First 2000 chars
            }
        )
        
    except subprocess.TimeoutExpired:
        return SupervisorResult(
            stage="contract_tests",
            status=StageStatus.FAIL,
            errors=["Contract tests timed out after 300 seconds"],
            warnings=[]
        )
    except Exception as e:
        return SupervisorResult(
            stage="contract_tests",
            status=StageStatus.FAIL,
            errors=[f"Failed to run contract tests: {str(e)}"],
            warnings=[]
        )
