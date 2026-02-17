#!/usr/bin/env python3
"""
Dev Supervisor - Main entry point
Autonomous orchestrator for development workflow
"""
import sys
import os
import logging
from pathlib import Path
from typing import List

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dev_supervisor.config import config
from dev_supervisor.report import SupervisorResult, StageStatus, aggregate_results, SupervisorReport
from dev_supervisor.guardrail_runner import run_guardrails
from dev_supervisor.alembic_checker import check_migration_chain, run_upgrade_head
from dev_supervisor.validator import validate_intel_contracts
from dev_supervisor.test_runner import run_contract_tests
from dev_supervisor.orchestrator_smoke import run_orchestrator_smoke
from dev_supervisor.planner import check_specs

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main() -> int:
    """
    Main supervisor flow:
    1. Load config
    2. Run guardrails
    3. Validate migration chain
    4. Run alembic upgrade head (dry)
    5. Run contract tests
    6. Run orchestrator smoke test
    7. Aggregate results
    8. Exit code: 0 = stable, 1 = failed
    """
    logger.info("🚀 Dev Supervisor starting...")
    
    results: List[SupervisorResult] = []
    
    # Stage 1: Check specs
    logger.info("📋 Stage 1: Checking specs...")
    try:
        spec_result = check_specs()
        results.append(spec_result)
    except Exception as e:
        logger.error(f"Spec check failed: {e}", exc_info=True)
        results.append(SupervisorResult(
            stage="specs_check",
            status=StageStatus.FAIL,
            errors=[str(e)],
            warnings=[]
        ))
    
    # Stage 2: Run guardrails
    logger.info("🛡️ Stage 2: Running guardrails...")
    try:
        guardrail_result = run_guardrails()
        results.append(guardrail_result)
    except Exception as e:
        logger.error(f"Guardrail check failed: {e}", exc_info=True)
        results.append(SupervisorResult(
            stage="guardrails",
            status=StageStatus.FAIL,
            errors=[str(e)],
            warnings=[]
        ))
    
    # Stage 3: Validate migration chain
    logger.info("🔗 Stage 3: Validating migration chain...")
    try:
        chain_result = check_migration_chain()
        results.append(chain_result)
    except Exception as e:
        logger.error(f"Migration chain check failed: {e}", exc_info=True)
        results.append(SupervisorResult(
            stage="migration_chain",
            status=StageStatus.FAIL,
            errors=[str(e)],
            warnings=[]
        ))
    
    # Stage 4: Run alembic upgrade head
    logger.info("📦 Stage 4: Running alembic upgrade head...")
    try:
        alembic_result = run_upgrade_head()
        results.append(alembic_result)
    except Exception as e:
        logger.error(f"Alembic upgrade failed: {e}", exc_info=True)
        results.append(SupervisorResult(
            stage="alembic_upgrade",
            status=StageStatus.FAIL,
            errors=[str(e)],
            warnings=[]
        ))
    
    # Stage 5: Validate Intel contracts
    logger.info("📝 Stage 5: Validating Intel contracts...")
    try:
        contract_result = validate_intel_contracts()
        results.append(contract_result)
    except Exception as e:
        logger.error(f"Contract validation failed: {e}", exc_info=True)
        results.append(SupervisorResult(
            stage="contract_validation",
            status=StageStatus.FAIL,
            errors=[str(e)],
            warnings=[]
        ))
    
    # Stage 6: Run contract tests
    logger.info("🧪 Stage 6: Running contract tests...")
    try:
        test_result = run_contract_tests()
        results.append(test_result)
    except Exception as e:
        logger.error(f"Contract tests failed: {e}", exc_info=True)
        results.append(SupervisorResult(
            stage="contract_tests",
            status=StageStatus.FAIL,
            errors=[str(e)],
            warnings=[]
        ))
    
    # Stage 7: Run orchestrator smoke test
    logger.info("💨 Stage 7: Running orchestrator smoke test...")
    try:
        smoke_result = run_orchestrator_smoke()
        results.append(smoke_result)
    except Exception as e:
        logger.error(f"Orchestrator smoke test failed: {e}", exc_info=True)
        results.append(SupervisorResult(
            stage="orchestrator_smoke",
            status=StageStatus.FAIL,
            errors=[str(e)],
            warnings=[]
        ))
    
    # Aggregate results
    report = aggregate_results(results)
    
    # Print report
    report.print()
    
    # Print JSON if any failures
    if not report.stable:
        logger.info("Structured JSON report:")
        report.print_json()
    
    # Exit code
    exit_code = 0 if report.stable else 1
    
    if report.stable:
        logger.info("✅ Dev Supervisor: STABLE")
    else:
        logger.error("❌ Dev Supervisor: FAILED")
    
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
