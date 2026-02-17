"""
Configuration for Dev Supervisor
"""
import os
from typing import Optional


class SupervisorConfig:
    """Configuration for Dev Supervisor Agent"""
    
    # Docker services
    DOCKER_SERVICE_API: str = os.getenv("DOCKER_SERVICE_API", "api")
    DOCKER_SERVICE_POSTGRES: str = os.getenv("DOCKER_SERVICE_POSTGRES", "postgres")
    
    # Strict mode: fail fast on any error
    STRICT_MODE: bool = os.getenv("SUPERVISOR_STRICT_MODE", "true").lower() == "true"
    
    # Paths
    GUARDRAIL_SCRIPT: str = "scripts/guardrail.sh"
    SPECS_DIR: str = "SPECS"
    INTEL_SPEC: str = "SPECS/INTEL_TZ_V2.md"
    WORKFLOW_SPEC: str = "SPECS/WORKFLOW.md"
    
    # Test paths
    CONTRACT_TESTS_DIR: str = "tests_contract"
    
    @classmethod
    def get_config(cls) -> "SupervisorConfig":
        """Get singleton config instance"""
        if not hasattr(cls, "_instance"):
            cls._instance = cls()
        return cls._instance


# Global config instance
config = SupervisorConfig.get_config()
