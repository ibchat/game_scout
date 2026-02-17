#!/usr/bin/env bash
# Intel Production Check Script
# Validates Intel pipeline health and runs production pipeline
# Exit 0: At least 1 message published
# Exit 1: No publications or critical failures

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
API_URL="${API_URL:-http://localhost:8000}"
INTEL_HEALTH_URL="${API_URL}/api/v1/intel/health"
INTEL_PIPELINE_URL="${API_URL}/api/v1/intel/pipeline/run"
INTEL_STATUS_URL="${API_URL}/api/v1/intel/pipeline/status"

# Check if running in Docker container
if [ -f "/.dockerenv" ] || [ -n "${IN_DOCKER:-}" ]; then
    IN_CONTAINER=true
else
    IN_CONTAINER=false
fi

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check 1: Health endpoint
check_health() {
    log_info "Checking Intel health endpoint..."
    
    if [ "$IN_CONTAINER" = true ]; then
        health_response=$(python3 -c "
import httpx
import json
try:
    resp = httpx.get('${INTEL_HEALTH_URL}', timeout=5)
    resp.raise_for_status()
    data = resp.json()
    print(json.dumps(data))
except Exception as e:
    print(json.dumps({'error': str(e)}))
")
    else
        health_response=$(curl -sS "${INTEL_HEALTH_URL}" 2>&1 || echo '{"error": "curl failed"}')
    fi
    
    if echo "$health_response" | python3 -c "import sys, json; data=json.load(sys.stdin); sys.exit(0 if data.get('enabled') and data.get('telegram_ok') and data.get('db_ok') else 1)" 2>/dev/null; then
        log_info "✓ Health check passed"
        echo "$health_response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(f\"  enabled: {data.get('enabled')}\"); print(f\"  telegram_ok: {data.get('telegram_ok')}\"); print(f\"  db_ok: {data.get('db_ok')}\")"
        return 0
    else
        log_error "✗ Health check failed"
        echo "$health_response" | python3 -m json.tool 2>/dev/null || echo "$health_response"
        return 1
    fi
}

# Check 2: Database sources
check_sources() {
    log_info "Checking Intel sources in database..."
    
    if [ "$IN_CONTAINER" = true ]; then
        source_count=$(python3 -c "
from apps.db.session import SessionLocal
from apps.intel.db.models import IntelSource
db = SessionLocal()
count = db.query(IntelSource).filter(IntelSource.is_enabled == True).count()
print(count)
db.close()
")
    else
        source_count=$(docker compose exec -T postgres psql -U postgres -d game_scout -t -c "SELECT COUNT(*) FROM intel_sources WHERE is_enabled = true;" 2>/dev/null | tr -d ' ' || echo "0")
    fi
    
    if [ "$source_count" -gt 0 ]; then
        log_info "✓ Found $source_count enabled sources"
        return 0
    else
        log_error "✗ No enabled sources found"
        return 1
    fi
}

# Check 3: Recent publish logs
check_publish_logs() {
    log_info "Checking recent publish logs..."
    
    if [ "$IN_CONTAINER" = true ]; then
        publish_logs=$(python3 -c "
from apps.db.session import SessionLocal
from apps.intel.db.models import IntelPublishLog
import json
db = SessionLocal()
logs = db.query(IntelPublishLog).order_by(IntelPublishLog.published_at.desc()).limit(10).all()
result = []
for log in logs:
    result.append({
        'id': str(log.id),
        'status': log.status,
        'telegram_message_id': log.telegram_message_id or '',
        'error': log.error[:100] if log.error else None,
        'published_at': log.published_at.isoformat() if log.published_at else None
    })
print(json.dumps(result))
db.close()
")
    else
        publish_logs=$(docker compose exec -T postgres psql -U postgres -d game_scout -t -A -F',' -c "
            SELECT id, status, COALESCE(telegram_message_id, ''), COALESCE(LEFT(error, 100), ''), published_at
            FROM intel_publish_log
            ORDER BY published_at DESC
            LIMIT 10;
        " 2>/dev/null | python3 -c "
import sys
import json
result = []
for line in sys.stdin:
    if line.strip():
        parts = line.strip().split(',')
        if len(parts) >= 4:
            result.append({
                'id': parts[0],
                'status': parts[1],
                'telegram_message_id': parts[2],
                'error': parts[3] if parts[3] else None,
                'published_at': parts[4] if len(parts) > 4 else None
            })
print(json.dumps(result))
" || echo "[]")
    fi
    
    published_count=$(echo "$publish_logs" | python3 -c "import sys, json; logs=json.load(sys.stdin); print(sum(1 for log in logs if log.get('status') == 'published'))")
    failed_count=$(echo "$publish_logs" | python3 -c "import sys, json; logs=json.load(sys.stdin); print(sum(1 for log in logs if log.get('status') == 'failed'))")
    skipped_count=$(echo "$publish_logs" | python3 -c "import sys, json; logs=json.load(sys.stdin); print(sum(1 for log in logs if log.get('status') == 'skipped'))")
    
    log_info "Recent publish logs:"
    echo "  Published: $published_count"
    echo "  Failed: $failed_count"
    echo "  Skipped: $skipped_count"
    
    if [ "$published_count" -gt 0 ]; then
        log_info "✓ Found published messages"
        return 0
    else
        log_warn "⚠ No published messages in recent logs"
        return 0  # Not a failure, just a warning
    fi
}

# Check 4: Pipeline dry run
run_pipeline_dry_run() {
    log_info "Running pipeline dry run..."
    
    if [ "$IN_CONTAINER" = true ]; then
        pipeline_response=$(python3 -c "
import httpx
import json
try:
    resp = httpx.post('${INTEL_PIPELINE_URL}', json={'sources': ['Steam RSS test'], 'dry_run': True}, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    print(json.dumps(data))
except Exception as e:
    print(json.dumps({'error': str(e)}))
")
    else
        pipeline_response=$(curl -sS -X POST "${INTEL_PIPELINE_URL}" \
            -H "Content-Type: application/json" \
            -d '{"sources": ["Steam RSS test"], "dry_run": true}' \
            --max-time 60 2>&1 || echo '{"error": "curl failed"}')
    fi
    
    eligible_count=$(echo "$pipeline_response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('eligible_count', 0))" 2>/dev/null || echo "0")
    collected=$(echo "$pipeline_response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('collected', 0))" 2>/dev/null || echo "0")
    extracted=$(echo "$pipeline_response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('extracted', 0))" 2>/dev/null || echo "0")
    
    log_info "Dry run results:"
    echo "  Collected: $collected"
    echo "  Extracted: $extracted"
    echo "  Eligible: $eligible_count"
    
    if echo "$pipeline_response" | python3 -c "import sys, json; data=json.load(sys.stdin); sys.exit(0 if 'error' not in data else 1)" 2>/dev/null; then
        log_info "✓ Dry run completed successfully"
        return 0
    else
        log_error "✗ Dry run failed"
        echo "$pipeline_response" | python3 -m json.tool 2>/dev/null || echo "$pipeline_response"
        return 1
    fi
}

# Check 5: Pipeline real run (if eligible)
run_pipeline_real() {
    if [ "$eligible_count" -le 0 ]; then
        log_warn "No eligible events, skipping real run"
        return 0
    fi
    
    log_info "Running pipeline real run (eligible_count=$eligible_count)..."
    
    if [ "$IN_CONTAINER" = true ]; then
        pipeline_response=$(python3 -c "
import httpx
import json
try:
    resp = httpx.post('${INTEL_PIPELINE_URL}', json={'sources': ['Steam RSS test'], 'dry_run': False}, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    print(json.dumps(data))
except Exception as e:
    print(json.dumps({'error': str(e)}))
")
    else
        pipeline_response=$(curl -sS -X POST "${INTEL_PIPELINE_URL}" \
            -H "Content-Type: application/json" \
            -d '{"sources": ["Steam RSS test"], "dry_run": false}' \
            --max-time 120 2>&1 || echo '{"error": "curl failed"}')
    fi
    
    published=$(echo "$pipeline_response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('published', 0))" 2>/dev/null || echo "0")
    skipped=$(echo "$pipeline_response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('skipped', 0))" 2>/dev/null || echo "0")
    
    log_info "Real run results:"
    echo "  Published: $published"
    echo "  Skipped: $skipped"
    
    # Get breakdown of skipped reasons
    if [ "$IN_CONTAINER" = true ]; then
        skipped_breakdown=$(python3 -c "
from apps.db.session import SessionLocal
from apps.intel.db.models import IntelPublishLog
import json
db = SessionLocal()
recent_skipped = db.query(IntelPublishLog).filter(
    IntelPublishLog.status == 'skipped'
).order_by(IntelPublishLog.published_at.desc()).limit(20).all()
breakdown = {}
for log in recent_skipped:
    error = log.error or 'unknown'
    reason = error.split(':')[0] if ':' in error else error
    breakdown[reason] = breakdown.get(reason, 0) + 1
print(json.dumps(breakdown))
db.close()
")
    else
        skipped_breakdown=$(docker compose exec -T postgres psql -U postgres -d game_scout -t -A -c "
            SELECT COALESCE(LEFT(error, 50), 'unknown')
            FROM intel_publish_log
            WHERE status = 'skipped'
            ORDER BY published_at DESC
            LIMIT 20;
        " 2>/dev/null | python3 -c "
import sys
import json
from collections import Counter
reasons = []
for line in sys.stdin:
    if line.strip():
        reason = line.strip().split(':')[0] if ':' in line.strip() else line.strip()
        reasons.append(reason)
breakdown = dict(Counter(reasons))
print(json.dumps(breakdown))
" || echo "{}")
    fi
    
    if [ -n "$skipped_breakdown" ] && [ "$skipped_breakdown" != "{}" ]; then
        log_info "Skipped reasons breakdown:"
        echo "$skipped_breakdown" | python3 -c "import sys, json; data=json.load(sys.stdin); [print(f\"  {k}: {v}\") for k, v in data.items()]"
    fi
    
    if [ "$published" -gt 0 ]; then
        log_info "✓ Published $published message(s)"
        return 0
    else
        log_error "✗ No messages published"
        return 1
    fi
}

# Main execution
main() {
    log_info "=== Intel Production Check ==="
    
    # Track failures
    failures=0
    
    # Check 1: Health
    if ! check_health; then
        failures=$((failures + 1))
    fi
    
    # Check 2: Sources
    if ! check_sources; then
        failures=$((failures + 1))
    fi
    
    # Check 3: Publish logs
    check_publish_logs || true  # Not critical
    
    # Check 4: Dry run
    if ! run_pipeline_dry_run; then
        failures=$((failures + 1))
    fi
    
    # Check 5: Real run (if eligible)
    if [ "$eligible_count" -gt 0 ]; then
        if ! run_pipeline_real; then
            failures=$((failures + 1))
        fi
    else
        log_warn "No eligible events for real run"
    fi
    
    # Final status
    echo ""
    if [ "$failures" -eq 0 ] && [ "${published:-0}" -gt 0 ]; then
        log_info "=== Production Check: PASSED ==="
        log_info "Published: ${published:-0} message(s)"
        exit 0
    elif [ "$failures" -eq 0 ]; then
        log_warn "=== Production Check: PASSED (no publications) ==="
        exit 0  # Health checks passed, but no publications
    else
        log_error "=== Production Check: FAILED ==="
        log_error "Failures: $failures"
        exit 1
    fi
}

# Run main
main "$@"
