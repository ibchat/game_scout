"""
Contract tests for migration chain
"""
import pytest
from pathlib import Path
import re


def test_migrations_directory_exists():
    """Test that migrations directory exists"""
    migrations_dir = Path("migrations/versions")
    assert migrations_dir.exists(), "Migrations directory should exist"


def test_migration_files_exist():
    """Test that migration files exist"""
    migrations_dir = Path("migrations/versions")
    migration_files = list(migrations_dir.glob("*.py"))
    assert len(migration_files) > 0, "Should have at least one migration file"


def test_intel_migration_exists():
    """Test that Intel migration exists"""
    intel_migration = Path("migrations/versions/009_add_intel_tables.py")
    assert intel_migration.exists(), "Intel migration (009_add_intel_tables.py) should exist"


def test_migration_files_have_revision():
    """Test that migration files have revision identifier"""
    migrations_dir = Path("migrations/versions")
    migration_files = [f for f in migrations_dir.glob("*.py") if f.name != "__init__.py"]
    
    for migration_file in migration_files[:5]:  # Check first 5
        content = migration_file.read_text(encoding='utf-8')
        assert 'revision =' in content, f"{migration_file.name} should have 'revision ='"


def test_migration_files_have_down_revision():
    """Test that migration files have down_revision (except initial)"""
    migrations_dir = Path("migrations/versions")
    migration_files = [f for f in migrations_dir.glob("*.py") if f.name != "__init__.py"]
    
    for migration_file in migration_files[:5]:  # Check first 5
        content = migration_file.read_text(encoding='utf-8')
        # Should have either down_revision or be initial migration
        has_down_revision = 'down_revision' in content
        is_initial = 'down_revision: Union[str, None] = None' in content or 'down_revision = None' in content
        assert has_down_revision or is_initial, f"{migration_file.name} should have down_revision or be initial"
