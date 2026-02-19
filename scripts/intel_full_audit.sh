#!/bin/bash
# Intel Full Audit Script
# One-command audit that checks everything and prints actionable output

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}✓${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

log_error() {
    echo -e "${RED}✗${NC} $1"
}

log_section() {
    echo ""
    echo "=== $1 ==="
}

# Check if running in container
IN_CONTAINER=${IN_CONTAINER:-false}
API_URL=${API_URL:-http://localhost:8000}

log_section "1. Docker Compose Sanity"
if command -v docker &> /dev/null && docker compose ps &> /dev/null; then
    if docker compose ps | grep -q "Up"; then
        log_info "Docker containers are running"
    else
        log_error "Docker containers are not running"
        exit 1
    fi
else
    log_warn "Docker not available, skipping container check"
fi

log_section "2. Alembic Current Revision"
if [ "$IN_CONTAINER" = true ]; then
    alembic_current=$(python3 << 'PYTHON_EOF'
import os
import sys
try:
    from alembic.config import Config
    from alembic import command
    from alembic.script import ScriptDirectory
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import create_engine
    
    # Get DB URL from env
    db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@postgres:5432/game_scout')
    engine = create_engine(db_url)
    
    with engine.connect() as conn:
        context = MigrationContext.configure(conn)
        current_rev = context.get_current_revision()
        print(current_rev if current_rev else "none")
except Exception as e:
    print(f"error: {str(e)}")
PYTHON_EOF
)
else
    alembic_current=$(docker compose exec -T api alembic current 2>&1 | grep -oP '^\w+' | head -1 || echo "error")
fi

if [ "$alembic_current" != "error" ] && [ -n "$alembic_current" ]; then
    log_info "Alembic current: $alembic_current"
    if [ "$alembic_current" != "017_created_at_publish_log" ]; then
        log_warn "Expected head: 017_created_at_publish_log, got: $alembic_current"
        log_warn "Run: docker compose exec api alembic upgrade head"
    fi
else
    log_error "Cannot get alembic current revision"
fi

log_section "3. Intel Health Check"
health_result=$(curl -sS "${API_URL}/api/v1/intel/health" 2>&1 || echo '{"error": "curl failed"}')
health_enabled=$(echo "$health_result" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('enabled', False))" 2>/dev/null || echo "false")
health_db=$(echo "$health_result" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('db_ok', False))" 2>/dev/null || echo "false")
health_telegram=$(echo "$health_result" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('telegram_ok', False))" 2>/dev/null || echo "false")

if [ "$health_enabled" = "true" ]; then
    log_info "Intel enabled: true"
else
    log_error "Intel enabled: false"
fi

if [ "$health_db" = "true" ]; then
    log_info "DB OK: true"
else
    log_error "DB OK: false"
fi

if [ "$health_telegram" = "true" ]; then
    log_info "Telegram OK: true"
else
    log_warn "Telegram OK: false (may be expected if bot token not set)"
fi

log_section "4. Debug Full State"
debug_result=$(curl -sS "${API_URL}/api/v1/intel/debug/full_state" 2>&1 || echo '{"error": "curl failed"}')
debug_status=$(echo "$debug_result" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('status', 'error'))" 2>/dev/null || echo "error")
debug_errors=$(echo "$debug_result" | python3 -c "import sys, json; data=json.load(sys.stdin); errors=data.get('errors', []); print(len(errors))" 2>/dev/null || echo "0")

if [ "$debug_status" = "ok" ]; then
    log_info "Debug endpoint status: ok"
    sources_enabled=$(echo "$debug_result" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('sources_enabled', 0))" 2>/dev/null || echo "0")
    extracted_at_exists=$(echo "$debug_result" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('extracted_at_exists', False))" 2>/dev/null || echo "false")
    log_info "Sources enabled: $sources_enabled"
    if [ "$extracted_at_exists" = "true" ]; then
        log_info "extracted_at column exists: true"
    else
        log_error "extracted_at column missing - run migration 016"
    fi
elif [ "$debug_status" = "partial" ]; then
    log_warn "Debug endpoint status: partial (errors: $debug_errors)"
    echo "$debug_result" | python3 -c "import sys, json; data=json.load(sys.stdin); [print(f'  - {e}') for e in data.get('errors', [])]" 2>/dev/null || true
else
    log_error "Debug endpoint failed"
    echo "$debug_result" | head -20
fi

log_section "5. Pipeline Dry Run"
dry_run_result=$(curl -sS -X POST "${API_URL}/api/v1/intel/pipeline/run" \
    -H "Content-Type: application/json" \
    -d '{"dry_run": true}' \
    --max-time 300 2>&1 || echo '{"error": "curl failed"}')

dry_run_collect=$(echo "$dry_run_result" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('collect_stage_executed', False))" 2>/dev/null || echo "false")
dry_run_sources=$(echo "$dry_run_result" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('sources_used', 0))" 2>/dev/null || echo "0")
dry_run_collected=$(echo "$dry_run_result" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('collected', 0))" 2>/dev/null || echo "0")

if [ "$dry_run_collect" = "true" ]; then
    log_info "Collect stage executed: true"
else
    log_error "Collect stage executed: false"
fi

if [ "$dry_run_sources" -gt 0 ]; then
    log_info "Sources used: $dry_run_sources"
else
    log_error "Sources used: 0"
fi

log_info "Collected: $dry_run_collected"

log_section "6. Pipeline Real Run (if eligible > 0)"
eligible_count=$(echo "$dry_run_result" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('eligible_count', 0))" 2>/dev/null || echo "0")

if [ "$eligible_count" -gt 0 ]; then
    log_info "Eligible items found: $eligible_count, running real pipeline..."
    real_run_result=$(curl -sS -X POST "${API_URL}/api/v1/intel/pipeline/run" \
        -H "Content-Type: application/json" \
        -d '{"dry_run": false}' \
        --max-time 300 2>&1 || echo '{"error": "curl failed"}')
    
    real_published=$(echo "$real_run_result" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('published', 0))" 2>/dev/null || echo "0")
    real_reason=$(echo "$real_run_result" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('published_reason', 'unknown'))" 2>/dev/null || echo "unknown")
    
    log_info "Published: $real_published"
    log_info "Published reason: $real_reason"
else
    log_info "No eligible items, skipping real run"
fi

log_section "7. Last 10 Publish Logs"
if [ "$IN_CONTAINER" = true ]; then
    publish_logs=$(python3 << 'PYTHON_EOF'
import os
import sys
import json
from sqlalchemy import create_engine, text

try:
    db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@postgres:5432/game_scout')
    engine = create_engine(db_url)
    
    with engine.connect() as conn:
        # Try created_at first, fallback to published_at
        try:
            result = conn.execute(text("""
                SELECT id, event_id, created_at, published_at, status, error
                FROM intel_publish_log
                ORDER BY COALESCE(created_at, published_at) DESC
                LIMIT 10
            """))
        except:
            result = conn.execute(text("""
                SELECT id, event_id, published_at, status, error
                FROM intel_publish_log
                ORDER BY published_at DESC
                LIMIT 10
            """))
        
        rows = result.fetchall()
        if rows:
            print(json.dumps([dict(row._mapping) for row in rows], default=str))
        else:
            print("[]")
except Exception as e:
    print(json.dumps({"error": str(e)}))
PYTHON_EOF
)
else
    publish_logs=$(docker compose exec -T postgres psql -U postgres -d game_scout -t -c "
        SELECT json_agg(row_to_json(t))
        FROM (
            SELECT id, event_id, COALESCE(created_at, published_at) as timestamp, status, error
            FROM intel_publish_log
            ORDER BY COALESCE(created_at, published_at) DESC
            LIMIT 10
        ) t;
    " 2>&1 | grep -v "^$" || echo "[]")
fi

if [ "$publish_logs" != "[]" ] && [ -n "$publish_logs" ]; then
    echo "$publish_logs" | python3 -c "import sys, json; [print(f\"  {i+1}. {r.get('status', 'unknown')} - {r.get('timestamp', 'N/A')}\") for i, r in enumerate(json.load(sys.stdin)[:5])]" 2>/dev/null || log_warn "Cannot parse publish logs"
else
    log_warn "No publish logs found"
fi

log_section "Summary"
echo ""
if [ "$debug_status" = "ok" ] && [ "$dry_run_collect" = "true" ] && [ "$dry_run_sources" -gt 0 ]; then
    log_info "✓ All checks passed"
    exit 0
else
    log_error "✗ Some checks failed - see details above"
    exit 1
fi
