#!/usr/bin/env python3
"""
Dev Supervisor - Main entry point
Autonomous orchestrator for development workflow

Run as module:
    python -m dev_supervisor.run

Or directly:
    python dev_supervisor/run.py
"""
import sys
import os
import logging
from pathlib import Path
from typing import List

# Determine project root: if running as module, __file__ is in dev_supervisor/
# If running directly, __file__ is dev_supervisor/run.py
if __name__ == "__main__":
    # Running directly: dev_supervisor/run.py -> parent.parent = root
    project_root = Path(__file__).parent.parent
else:
    # Running as module: __file__ is dev_supervisor/__init__.py or run.py
    # Find root by looking for pyproject.toml or docker-compose.yml
    current = Path(__file__).parent
    while current != current.parent:
        if (current / "pyproject.toml").exists() or (current / "docker-compose.yml").exists():
            project_root = current
            break
        current = current.parent
    else:
        project_root = Path(__file__).parent.parent

# Add project root to path only if not already there
if str(project_root) not in sys.path:
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
    8. If --autofix and failed, apply fixes and retry (max 2 iterations)
    9. Exit code: 0 = stable, 1 = failed
    """
    # Parse arguments
    autofix_mode = "--autofix" in sys.argv
    
    logger.info("🚀 Dev Supervisor starting...")
    if autofix_mode:
        logger.info("🔧 Autofix mode enabled")
    
    max_iterations = 2 if autofix_mode else 1
    iteration = 0
    final_report = None
    
    while iteration < max_iterations:
        if iteration > 0:
            logger.info(f"🔄 Retry iteration {iteration + 1}/{max_iterations} after autofix...")
        
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
        final_report = report
        
        # If stable or not in autofix mode, exit loop
        if report.stable or not autofix_mode:
            break
        
        # In autofix mode and failed: try to apply fixes
        logger.info("🔧 Attempting autofixes...")
        from dev_supervisor.autofix import detect_and_apply_fixes
        
        # Collect all error messages
        error_messages = []
        for result in results:
            error_messages.extend(result.errors)
        
        if error_messages:
            fix_results = detect_and_apply_fixes(project_root, error_messages, logger)
            
            applied_fixes = [f for f in fix_results if f.applied]
            if applied_fixes:
                logger.info(f"✅ Applied {len(applied_fixes)} autofix(es):")
                for fix in applied_fixes:
                    logger.info(f"   - {fix.fix_name}: {fix.reason}")
                # Rebuild if Dockerfiles changed
                dockerfile_fixes = [f for f in applied_fixes if "Dockerfile" in str(f.changes)]
                if dockerfile_fixes:
                    logger.info("📦 Dockerfiles changed, rebuild required (will be done by gs-dev.sh)")
            else:
                logger.warning("⚠️  No applicable autofixes found")
                break  # No fixes applied, exit loop
        else:
            break  # No errors to fix
        
        iteration += 1
    
    # Print final report
    if final_report:
        final_report.print()
        
        # Print JSON if any failures
        if not final_report.stable:
            logger.info("Structured JSON report:")
            final_report.print_json()
        
        # Exit code
        exit_code = 0 if final_report.stable else 1
        
        if final_report.stable:
            logger.info("✅ Dev Supervisor: STABLE")
        else:
            logger.error("❌ Dev Supervisor: FAILED")
        
        return exit_code
    else:
        logger.error("No report generated")
        return 1


if __name__ == "__main__":
    sys.exit(main())
