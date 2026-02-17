"""
Planner - Checks specs and workflow compliance
"""
import os
from pathlib import Path
from typing import List

from dev_supervisor.config import config
from dev_supervisor.report import SupervisorResult, StageStatus

def check_specs() -> SupervisorResult:
    """
    Check that required spec files exist and have key sections.
    Returns SupervisorResult with status.
    """
    errors: List[str] = []
    warnings: List[str] = []
    
    # Check Intel spec
    intel_spec_path = Path(config.INTEL_SPEC)
    if not intel_spec_path.exists():
        errors.append(f"Intel spec not found: {config.INTEL_SPEC}")
    else:
        # Check for key sections
        content = intel_spec_path.read_text(encoding='utf-8')
        required_sections = [
            "Policy",
            "База данных",
            "Источники данных",
            "Extractor",
            "Dedup/Cluster"
        ]
        for section in required_sections:
            if section not in content:
                warnings.append(f"Intel spec missing section: {section}")
    
    # Check workflow spec
    workflow_spec_path = Path(config.WORKFLOW_SPEC)
    if not workflow_spec_path.exists():
        errors.append(f"Workflow spec not found: {config.WORKFLOW_SPEC}")
    else:
        # Check for key sections
        content = workflow_spec_path.read_text(encoding='utf-8')
        required_sections = [
            "Commit → Allowed Files Mapping",
            "Process Overview"
        ]
        for section in required_sections:
            if section not in content:
                warnings.append(f"Workflow spec missing section: {section}")
    
    # Determine status
    if errors:
        status = StageStatus.FAIL
    elif warnings:
        status = StageStatus.WARN
    else:
        status = StageStatus.OK
    
    return SupervisorResult(
        stage="specs_check",
        status=status,
        errors=errors,
        warnings=warnings,
        details={
            "intel_spec_exists": intel_spec_path.exists() if intel_spec_path else False,
            "workflow_spec_exists": workflow_spec_path.exists() if workflow_spec_path else False
        }
    )
