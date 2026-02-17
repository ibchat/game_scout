#!/usr/bin/env bash
# Autopilot C++ LOCAL - File watcher daemon
# Monitors file changes and automatically runs supervisor
# For macOS: uses fswatch (install via: brew install fswatch)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

# Check if running on host
if [ -f "/.dockerenv" ] || [ "${IN_DOCKER:-}" = "1" ]; then
    echo "❌ This script must be run on the host, not inside a container."
    exit 2
fi

# Check for fswatch (macOS file watcher)
if ! command -v fswatch &> /dev/null; then
    echo "❌ fswatch not found. Install via: brew install fswatch"
    echo "   Or run autopilot manually: bash scripts/gs-dev.sh --autofix"
    exit 1
fi

# Create logs directory
mkdir -p "$PROJECT_ROOT/logs"

# Status file (JSON)
STATUS_FILE="$PROJECT_ROOT/logs/autopilot_status.json"
LOG_FILE="$PROJECT_ROOT/logs/autopilot_daemon.log"

# Function to update status JSON
update_status() {
    local status=$1
    local message=$2
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    
    cat > "$STATUS_FILE" <<EOF
{
  "status": "$status",
  "message": "$message",
  "last_check": "$timestamp",
  "pid": $$
}
EOF
}

# Function to log
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log "🚀 Autopilot Daemon starting..."
log "Watching: apps/ dev_supervisor/ migrations/"

update_status "watching" "Monitoring file changes"

# Directories to watch
WATCH_DIRS=(
    "$PROJECT_ROOT/apps"
    "$PROJECT_ROOT/dev_supervisor"
    "$PROJECT_ROOT/migrations"
    "$PROJECT_ROOT/scripts/gs-dev.sh"
    "$PROJECT_ROOT/scripts/verify_autopilot.sh"
)

# Debounce: wait 2 seconds after last change before triggering
DEBOUNCE_SECONDS=2
LAST_CHANGE=0
BUILD_IN_PROGRESS=false

# Function to run supervisor
run_supervisor() {
    if [ "$BUILD_IN_PROGRESS" = true ]; then
        log "⏭️  Skipping: build already in progress"
        return
    fi
    
    BUILD_IN_PROGRESS=true
    update_status "building" "Rebuilding containers and running supervisor"
    
    log "📦 File change detected, rebuilding..."
    
    # Rebuild api container
    if docker compose build api >> "$LOG_FILE" 2>&1; then
        log "✅ Build successful"
    else
        log "❌ Build failed"
        update_status "error" "Docker build failed"
        BUILD_IN_PROGRESS=false
        return
    fi
    
    # Restart services
    docker compose up -d >> "$LOG_FILE" 2>&1
    
    # Wait for services
    sleep 5
    
    # Run supervisor
    log "🔍 Running supervisor..."
    update_status "running" "Running dev supervisor"
    
    if bash scripts/gs-dev.sh --autofix >> "$LOG_FILE" 2>&1; then
        log "✅ Supervisor: STABLE"
        update_status "stable" "All checks passed"
    else
        log "❌ Supervisor: FAILED"
        update_status "failed" "Supervisor checks failed - see logs"
    fi
    
    BUILD_IN_PROGRESS=false
}

# Trap signals
trap 'log "🛑 Autopilot Daemon stopping..."; update_status "stopped" "Daemon stopped"; exit 0' INT TERM

# Start watching
log "👀 Watching for file changes..."
log "Press Ctrl+C to stop"

fswatch -o "${WATCH_DIRS[@]}" | while read -r event; do
    CURRENT_TIME=$(date +%s)
    
    # Debounce: only trigger if no changes for DEBOUNCE_SECONDS
    if [ $((CURRENT_TIME - LAST_CHANGE)) -ge $DEBOUNCE_SECONDS ]; then
        LAST_CHANGE=$CURRENT_TIME
        run_supervisor
    else
        LAST_CHANGE=$CURRENT_TIME
    fi
done
