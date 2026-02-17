# Autopilot C++ LOCAL - Self-Trigger Mode Setup

## Overview

Autopilot C++ LOCAL provides fully automatic development workflow:
- **Git hook**: Automatically runs supervisor after commits
- **File watcher daemon**: Monitors file changes and auto-rebuilds
- **Strict criteria**: All checks must pass, no warnings allowed

## Quick Setup

### 1. Enable Git Hook

```bash
chmod +x .git/hooks/post-commit
```

The hook will automatically run `bash scripts/gs-dev.sh --autofix` after commits that:
- Contain `[autopilot]` in commit message, OR
- Change files in `apps/`, `dev_supervisor/`, `migrations/`

### 2. Install fswatch (for daemon mode)

```bash
brew install fswatch
```

### 3. Start File Watcher Daemon (optional)

```bash
bash scripts/autopilot_daemon.sh
```

This will:
- Monitor `apps/`, `dev_supervisor/`, `migrations/`
- Auto-rebuild containers on file changes
- Run supervisor automatically
- Write status to `logs/autopilot_status.json`

## Usage Modes

### Automatic (Git Hook)

Just commit normally:

```bash
git commit -m "test change [autopilot]"
# Hook automatically runs supervisor
# If fails, commit is auto-reverted
```

Skip hook for a commit:

```bash
git commit -m "test change [skip-autopilot]"
```

### Manual

```bash
bash scripts/gs-dev.sh --autofix
```

### Daemon (Background)

```bash
bash scripts/autopilot_daemon.sh
# Runs in foreground, monitors file changes
# Press Ctrl+C to stop
```

## Logs

- **Git hook**: `logs/autopilot.log`
- **Daemon**: `logs/autopilot_daemon.log`
- **Status**: `logs/autopilot_status.json` (JSON format)

## Strict Criteria

Supervisor will **FAIL** if:

1. **Health endpoint**: Not 200 or not accessible
2. **Smoke test**: `intel_raw_items` count is 0 after smoke
3. **Pytest**: Any tests are skipped (SKIPPED)
4. **Any stage**: Returns FAIL status

**STABLE** only if:
- All 7 stages pass (OK)
- `intel_raw_items` count > 0
- No warnings that indicate failures

## Troubleshooting

**Hook not running:**
```bash
chmod +x .git/hooks/post-commit
git commit -m "test [autopilot]"
```

**Daemon not starting:**
```bash
brew install fswatch
bash scripts/autopilot_daemon.sh
```

**Check logs:**
```bash
tail -f logs/autopilot.log
tail -f logs/autopilot_daemon.log
cat logs/autopilot_status.json
```

## Acceptance Criteria

✅ After `git commit -m "test [autopilot]"`:
- Hook runs automatically
- Supervisor executes
- If FAIL → commit auto-reverted
- If STABLE → commit stays

✅ After file change in `apps/`:
- Daemon detects change
- Auto-rebuilds container
- Runs supervisor
- Updates status JSON

✅ No manual commands needed:
- Everything runs automatically
- Logs show what happened
- Status JSON shows current state
