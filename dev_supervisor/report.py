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
    
    return SupervisorReport(
        stable=stable,
        stages=results,
        summary=summary,
        critical_errors=critical_errors,
        total_stages=total,
        passed_stages=passed,
        failed_stages=failed
    )
