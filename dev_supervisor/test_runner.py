"""
Test Runner - Runs contract tests via pytest
"""
import subprocess
import sys
import os
from pathlib import Path
from typing import List

from dev_supervisor.config import config
from dev_supervisor.report import SupervisorResult, StageStatus


def run_contract_tests() -> SupervisorResult:
    """
    Run contract tests using pytest.
    If inside container, run directly. If on host, run via docker compose.
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
    
    # Check if inside container
    is_inside_container = os.path.exists("/.dockerenv") or os.getenv("IN_DOCKER") == "1"
    
    if is_inside_container:
        # Inside container: run pytest directly
        # First check if pytest is available
        try:
            pytest_check = subprocess.run(
                [sys.executable, "-m", "pytest", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if pytest_check.returncode != 0:
                errors.append("pytest not available in container (required for contract tests)")
                return SupervisorResult(
                    stage="contract_tests",
                    status=StageStatus.FAIL,
                    errors=errors,
                    warnings=warnings
                )
        except Exception as e:
            errors.append(f"Failed to check pytest availability: {str(e)}")
            return SupervisorResult(
                stage="contract_tests",
                status=StageStatus.FAIL,
                errors=errors,
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
    else:
        # On host: run via docker compose
        try:
            docker_check = subprocess.run(
                ["docker", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if docker_check.returncode != 0:
                warnings.append("Docker not available, skipping contract tests")
                return SupervisorResult(
                    stage="contract_tests",
                    status=StageStatus.WARN,
                    errors=[],
                    warnings=warnings
                )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            warnings.append("Docker not found, skipping contract tests")
            return SupervisorResult(
                stage="contract_tests",
                status=StageStatus.WARN,
                errors=[],
                warnings=warnings
            )
        
        # Check if service is running
        try:
            service_check = subprocess.run(
                ["docker", "compose", "ps", config.DOCKER_SERVICE_API, "--format", "json"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if service_check.returncode != 0:
                warnings.append(f"Service {config.DOCKER_SERVICE_API} not running, skipping contract tests")
                return SupervisorResult(
                    stage="contract_tests",
                    status=StageStatus.WARN,
                    errors=[],
                    warnings=warnings
                )
        except Exception as e:
            warnings.append(f"Cannot check service status: {str(e)}")
            return SupervisorResult(
                stage="contract_tests",
                status=StageStatus.WARN,
                errors=[],
                warnings=warnings
            )
        
        # Run pytest inside Docker container
        try:
            result = subprocess.run(
                ["docker", "compose", "exec", "-T", config.DOCKER_SERVICE_API, 
                 "python", "-m", "pytest", str(tests_dir), "-v", "--tb=short"],
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
