"""
Structured reporting for Dev Supervisor
"""
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum


class StageStatus(str, Enum):
    """Status of a stage"""
    OK = "ok"
    FAIL = "fail"
    SKIP = "skip"
    WARN = "warn"


@dataclass
class SupervisorResult:
    """Result from a supervisor stage"""
    stage: str
    status: StageStatus
    errors: List[str]
    warnings: List[str]
    details: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        result = asdict(self)
        result["status"] = self.status.value
        return result


@dataclass
class SupervisorReport:
    """Final aggregated report"""
    stable: bool
    stages: List[SupervisorResult]
    summary: str
    critical_errors: List[str]
    total_stages: int
    passed_stages: int
    failed_stages: int
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "stable": self.stable,
            "stages": [stage.to_dict() for stage in self.stages],
            "summary": self.summary,
            "critical_errors": self.critical_errors,
            "total_stages": self.total_stages,
            "passed_stages": self.passed_stages,
            "failed_stages": self.failed_stages
        }
    
    def print(self) -> None:
        """Print formatted report"""
        print("\n" + "=" * 60)
        print("DEV SUPERVISOR REPORT")
        print("=" * 60)
        
        if self.stable:
            print("\n✅ SYSTEM STATUS: STABLE")
        else:
            print("\n❌ SYSTEM STATUS: FAILED")
        
        print(f"\nStages: {self.passed_stages}/{self.total_stages} passed")
        
        if self.critical_errors:
            print("\n🔴 CRITICAL ERRORS:")
            for error in self.critical_errors:
                print(f"  • {error}")
        
        print("\n📊 STAGE DETAILS:")
        for stage in self.stages:
            status_icon = "✅" if stage.status == StageStatus.OK else "❌" if stage.status == StageStatus.FAIL else "⚠️"
            print(f"\n{status_icon} {stage.stage}: {stage.status.value}")
            
            if stage.errors:
                print("  Errors:")
                for error in stage.errors:
                    print(f"    • {error}")
            
            if stage.warnings:
                print("  Warnings:")
                for warning in stage.warnings:
                    print(f"    • {warning}")
        
        print("\n" + "=" * 60)
        print(f"Summary: {self.summary}")
        print("=" * 60 + "\n")
    
    def print_json(self) -> None:
        """Print JSON report"""
        print(json.dumps(self.to_dict(), indent=2))


def aggregate_results(results: List[SupervisorResult]) -> SupervisorReport:
    """Aggregate multiple results into final report"""
    total = len(results)
    passed = sum(1 for r in results if r.status == StageStatus.OK)
    failed = sum(1 for r in results if r.status == StageStatus.FAIL)
    
    critical_errors = []
    for result in results:
        if result.status == StageStatus.FAIL:
            critical_errors.extend(result.errors)
    
    stable = failed == 0 and all(r.status == StageStatus.OK for r in results)
    
    summary_parts = []
    if stable:
        summary_parts.append("All stages passed")
    else:
        summary_parts.append(f"{failed} stage(s) failed")
    
    if critical_errors:
        summary_parts.append(f"{len(critical_errors)} critical error(s)")
    
    summary = ". ".join(summary_parts) if summary_parts else "No issues detected"
    
    # Complexity warnings (D2)
    complexity_warnings = _check_complexity(results)
    if complexity_warnings:
        summary += f". {len(complexity_warnings)} complexity warning(s)"
    
    return SupervisorReport(
        stable=stable,
        stages=results,
        summary=summary,
        critical_errors=critical_errors,
        total_stages=total,
        passed_stages=passed,
        failed_stages=failed
    )


def _check_complexity(results: List[SupervisorResult]) -> List[str]:
    """Check for complexity issues (D2)"""
    warnings = []
    
    # Check file sizes (if we have access to git)
    try:
        import subprocess
        from pathlib import Path
        
        project_root = Path(__file__).parent.parent.parent
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            changed_files = result.stdout.strip().split("\n")
            for file_path in changed_files:
                if not file_path:
                    continue
                full_path = project_root / file_path
                if full_path.exists() and full_path.is_file():
                    line_count = len(full_path.read_text(encoding="utf-8").split("\n"))
                    if line_count > 600:
                        warnings.append(f"File {file_path} exceeds 600 lines ({line_count})")
            
            # Check number of new modules
            new_modules = [f for f in changed_files if f.endswith("__init__.py") or "/" in f]
            if len(new_modules) > 5:
                warnings.append(f"More than 5 new modules added in this commit ({len(new_modules)})")
    except Exception:
        # Git not available or other error - skip complexity check
        pass
    
    return warnings
