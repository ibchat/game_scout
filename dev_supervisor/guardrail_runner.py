"""
Guardrail Runner - Wrapper for scripts/guardrail.sh
"""
import subprocess
import sys
from pathlib import Path

from dev_supervisor.config import config
from dev_supervisor.report import SupervisorResult, StageStatus


def run_guardrails() -> SupervisorResult:
    """
    Run guardrail script and parse results.
    Returns SupervisorResult.
    """
    errors: List[str] = []
    warnings: List[str] = []
    
    guardrail_path = Path(config.GUARDRAIL_SCRIPT)
    
    if not guardrail_path.exists():
        return SupervisorResult(
            stage="guardrails",
            status=StageStatus.FAIL,
            errors=[f"Guardrail script not found: {config.GUARDRAIL_SCRIPT}"],
            warnings=[]
        )
    
    # Make executable
    guardrail_path.chmod(0o755)
    
    # Run guardrail script
    try:
        result = subprocess.run(
            ["bash", str(guardrail_path)],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        output = result.stdout + result.stderr
        
        # Parse output
        if result.returncode == 0:
            status = StageStatus.OK
            # Check for warnings in output
            if "⚠" in output or "WARNING" in output.upper():
                warnings.append("Guardrails passed but warnings detected")
        else:
            status = StageStatus.FAIL
            # Extract errors from output
            lines = output.split('\n')
            for line in lines:
                if "✗" in line or "FAIL" in line.upper() or "ERROR" in line.upper():
                    if line.strip():
                        errors.append(line.strip())
            
            if not errors:
                errors.append(f"Guardrails failed with exit code {result.returncode}")
        
        return SupervisorResult(
            stage="guardrails",
            status=status,
            errors=errors,
            warnings=warnings,
            details={
                "exit_code": result.returncode,
                "output": output[:1000]  # First 1000 chars
            }
        )
        
    except subprocess.TimeoutExpired:
        return SupervisorResult(
            stage="guardrails",
            status=StageStatus.FAIL,
            errors=["Guardrail script timed out after 60 seconds"],
            warnings=[]
        )
    except Exception as e:
        return SupervisorResult(
            stage="guardrails",
            status=StageStatus.FAIL,
            errors=[f"Failed to run guardrails: {str(e)}"],
            warnings=[]
        )
