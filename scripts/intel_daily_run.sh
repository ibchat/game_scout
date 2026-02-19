#!/bin/bash
# Intel Daily Run Script
# One-button daily run: seed (optional) → run pipeline → show results

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running in container
if [ -f /.dockerenv ] || [ -n "$DOCKER_CONTAINER" ]; then
    IN_CONTAINER=true
    API_URL="${API_URL:-http://localhost:8000}"
else
    IN_CONTAINER=false
    API_URL="${API_URL:-http://localhost:8000}"
fi

log_info "=== Intel Daily Run ==="
log_info "Running pipeline with immediate publishing..."

# Step 1: Optional seeding (if enabled sources < 30)
if [ "$IN_CONTAINER" = true ]; then
    enabled_count=$(python3 << 'PYTHON_EOF'
from apps.db.session import SessionLocal
from apps.intel.db.models import IntelSource
db = SessionLocal()
count = db.query(IntelSource).filter(IntelSource.is_enabled == True).count()
print(count)
db.close()
PYTHON_EOF
)
else
    enabled_count=$(docker compose exec -T postgres psql -U postgres -d game_scout -t -A -c "SELECT COUNT(*) FROM intel_sources WHERE is_enabled = true;" 2>/dev/null || echo "0")
fi

if [ "${enabled_count:-0}" -lt 30 ]; then
    log_warn "Only ${enabled_count} enabled sources found, seeding global sources..."
    if [ "$IN_CONTAINER" = true ]; then
        seed_result=$(python3 << 'PYTHON_EOF'
import httpx
import json
import os
url = os.getenv('API_URL', 'http://localhost:8000')
try:
    resp = httpx.post(f"{url}/api/v1/intel/sources/seed_global", timeout=30)
    resp.raise_for_status()
    data = resp.json()
    print(json.dumps(data))
except Exception as e:
    print(json.dumps({'error': str(e)}))
PYTHON_EOF
)
    else
        seed_result=$(curl -sS -X POST "${API_URL}/api/v1/intel/sources/seed_global" --max-time 30 2>&1 || echo '{"error": "curl failed"}')
    fi
    
    if echo "$seed_result" | python3 -c "import sys, json; data=json.load(sys.stdin); sys.exit(0 if 'error' not in data else 1)" 2>/dev/null; then
        log_info "✓ Sources seeded successfully"
    else
        log_warn "⚠ Seeding failed or skipped"
    fi
fi

# Step 2: Run pipeline (real run, not dry_run)
log_info "Running pipeline (real run)..."

# ARCHITECTURE FIX: Don't pass sources: [] - let pipeline use all active sources
if [ "$IN_CONTAINER" = true ]; then
    pipeline_result=$(python3 << 'PYTHON_EOF'
import httpx
import json
import os
url = os.getenv('API_URL', 'http://localhost:8000')
try:
    # Don't pass sources - pipeline will use all active sources
    resp = httpx.post(f"{url}/api/v1/intel/pipeline/run", json={'dry_run': False}, timeout=300)
    resp.raise_for_status()
    data = resp.json()
    print(json.dumps(data))
except Exception as e:
    print(json.dumps({'error': str(e)}))
PYTHON_EOF
)
else
    # Don't pass sources - pipeline will use all active sources
    pipeline_result=$(curl -sS -X POST "${API_URL}/api/v1/intel/pipeline/run" \
        -H "Content-Type: application/json" \
        -d '{"dry_run": false}' \
        --max-time 300 2>&1 || echo '{"error": "curl failed"}')
fi

# Parse results (ARCHITECTURE FIX: Check collect_stage_executed)
# Fix: Convert Python boolean True/False to lowercase true/false for bash comparison
collect_stage_executed=$(echo "$pipeline_result" | python3 -c "import sys, json; data=json.load(sys.stdin); print(str(data.get('collect_stage_executed', False)).lower())" 2>/dev/null || echo "false")
collect_reason=$(echo "$pipeline_result" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('collect_reason', 'unknown'))" 2>/dev/null || echo "unknown")
sources_used=$(echo "$pipeline_result" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('sources_used', 0))" 2>/dev/null || echo "0")
collected=$(echo "$pipeline_result" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('collected', 0))" 2>/dev/null || echo "0")
extracted=$(echo "$pipeline_result" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('extracted', 0))" 2>/dev/null || echo "0")
eligible=$(echo "$pipeline_result" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('eligible_count', 0))" 2>/dev/null || echo "0")
published=$(echo "$pipeline_result" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('published', 0))" 2>/dev/null || echo "0")
skipped=$(echo "$pipeline_result" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('skipped', 0))" 2>/dev/null || echo "0")

