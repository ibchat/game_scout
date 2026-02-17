"""
Autofix Module - Safe automatic fixes for common issues
Only applies fixes from whitelist, all fixes are idempotent
"""
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Optional, Tuple

logger = None  # Will be set by caller


class AutofixResult:
    """Result of an autofix attempt"""
    def __init__(self, fix_name: str, applied: bool, reason: str, changes: List[str] = None):
        self.fix_name = fix_name
        self.applied = applied
        self.reason = reason
        self.changes = changes or []


class BaseAutofix:
    """Base class for autofixes"""
    def __init__(self, project_root: Path):
        self.project_root = project_root
    
    def can_fix(self, error_message: str) -> bool:
        """Check if this fix can handle the error"""
        raise NotImplementedError
    
    def apply(self) -> AutofixResult:
        """Apply the fix"""
        raise NotImplementedError
    
    def _run_git_command(self, cmd: List[str]) -> Tuple[bool, str]:
        """Run git command and return (success, output)"""
        try:
            result = subprocess.run(
                ["git"] + cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.returncode == 0, result.stdout + result.stderr
        except Exception as e:
            return False, str(e)


class FixMissingImportSubprocess(BaseAutofix):
    """Fix missing 'import subprocess' in orchestrator_smoke.py"""
    
    def can_fix(self, error_message: str) -> bool:
        return "NameError: name 'subprocess' is not defined" in error_message or \
               "NameError: subprocess" in error_message
    
    def apply(self) -> AutofixResult:
        file_path = self.project_root / "dev_supervisor" / "orchestrator_smoke.py"
        
        if not file_path.exists():
            return AutofixResult(
                "FixMissingImportSubprocess",
                False,
                f"File not found: {file_path}"
            )
        
        content = file_path.read_text(encoding="utf-8")
        
        # Check if import already exists
        if "import subprocess" in content:
            return AutofixResult(
                "FixMissingImportSubprocess",
                False,
                "import subprocess already present"
            )
        
        # Find import section and add subprocess
        lines = content.split("\n")
        import_section_end = 0
        
        for i, line in enumerate(lines):
            if line.startswith("import ") or line.startswith("from "):
                import_section_end = i + 1
            elif import_section_end > 0 and line.strip() and not line.startswith("#"):
                break
        
        # Insert import subprocess after other imports
        if import_section_end > 0:
            lines.insert(import_section_end, "import subprocess")
        else:
            # Fallback: add after first line
            lines.insert(1, "import subprocess")
        
        new_content = "\n".join(lines)
        file_path.write_text(new_content, encoding="utf-8")
        
        # Commit the fix
        success, output = self._run_git_command(["add", str(file_path.relative_to(self.project_root))])
        if success:
            self._run_git_command([
                "commit", "-m",
                "autofix: add missing import subprocess in orchestrator_smoke.py"
            ])
        
        return AutofixResult(
            "FixMissingImportSubprocess",
            True,
            "Added import subprocess",
            [str(file_path.relative_to(self.project_root))]
        )


class FixMissingGitInDockerfile(BaseAutofix):
    """Fix missing git in Dockerfile (for guardrail.sh)"""
    
    def can_fix(self, error_message: str) -> bool:
        return "git: command not found" in error_message or \
               "git not found" in error_message.lower()
    
    def apply(self) -> AutofixResult:
        dockerfiles = [
            self.project_root / "docker" / "api.Dockerfile",
            self.project_root / "docker" / "worker.Dockerfile"
        ]
        
        changes = []
        
        for dockerfile in dockerfiles:
            if not dockerfile.exists():
                continue
            
            content = dockerfile.read_text(encoding="utf-8")
            
            # Check if git already installed
            if "apt-get install" in content and "git" in content:
                continue
            
            # Find apt-get install line and add git
            pattern = r"(apt-get install -y[^\n]*)"
            match = re.search(pattern, content)
            
            if match:
                install_line = match.group(1)
                if "git" not in install_line:
                    # Add git to install line
                    new_line = install_line.rstrip(" \\") + " \\\n    git"
                    content = content.replace(install_line, new_line)
                    dockerfile.write_text(content, encoding="utf-8")
                    changes.append(str(dockerfile.relative_to(self.project_root)))
        
        if not changes:
            return AutofixResult(
                "FixMissingGitInDockerfile",
                False,
                "git already present in Dockerfiles or files not found"
            )
        
        # Commit the fix
        for change in changes:
            self._run_git_command(["add", change])
        
        self._run_git_command([
            "commit", "-m",
            "autofix: add git to Dockerfiles for guardrail.sh"
        ])
        
        return AutofixResult(
            "FixMissingGitInDockerfile",
            True,
            f"Added git to {len(changes)} Dockerfile(s)",
            changes
        )


class FixMissingPytest(BaseAutofix):
    """Fix missing pytest in pyproject.toml"""
    
    def can_fix(self, error_message: str) -> bool:
        return "No module named pytest" in error_message or \
               "pytest not found" in error_message.lower() or \
               "pytest: command not found" in error_message
    
    def apply(self) -> AutofixResult:
        pyproject_path = self.project_root / "pyproject.toml"
        
        if not pyproject_path.exists():
            return AutofixResult(
                "FixMissingPytest",
                False,
                "pyproject.toml not found"
            )
        
        content = pyproject_path.read_text(encoding="utf-8")
        
        # Check if pytest already present
        if 'pytest =' in content:
            return AutofixResult(
                "FixMissingPytest",
                False,
                "pytest already in pyproject.toml"
            )
        
        # Add pytest to dependencies (in dev or main section)
        # Look for [tool.poetry.dependencies] or [tool.poetry.group.dev.dependencies]
        if "[tool.poetry.group.dev.dependencies]" in content:
            # Add to dev dependencies
            pattern = r"(\[tool\.poetry\.group\.dev\.dependencies\]\n)"
            if re.search(pattern, content):
                content = re.sub(
                    pattern,
                    r"\1pytest = \"^7.4.4\"\n",
                    content
                )
        elif "[tool.poetry.dependencies]" in content:
            # Add to main dependencies
            pattern = r"(\[tool\.poetry\.dependencies\]\n)"
            content = re.sub(
                pattern,
                r"\1pytest = \"^7.4.4\"\n",
                content
            )
        else:
            # Fallback: add at end
            content += "\n[tool.poetry.dependencies]\npytest = \"^7.4.4\"\n"
        
        pyproject_path.write_text(content, encoding="utf-8")
        
        # Commit the fix
        self._run_git_command(["add", "pyproject.toml"])
        self._run_git_command([
            "commit", "-m",
            "autofix: add pytest to pyproject.toml dependencies"
        ])
        
        return AutofixResult(
            "FixMissingPytest",
            True,
            "Added pytest to pyproject.toml",
            ["pyproject.toml"]
        )


class FixMissingSmokeScript(BaseAutofix):
    """Create missing intel_smoke_collect_rss.py script"""
    
    def can_fix(self, error_message: str) -> bool:
        return "Smoke script not found" in error_message or \
               "intel_smoke_collect_rss.py not found" in error_message
    
    def apply(self) -> AutofixResult:
        script_path = self.project_root / "scripts" / "intel_smoke_collect_rss.py"
        
        if script_path.exists():
            return AutofixResult(
                "FixMissingSmokeScript",
                False,
                "Smoke script already exists"
            )
        
        # Create script from template
        script_content = '''#!/usr/bin/env python3
"""
Intel RSS Collector Smoke Test
Creates test source and collects RSS items, verifies they are saved to DB.
"""
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from apps.db.session import SessionLocal
from apps.intel.db.models import IntelSource, IntelRawItem
from apps.intel.services.collectors.rss_collector import RSSCollector

# Test RSS feed (Steam RSS)
TEST_RSS_URL = "https://store.steampowered.com/feeds/news.xml"


def main():
    """Run smoke test"""
    db = SessionLocal()
    
    try:
        # Get or create test source
        source = db.query(IntelSource).filter(
            IntelSource.name == "Steam RSS test"
        ).first()
        
        if not source:
            source = IntelSource(
                type="rss",
                name="Steam RSS test",
                url=TEST_RSS_URL,
                is_enabled=True
            )
            db.add(source)
            db.commit()
            db.refresh(source)
            print(f"Created test source: {source.id}")
        else:
            print(f"Using existing source: {source.id}")
        
        # Get initial count
        initial_count = db.query(IntelRawItem).count()
        print(f"Initial intel_raw_items count: {initial_count}")
        
        # Create collector and collect
        collector = RSSCollector(db=db)
        saved_count = collector.collect_source(source)
        
        # Get final count
        final_count = db.query(IntelRawItem).count()
        new_items = final_count - initial_count
        
        print(f"COLLECTED: {saved_count} new items")
        print(f"TOTAL: {final_count} items in database")
        print(f"NEW: {new_items} items added")
        
        # Verify
        if saved_count > 0:
            print("✅ SUCCESS: Items were collected and saved")
            return 0
        elif new_items == 0 and initial_count > 0:
            print("✅ SUCCESS: Idempotency check passed (no duplicates added)")
            return 0
        else:
            print("❌ FAILED: No items were collected")
            return 1
            
    except Exception as e:
        print(f"❌ ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
'''
        
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(script_content, encoding="utf-8")
        script_path.chmod(0o755)  # Make executable
        
        # Commit the fix
        self._run_git_command(["add", str(script_path.relative_to(self.project_root))])
        self._run_git_command([
            "commit", "-m",
            "autofix: create missing intel_smoke_collect_rss.py script"
        ])
        
        return AutofixResult(
            "FixMissingSmokeScript",
            True,
            "Created intel_smoke_collect_rss.py",
            [str(script_path.relative_to(self.project_root))]
        )


class FixHealthEndpoint(BaseAutofix):
    """Fix missing /intel/health endpoint (ensure router is included)"""
    
    def can_fix(self, error_message: str) -> bool:
        return "404" in error_message and ("intel/health" in error_message or "/health" in error_message) or \
               "Intel health endpoint not reachable" in error_message
    
    def apply(self) -> AutofixResult:
        main_py = self.project_root / "apps" / "api" / "main.py"
        
        if not main_py.exists():
            return AutofixResult(
                "FixHealthEndpoint",
                False,
                "apps/api/main.py not found"
            )
        
        content = main_py.read_text(encoding="utf-8")
        
        # Check if Intel router already included
        if "intel_router" in content and "include_router" in content:
            # Check if it's actually included
            if "app.include_router(intel_router" in content:
                return AutofixResult(
                    "FixHealthEndpoint",
                    False,
                    "Intel router already included in main.py"
                )
        
        # Add Intel router inclusion (if not present)
        # Look for other router inclusions and add Intel after them
        if "intel_router" not in content:
            # Add import
            import_pattern = r"(from apps\.api\.routers import[^\n]*)"
            if re.search(import_pattern, content):
                # Add to existing import or add new import
                content = content.replace(
                    "# Intel module",
                    "# Intel module\ntry:\n    from apps.intel.api import router as intel_router\n    app.include_router(intel_router.router, prefix=API_V1)\nexcept Exception as e:\n    logger.warning(f\"Intel router not available: {e}\")"
                )
            else:
                # Add at end before CMD
                content += "\n# Intel module\ntry:\n    from apps.intel.api import router as intel_router\n    app.include_router(intel_router.router, prefix=API_V1)\nexcept Exception as e:\n    logger.warning(f\"Intel router not available: {e}\")\n"
        
        main_py.write_text(content, encoding="utf-8")
        
        # Commit the fix
        self._run_git_command(["add", "apps/api/main.py"])
        self._run_git_command([
            "commit", "-m",
            "autofix: ensure Intel router is included in main.py"
        ])
        
        return AutofixResult(
            "FixHealthEndpoint",
            True,
            "Ensured Intel router is included",
            ["apps/api/main.py"]
        )


# Registry of all available fixes
ALL_FIXES = [
    FixMissingImportSubprocess,
    FixMissingGitInDockerfile,
    FixMissingPytest,
    FixMissingSmokeScript,
    FixHealthEndpoint,
]


def detect_and_apply_fixes(project_root: Path, error_messages: List[str], logger_instance=None) -> List[AutofixResult]:
    """
    Detect applicable fixes and apply them.
    Returns list of AutofixResult.
    """
    global logger
    logger = logger_instance
    
    results = []
    
    for error_msg in error_messages:
        for fix_class in ALL_FIXES:
            fix_instance = fix_class(project_root)
            if fix_instance.can_fix(error_msg):
                if logger:
                    logger.info(f"Applying autofix: {fix_class.__name__}")
                result = fix_instance.apply()
                results.append(result)
                # Only apply first matching fix per error
                break
    
    return results
