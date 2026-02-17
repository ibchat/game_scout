# Game Scout Workflow Specification

## Process Overview

1. Select Commit N from `SPECS/INTEL_TZ_V2.md`
2. Check allowed files list for Commit N (see table below)
3. Make changes **only** inside allowed files
4. Run `bash scripts/guardrail.sh`
5. If green: `git commit -m "..."` with descriptive message
6. If red: fix issues and repeat from step 4

## Commit → Allowed Files Mapping

### Commit 0: Fix Alembic Chain (if needed)
**Allowed Files:**
- `migrations/versions/006_add_voy_tables.py` (only if fixing down_revision)

**Forbidden:**
- Any other migration files
- Any other files

---

### Commit 1: Intel Scaffold + Config + Router + Docs
**Allowed Files:**
- `apps/intel/__init__.py`
- `apps/intel/config.py`
- `apps/intel/api/__init__.py`
- `apps/intel/api/router.py`
- `apps/intel/policy/__init__.py`
- `apps/intel/db/__init__.py`
- `apps/intel/services/__init__.py`
- `apps/intel/services/collectors/__init__.py`
- `apps/api/main.py` (only Intel router integration)
- `CONFIGURATION.md` (only Intel documentation section)

**Forbidden:**
- `apps/intel/db/models.py` (Commit 2)
- `migrations/versions/009_add_intel_tables.py` (Commit 2)
- Any changes to existing routers/models/tables

---

### Commit 2: Intel DB Models + Alembic Migration
**Allowed Files:**
- `apps/intel/db/models.py`
- `migrations/versions/009_add_intel_tables.py`
- `migrations/env.py` (only Intel models import)

**Forbidden:**
- Any changes to existing models in `apps/db/models.py`
- Any changes to existing migrations (001-008)
- Any other files

---

### Commit 3: Policy Engine
**Allowed Files:**
- `apps/intel/policy/intel_policy.yaml`
- `apps/intel/policy/policy_engine.py`
- `apps/intel/policy/policy_brief.py`
- `apps/intel/api/router.py` (only /intel/health endpoint if needed)
- `apps/intel/db/models.py` (only if adding audit_log fields, but table already in Commit 2)

**Forbidden:**
- Collectors (Commit 4)
- Services (Commit 5+)
- Telegram publisher (Commit 10)

---

### Commit 4: Collectors
**Allowed Files:**
- `apps/intel/services/collectors/rss_collector.py`
- `apps/intel/services/collectors/steam_news_collector.py`
- `apps/intel/services/collectors/reddit_rss_collector.py`
- `apps/worker/tasks/intel_collect_task.py` (if needed)

**Forbidden:**
- Extractor (Commit 5)
- Other services

---

### Guardrails Commit
**Allowed Files:**
- `scripts/guardrail.sh`
- `.cursor/rules/guardrails.md`
- `SPECS/WORKFLOW.md`
- `CONFIGURATION.md` (only guardrails section)

**Forbidden:**
- Any Intel implementation files
- Any migration files

---

## General Rules

### Always Allowed (any commit):
- Documentation files (`.md` in root or `docs/`)
- Configuration examples (`.env.example`)
- Test files (if adding new tests)

### Always Forbidden:
- Existing migrations (001-008)
- Existing models in `apps/db/models.py`
- Existing API routers (except adding Intel router in main.py)
- Existing Celery tasks (except new Intel tasks)

## Validation Checklist

Before committing:
- [ ] All changes are in allowed files list
- [ ] No changes to forbidden files
- [ ] `bash scripts/guardrail.sh` passes
- [ ] `git status` shows only expected files
- [ ] Commit message follows pattern from `SPECS/INTEL_TZ_V2.md`

## Error Recovery

If you accidentally modified forbidden file:
1. **DO NOT commit**
2. Use `git checkout HEAD -- <forbidden_file>` to restore
3. Re-apply changes to allowed files only
4. Re-run guardrail
5. Then commit