log_info "=== Pipeline Results ==="
echo "  Collect stage executed: $collect_stage_executed"
echo "  Collect reason: $collect_reason"
echo "  Sources used: $sources_used"
echo "  Collected: $collected"
echo "  Extracted: $extracted"
echo "  Eligible: $eligible"
echo "  Published: $published"
echo "  Skipped: $skipped"

# ARCHITECTURE FIX: Validate collect stage executed
if [ "$collect_stage_executed" != "true" ]; then
    log_error "✗ CRITICAL: Collect stage did NOT execute!"
    log_error "  Reason: $collect_reason"
    exit 1
fi

# ARCHITECTURE FIX: Validate sources were used
if [ "$sources_used" -eq 0 ]; then
    log_error "✗ CRITICAL: No sources used for collection!"
    exit 1
fi

# Show skip breakdown if available
skip_breakdown=$(echo "$pipeline_result" | python3 -c "import sys, json; data=json.load(sys.stdin); print(json.dumps(data.get('skip_breakdown', {})))" 2>/dev/null || echo "{}")
if [ -n "$skip_breakdown" ] && [ "$skip_breakdown" != "{}" ]; then
    log_info "Skip breakdown:"
    echo "$skip_breakdown" | python3 -c "import sys, json; data=json.load(sys.stdin); [print(f\"  {k}: {v}\") for k, v in sorted(data.items(), key=lambda x: x[1], reverse=True) if v > 0]" 2>/dev/null || true
fi

# Step 3: Show last 5 publish logs
log_info "=== Last 5 Publications ==="

if [ "$IN_CONTAINER" = true ]; then
    recent_logs=$(python3 << 'PYTHON_EOF'
from apps.db.session import SessionLocal
from apps.intel.db.models import IntelPublishLog
import json
db = SessionLocal()
logs = db.query(IntelPublishLog).order_by(IntelPublishLog.published_at.desc()).limit(5).all()
result = []
for log in logs:
    result.append({
        'id': str(log.id),
        'status': log.status,
        'message_id': log.telegram_message_id or 'N/A',
        'published_at': log.published_at.isoformat() if log.published_at else None,
        'error': log.error[:100] if log.error else None
    })
print(json.dumps(result))
db.close()
PYTHON_EOF
)
else
    recent_logs=$(docker compose exec -T postgres psql -U postgres -d game_scout -t -A -c "
        SELECT json_agg(json_build_object(
            'id', id::text,
            'status', status,
            'message_id', COALESCE(telegram_message_id, 'N/A'),
            'published_at', published_at,
            'error', LEFT(error, 100)
        ))
        FROM (
            SELECT id, status, telegram_message_id, published_at, error
            FROM intel_publish_log
            ORDER BY published_at DESC
            LIMIT 5
        ) t;
    " 2>/dev/null | python3 -c "import sys, json; data=json.load(sys.stdin); print(json.dumps(data))" || echo "[]")
fi

if [ -n "$recent_logs" ] && [ "$recent_logs" != "[]" ]; then
    echo "$recent_logs" | python3 -c "import sys, json; logs=json.load(sys.stdin); [print(f\"  [{log.get('status', 'N/A')}] {log.get('published_at', 'N/A')[:19]} - Message ID: {log.get('message_id', 'N/A')}\") for log in logs[:5]]" 2>/dev/null || true
else
    log_warn "No recent publications found"
fi

# Final status
if [ "$published" -gt 0 ]; then
    log_info "✓ Daily run completed: $published message(s) published"
    exit 0
else
    log_warn "⚠ Daily run completed but no messages published"
    if [ "$eligible" -gt 0 ]; then
        log_warn "  Eligible events exist but were skipped (check skip_breakdown above)"
    else
        log_warn "  No eligible events found"
    fi
    exit 0  # Don't fail, just warn
fi
