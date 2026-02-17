# Architecture Decisions

This document tracks key architectural decisions made during development, especially those introduced by AI-assisted development.

## Format

Each decision includes:
- **What changed**: Brief description of the change
- **Why it exists**: Rationale and context
- **What to remove later**: If this is temporary or should be refactored later

---

## 2026-01-19: Dev Supervisor Autopilot C+

### What changed
- Created `dev_supervisor/` module with autonomous orchestrator
- Added container detection logic (`_is_inside_container()`) across multiple modules
- Added autofix system with whitelist of safe fixes
- Modified `gs-dev.sh` to be host-only with readiness checks

### Why it exists
- **Container detection**: Supervisor runs both on host and inside containers. Need to detect context to avoid Docker-in-Docker issues.
- **Autofix**: Common issues (missing imports, git in Dockerfiles) can be fixed automatically without human intervention.
- **Host-only gs-dev.sh**: Prevents confusion when script is run inside container (which doesn't work).

### What to remove later
- If we standardize on always running supervisor inside container, remove host detection logic.
- Autofix system can be expanded but should remain whitelist-only (never auto-delete files or change migrations).

---

## 2026-01-19: Intel Module Container Detection

### What changed
- `orchestrator_smoke.py` and `test_runner.py` detect container via `/.dockerenv` or `IN_DOCKER` env var
- Health endpoint path fixed: `/api/v1/intel/health` (not `/intel/health`)

### Why it exists
- Intel health check was failing with 404 because endpoint path was incorrect
- Smoke tests need to run directly inside container, not via docker compose exec

### What to remove later
- If we standardize on single execution context, simplify detection logic.

---

## 2026-01-19: Git in Dockerfiles

### What changed
- Added `git` to `apt-get install` in both `docker/api.Dockerfile` and `docker/worker.Dockerfile`

### Why it exists
- `guardrail.sh` uses git commands and fails with "git: command not found" inside containers
- Needed for guardrails to work inside Docker

### What to remove later
- If guardrails are moved to host-only, git can be removed from Dockerfiles to reduce image size.

---

## 2026-01-19: pytest in Dev Dependencies

### What changed
- `docker/api.Dockerfile` changed from `poetry install --only main` to `poetry install` (includes dev deps)

### Why it exists
- Contract tests require pytest, which is in dev dependencies
- Supervisor needs to run tests inside container

### What to remove later
- If we move tests to separate CI stage, can revert to `--only main` to reduce image size.

---

## 2026-01-19: Intel Collectors Unified Contract

### What changed
- All collectors (`RSSCollector`, `SteamNewsCollector`, `RedditRSSCollector`) now:
  - Accept `db: Session` in `__init__`
  - Implement `collect_source(self, source: IntelSource) -> int`
  - Use `self.db` consistently

### Why it exists
- Unified interface makes collectors interchangeable
- Easier to test and mock
- Consistent error handling

### What to remove later
- None - this is the target architecture.

---

## Complexity Warnings

The supervisor will warn if:
- A file exceeds 600 lines
- More than 5 new modules are added in a single commit

These are warnings, not blockers, but should prompt review.
