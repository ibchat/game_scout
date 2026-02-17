---
alwaysApply: true
description: Guardrails and quality gates for Game Scout development
---

# Guardrails for Game Scout Development

## Critical Rules (MANDATORY)

### 1. File Deletion Policy
- **NEVER delete files** without explicit user permission
- If a file is marked as deleted in git status, restore it from git history first
- Exception: Only if user explicitly requests deletion in the prompt

### 2. Additive-Only for Intel Module
- Intel module must be **strictly additive-only**
- **DO NOT** modify existing:
  - API routers and their contracts
  - Database tables and models (except new Intel tables)
  - UI tabs and dashboard routing (except adding Intel tab)
  - Existing Celery tasks and schedules
- **ONLY allowed**: New files, new tables via Alembic, new routes, new Celery tasks

### 3. Migration Policy
- **NEVER modify existing migrations** (001-008)
- Only create new migrations (009+)
- If migration fix is needed, create separate commit: "MIGRATION FIX: ..."
- Always verify Alembic chain: `docker compose exec api alembic heads` should show single head

### 4. Commit Structure
- Follow commit plan from `SPECS/INTEL_TZ_V2.md` strictly
- **DO NOT skip commits** or combine unrelated changes
- Each commit must be:
  - Focused on single topic
  - Pass `scripts/guardrail.sh`
  - Leave `git status` clean

### 5. Guardrail Execution
- **ALWAYS run** `bash scripts/guardrail.sh` after each commit
- If guardrail fails, **YOU fix it** and re-run until green
- Never commit with failing guardrails

### 6. Specification Compliance
- **ALWAYS read** `SPECS/INTEL_TZ_V2.md` before making Intel changes
- **ALWAYS read** `SPECS/WORKFLOW.md` for commit structure
- Follow allowed files list for each commit (see WORKFLOW.md)

### 7. No Creative Refactoring
- **DO NOT** refactor existing code "just because"
- **DO NOT** change code style of existing modules
- **DO NOT** optimize code that wasn't requested
- Only make changes explicitly required by the task

## Workflow

1. Read `SPECS/INTEL_TZ_V2.md` to understand current commit
2. Check `SPECS/WORKFLOW.md` for allowed files list
3. Make changes **only** in allowed files
4. Run `bash scripts/guardrail.sh`
5. If green: commit with descriptive message
6. If red: fix issues and repeat from step 4

## Quality Gates

Before every commit:
- ✅ `git status` is clean (only expected files)
- ✅ `bash scripts/guardrail.sh` passes
- ✅ No syntax errors
- ✅ Alembic chain valid (if Docker available)
- ✅ No unauthorized file deletions
- ✅ No changes to existing migrations

## Error Handling

If guardrail fails:
1. **DO NOT** ask user to fix it
2. **YOU fix** the issues
3. Re-run guardrail
4. Repeat until green
5. Then commit

## Intel Commit Plan Reference

See `SPECS/INTEL_TZ_V2.md` section 21 for full commit plan:
- Commit 1: Intel scaffold + config + router
- Commit 2: DB models + Alembic migration
- Commit 3: Policy engine
- Commit 4: Collectors
- ... (see full plan in spec)
