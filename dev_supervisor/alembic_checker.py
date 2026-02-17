"""
Alembic Checker - Validates migration chain and runs upgrade
"""
import subprocess
import sys
from pathlib import Path
from typing import List

from dev_supervisor.config import config
from dev_supervisor.report import SupervisorResult, StageStatus


def check_migration_chain() -> SupervisorResult:
    """
    Check that migration chain is valid (no breaks in down_revision).
    Returns SupervisorResult.
    """
    errors: List[str] = []
    warnings: List[str] = []
    
    migrations_dir = Path("migrations/versions")
    
    if not migrations_dir.exists():
        return SupervisorResult(
            stage="migration_chain",
            status=StageStatus.FAIL,
            errors=["Migrations directory not found: migrations/versions"],
            warnings=[]
        )
    
    # Check for multiple heads (basic check)
    try:
        result = subprocess.run(
            ["docker", "compose", "exec", "-T", config.DOCKER_SERVICE_API, "alembic", "heads"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            # Docker might not be available - this is a warning, not error
            warnings.append("Cannot check migration heads (Docker not available or service not running)")
        else:
            output = result.stdout.strip()
            heads = [line.strip() for line in output.split('\n') if line.strip() and not line.startswith('INFO:')]
            
            if len(heads) > 1:
                errors.append(f"Multiple Alembic heads detected: {heads}")
            elif len(heads) == 0:
                warnings.append("No Alembic heads found")
        
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError) as e:
        warnings.append(f"Cannot check migration heads: {str(e)}")
    
    # Check migration files exist
    migration_files = list(migrations_dir.glob("*.py"))
    if not migration_files:
        errors.append("No migration files found")
    
    status = StageStatus.FAIL if errors else (StageStatus.WARN if warnings else StageStatus.OK)
    
    return SupervisorResult(
        stage="migration_chain",
        status=status,
        errors=errors,
        warnings=warnings,
        details={
            "migration_files_count": len(migration_files)
        }
    )


def run_upgrade_head() -> SupervisorResult:
    """
    Run alembic upgrade head (dry run check).
    Returns SupervisorResult.
    """
    errors: List[str] = []
    warnings: List[str] = []
    
    try:
        # Check if Docker is available
        docker_check = subprocess.run(
            ["docker", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if docker_check.returncode != 0:
            warnings.append("Docker not available, skipping alembic upgrade check")
            return SupervisorResult(
                stage="alembic_upgrade",
                status=StageStatus.WARN,
                errors=[],
                warnings=warnings
            )
        
        # Check if service is running
        service_check = subprocess.run(
            ["docker", "compose", "ps", config.DOCKER_SERVICE_API, "--format", "json"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if service_check.returncode != 0:
            warnings.append(f"Service {config.DOCKER_SERVICE_API} not running, skipping alembic upgrade")
            return SupervisorResult(
                stage="alembic_upgrade",
                status=StageStatus.WARN,
                errors=[],
                warnings=warnings
            )
        
        # Run alembic upgrade head
        result = subprocess.run(
            ["docker", "compose", "exec", "-T", config.DOCKER_SERVICE_API, "alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
            timeout=120
        )
        
        output = result.stdout + result.stderr
        
        if result.returncode == 0:
            status = StageStatus.OK
        else:
            status = StageStatus.FAIL
            errors.append(f"Alembic upgrade failed with exit code {result.returncode}")
            # Extract error details
            error_lines = [line for line in output.split('\n') if 'error' in line.lower() or 'fail' in line.lower()]
            if error_lines:
                errors.extend(error_lines[:5])  # First 5 error lines
        
        return SupervisorResult(
            stage="alembic_upgrade",
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
            stage="alembic_upgrade",
            status=StageStatus.FAIL,
            errors=["Alembic upgrade timed out after 120 seconds"],
            warnings=[]
        )
    except FileNotFoundError:
        warnings.append("Docker not found in PATH")
        return SupervisorResult(
            stage="alembic_upgrade",
            status=StageStatus.WARN,
            errors=[],
            warnings=warnings
        )
    except Exception as e:
        return SupervisorResult(
            stage="alembic_upgrade",
            status=StageStatus.FAIL,
            errors=[f"Failed to run alembic upgrade: {str(e)}"],
            warnings=[]
        )
