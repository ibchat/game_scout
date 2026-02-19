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

# Check 0: Daily schedule configuration
check_daily_schedule() {
    log_info "Checking daily schedule configuration..."
    
    if [ "$IN_CONTAINER" = true ]; then
        schedule_info=$(python3 << 'PYTHON_EOF'
import os
schedule_mode = os.getenv('INTEL_SCHEDULE_MODE', 'hourly')
daily_hour = os.getenv('INTEL_DAILY_RUN_HOUR', '9')
daily_tz = os.getenv('INTEL_DAILY_RUN_TZ', 'Europe/Madrid')
print(f"mode={schedule_mode}")
print(f"hour={daily_hour}")
print(f"tz={daily_tz}")
PYTHON_EOF
)
    else
        schedule_info=$(docker compose exec -T api python3 << 'PYTHON_EOF'
import os
schedule_mode = os.getenv('INTEL_SCHEDULE_MODE', 'hourly')
daily_hour = os.getenv('INTEL_DAILY_RUN_HOUR', '9')
daily_tz = os.getenv('INTEL_DAILY_RUN_TZ', 'Europe/Madrid')
print(f"mode={schedule_mode}")
print(f"hour={daily_hour}")
print(f"tz={daily_tz}")
PYTHON_EOF
)
    fi
    
    schedule_mode=$(echo "$schedule_info" | grep "mode=" | cut -d= -f2)
    daily_hour=$(echo "$schedule_info" | grep "hour=" | cut -d= -f2)
    daily_tz=$(echo "$schedule_info" | grep "tz=" | cut -d= -f2)
    
    if [ "$schedule_mode" = "daily" ]; then
        log_info "✓ Schedule mode: daily at ${daily_hour}:00 ${daily_tz}"
    else
        log_warn "⚠ Schedule mode: ${schedule_mode} (expected: daily)"
    fi
    
    # Check daily lock
    if [ "$IN_CONTAINER" = true ]; then
        lock_info=$(python3 << 'PYTHON_EOF'
from apps.intel.services.daily_lock import check_daily_lock
from datetime import datetime
from zoneinfo import ZoneInfo
import os

tz = ZoneInfo(os.getenv("INTEL_DAILY_RUN_TZ", "Europe/Madrid"))
today = datetime.now(tz).date()
lock_exists = check_daily_lock()

print(f"lock_exists={lock_exists}")
print(f"today={today.isoformat()}")
PYTHON_EOF
)
    else
        lock_info=$(docker compose exec -T api python3 << 'PYTHON_EOF'
from apps.intel.services.daily_lock import check_daily_lock
from datetime import datetime
from zoneinfo import ZoneInfo
import os

tz = ZoneInfo(os.getenv("INTEL_DAILY_RUN_TZ", "Europe/Madrid"))
today = datetime.now(tz).date()
lock_exists = check_daily_lock()

print(f"lock_exists={lock_exists}")
print(f"today={today.isoformat()}")
PYTHON_EOF
)
    fi
    
    lock_exists=$(echo "$lock_info" | grep "lock_exists=" | cut -d= -f2)
    today=$(echo "$lock_info" | grep "today=" | cut -d= -f2)
    
    if [ "$lock_exists" = "True" ]; then
        log_info "✓ Daily lock exists (run already executed today: ${today})"
    else
        log_info "ℹ Daily lock not found (run not executed today yet: ${today})"
    fi
    
    echo ""
}

# Check 1: Health endpoint
check_health() {
    log_info "Checking Intel health endpoint..."
    
    if [ "$IN_CONTAINER" = true ]; then
        health_response=$(python3 << PYTHON_EOF
import httpx
import json
import os
url = os.getenv('INTEL_HEALTH_URL', '${INTEL_HEALTH_URL}')
try:
    resp = httpx.get(url, timeout=5)
    resp.raise_for_status()
    data = resp.json()
    print(json.dumps(data))
except Exception as e:
    print(json.dumps({'error': str(e)}))
PYTHON_EOF
)
    else
        health_response=$(curl -sS "${INTEL_HEALTH_URL}" 2>&1 || echo '{"error": "curl failed"}')
    fi
    
    if echo "$health_response" | python3 -c "import sys, json; data=json.load(sys.stdin); sys.exit(0 if data.get('enabled') and data.get('telegram_ok') and data.get('db_ok') and data.get('translation_ok') else 1)" 2>/dev/null; then
        log_info "✓ Health check passed"
        echo "$health_response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(f\"  enabled: {data.get('enabled')}\"); print(f\"  telegram_ok: {data.get('telegram_ok')}\"); print(f\"  db_ok: {data.get('db_ok')}\"); print(f\"  translation_ok: {data.get('translation_ok')}\")"
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
        source_info=$(python3 << 'PYTHON_EOF'
from apps.db.session import SessionLocal
from apps.intel.db.models import IntelSource
import json
db = SessionLocal()
total = db.query(IntelSource).count()
enabled = db.query(IntelSource).filter(IntelSource.is_enabled == True).count()
result = {'total': total, 'enabled': enabled}
print(json.dumps(result))
db.close()
PYTHON_EOF
)
        source_count=$(echo "$source_info" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('enabled', 0))")
        total_sources=$(echo "$source_info" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('total', 0))")
    else
        source_count=$(docker compose exec -T postgres psql -U postgres -d game_scout -t -c "SELECT COUNT(*) FROM intel_sources WHERE is_enabled = true;" 2>/dev/null | tr -d ' ' || echo "0")
        total_sources=$(docker compose exec -T postgres psql -U postgres -d game_scout -t -c "SELECT COUNT(*) FROM intel_sources;" 2>/dev/null | tr -d ' ' || echo "0")
    fi
    
    log_info "Sources: $source_count enabled / $total_sources total"
    
    if [ "$source_count" -ge 30 ]; then
        log_info "✓ Found $source_count enabled sources (>= 30 required for high-noise mode)"
        return 0
    elif [ "$source_count" -gt 0 ]; then
        log_warn "⚠ Found $source_count enabled sources (recommend >= 30 for high-noise mode)"
        # Auto-fix: seed global sources if < 30
        if [ "$source_count" -lt 30 ]; then
            log_info "Auto-fixing: seeding global sources..."
            if [ "$IN_CONTAINER" = true ]; then
                seed_result=$(python3 << 'PYTHON_EOF'
import httpx
import json
import os
url = os.getenv('API_URL', 'http://localhost:8000') + '/api/v1/intel/sources/seed_global'
try:
    resp = httpx.post(url, timeout=30)
    data = resp.json()
    print(json.dumps(data))
except Exception as e:
    print(json.dumps({'error': str(e)}))
PYTHON_EOF
)
            else
                seed_result=$(curl -sS -X POST "${API_URL}/api/v1/intel/sources/seed_global" --max-time 30 2>&1 || echo '{"error": "curl failed"}')
            fi
            
            if echo "$seed_result" | python3 -c "import sys, json; data=json.load(sys.stdin); sys.exit(0 if data.get('status') == 'ok' else 1)" 2>/dev/null; then
                log_info "✓ Global sources seeded successfully"
                # Re-check count
                if [ "$IN_CONTAINER" = true ]; then
                    source_count=$(python3 << 'PYTHON_EOF'
from apps.db.session import SessionLocal
from apps.intel.db.models import IntelSource
db = SessionLocal()
count = db.query(IntelSource).filter(IntelSource.is_enabled == True).count()
print(count)
db.close()
PYTHON_EOF
)
                else
                    source_count=$(docker compose exec -T postgres psql -U postgres -d game_scout -t -c "SELECT COUNT(*) FROM intel_sources WHERE is_enabled = true;" 2>/dev/null | tr -d ' ' || echo "0")
                fi
                log_info "Updated source count: $source_count"
            else
                log_warn "Failed to seed global sources (non-critical)"
            fi
        fi
        return 0  # Not a failure, but warning
    else
        log_error "✗ No enabled sources found"
        return 1
    fi
}

# Check 3: Recent publish logs
check_publish_logs() {
    log_info "Checking recent publish logs..."
    
    if [ "$IN_CONTAINER" = true ]; then
        publish_logs=$(python3 << 'PYTHON_EOF'
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
PYTHON_EOF
)
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

# Check 4: Pipeline dry run (uses ALL active sources)
run_pipeline_dry_run() {
    log_info "Running pipeline dry run (all active sources)..."
    
    if [ "$IN_CONTAINER" = true ]; then
        pipeline_response=$(python3 << PYTHON_EOF
import httpx
import json
import os
url = os.getenv('INTEL_PIPELINE_URL', '${INTEL_PIPELINE_URL}')
try:
    # Empty sources list = use all active sources
    resp = httpx.post(url, json={'sources': [], 'dry_run': True}, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    print(json.dumps(data))
except Exception as e:
    print(json.dumps({'error': str(e)}))
PYTHON_EOF
)
    else
        pipeline_response=$(curl -sS -X POST "${INTEL_PIPELINE_URL}" \
            -H "Content-Type: application/json" \
            -d '{"sources": [], "dry_run": true}' \
            --max-time 120 2>&1 || echo '{"error": "curl failed"}')
    fi
    
    # ETAP 7: Enhanced diagnostics
    collect_stage_executed=$(echo "$pipeline_response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('collect_stage_executed', False))" 2>/dev/null || echo "false")
    eligible_count=$(echo "$pipeline_response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('eligible_count', 0))" 2>/dev/null || echo "0")
    collected=$(echo "$pipeline_response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('collected', 0))" 2>/dev/null || echo "0")
    extracted=$(echo "$pipeline_response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('extracted', 0))" 2>/dev/null || echo "0")
    relevant_count=$(echo "$pipeline_response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('relevant_count', 0))" 2>/dev/null || echo "0")
    translated_count=$(echo "$pipeline_response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('translated_count', 0))" 2>/dev/null || echo "0")
    sources_processed=$(echo "$pipeline_response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('sources_processed', 0))" 2>/dev/null || echo "0")
    raw_last_24h=$(echo "$pipeline_response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('raw_last_24h', 0))" 2>/dev/null || echo "0")
    extraction_ratio=$(echo "$pipeline_response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('extraction_ratio', 0))" 2>/dev/null || echo "0")
    zero_scores=$(echo "$pipeline_response" | python3 -c "import sys, json; data=json.load(sys.stdin); stats=data.get('scoring_stats', {}); print(stats.get('zero_scores', 0))" 2>/dev/null || echo "0")
    
    log_info "Dry run results:"
    echo "  Collect stage executed: $collect_stage_executed"
    echo "  Sources processed: $sources_processed"
    echo "  Collected: $collected"
    echo "  Raw last 24h: $raw_last_24h"
    echo "  Extracted: $extracted"
    echo "  Extraction ratio: ${extraction_ratio}%"
    echo "  Relevant: $relevant_count"
    echo "  Translated: $translated_count"
    echo "  Eligible: $eligible_count"
    echo "  Zero scores: $zero_scores"
    
    # ETAP 7: Validation checks
    if [ "$collect_stage_executed" != "true" ]; then
        log_error "✗ Collect stage not executed!"
        return 1
    fi
    
    if [ "$raw_last_24h" -eq 0 ]; then
        log_error "✗ No raw items in last 24h!"
        return 1
    fi
    
    EXTRACTION_OK=$(echo "$extraction_ratio" | python3 -c "import sys; ratio = float(sys.stdin.read().strip() or 0); print('1' if ratio >= 5.0 else '0')" 2>/dev/null || echo "0")
    if [ "$EXTRACTION_OK" != "1" ]; then
        log_warn "⚠ Extraction ratio < 5%: ${extraction_ratio}% (target: ≥5%)"
    fi
    
    if [ "$zero_scores" -gt 0 ]; then
        log_error "✗ Found $zero_scores events with score=0 (should be 0)"
        return 1
    fi
    
    # Calculate ratios
    if [ "$collected" -gt 0 ]; then
        relevance_ratio=$(python3 -c "print(f\"{($relevant_count / $collected * 100):.1f}%\")" 2>/dev/null || echo "N/A")
        echo "  Relevance ratio: $relevance_ratio"
    fi
    if [ "$relevant_count" -gt 0 ]; then
        translation_ratio=$(python3 -c "print(f\"{($translated_count / $relevant_count * 100):.1f}%\")" 2>/dev/null || echo "N/A")
        echo "  Translation ratio: $translation_ratio"
    fi
    if [ "$relevant_count" -gt 0 ]; then
        eligible_ratio=$(python3 -c "print(f\"{($eligible_count / $relevant_count * 100):.1f}%\")" 2>/dev/null || echo "N/A")
        echo "  Eligible ratio: $eligible_ratio"
    fi
    
    # Show items per source
    items_per_source=$(echo "$pipeline_response" | python3 -c "import sys, json; data=json.load(sys.stdin); items=data.get('items_per_source', {}); [print(f\"    {k}: {v}\") for k, v in sorted(items.items(), key=lambda x: x[1], reverse=True)[:10]]" 2>/dev/null || echo "")
    if [ -n "$items_per_source" ]; then
        log_info "Top sources by items collected:"
        echo "$items_per_source"
    fi
    
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
        pipeline_response=$(python3 << PYTHON_EOF
import httpx
import json
import os
url = os.getenv('INTEL_PIPELINE_URL', '${INTEL_PIPELINE_URL}')
try:
    # Empty sources list = use all active sources
    resp = httpx.post(url, json={'sources': [], 'dry_run': False}, timeout=180)
    resp.raise_for_status()
    data = resp.json()
    print(json.dumps(data))
except Exception as e:
    print(json.dumps({'error': str(e)}))
PYTHON_EOF
)
    else
        pipeline_response=$(curl -sS -X POST "${INTEL_PIPELINE_URL}" \
            -H "Content-Type: application/json" \
            -d '{"sources": [], "dry_run": false}' \
            --max-time 180 2>&1 || echo '{"error": "curl failed"}')
    fi
    
    published=$(echo "$pipeline_response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('published', 0))" 2>/dev/null || echo "0")
    skipped=$(echo "$pipeline_response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('skipped', 0))" 2>/dev/null || echo "0")
    eligible=$(echo "$pipeline_response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('eligible_count', 0))" 2>/dev/null || echo "0")
    skip_reasons=$(echo "$pipeline_response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(json.dumps(data.get('skip_reasons', {})))" 2>/dev/null || echo "{}")
    error_breakdown=$(echo "$pipeline_response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(json.dumps(data.get('error_breakdown', {})))" 2>/dev/null || echo "{}")
    
    log_info "Real run results:"
    echo "  Published: $published"
    echo "  Skipped: $skipped"
    echo "  Eligible: $eligible"
    
    # ETAP 7: Show skip reasons breakdown
    if [ -n "$skip_reasons" ] && [ "$skip_reasons" != "{}" ]; then
        log_info "Skip reasons breakdown:"
        echo "$skip_reasons" | python3 -c "import sys, json; data=json.load(sys.stdin); [print(f\"  {k}: {v}\") for k, v in sorted(data.items(), key=lambda x: x[1], reverse=True) if v > 0]" 2>/dev/null || true
    fi
    
    # ETAP 7: Show source error breakdown
    if [ -n "$error_breakdown" ] && [ "$error_breakdown" != "{}" ]; then
        log_info "Source error breakdown:"
        echo "$error_breakdown" | python3 -c "import sys, json; data=json.load(sys.stdin); [print(f\"  {k}: {len(v)} sources\") for k, v in data.items()]" 2>/dev/null || true
    fi
    
    # Get breakdown of skipped reasons
    if [ "$IN_CONTAINER" = true ]; then
        skipped_breakdown=$(python3 << 'PYTHON_EOF'
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
PYTHON_EOF
)
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
    
    # Parse and display skipped breakdown
    if [ -n "$skipped_breakdown" ] && [ "$skipped_breakdown" != "{}" ]; then
        breakdown_dict=$(echo "$skipped_breakdown" | python3 -c "import sys, json; data=json.load(sys.stdin); print(json.dumps(data.get('breakdown', {})))" 2>/dev/null || echo "$skipped_breakdown")
        
        if [ -n "$breakdown_dict" ] && [ "$breakdown_dict" != "{}" ]; then
            log_info "Top skip reasons (last 24h):"
            echo "$breakdown_dict" | python3 -c "import sys, json; data=json.load(sys.stdin); sorted_items=sorted(data.items(), key=lambda x: x[1], reverse=True)[:5]; [print(f\"  {k}: {v}\") for k, v in sorted_items]"
        fi
        
        # Show recent logs if available
        recent_logs=$(echo "$skipped_breakdown" | python3 -c "import sys, json; data=json.load(sys.stdin); logs=data.get('recent_logs', []); print(json.dumps(logs[:5]))" 2>/dev/null || echo "[]")
        if [ -n "$recent_logs" ] && [ "$recent_logs" != "[]" ]; then
            log_info "Recent skipped events (sample):"
            echo "$recent_logs" | python3 -c "import sys, json; logs=json.load(sys.stdin); [print(f\"  Event {log.get('event_id', 'N/A')[:8]}: {log.get('error', 'N/A')[:60]} (score: {log.get('event_info', {}).get('significance_score', 'N/A')})\") for log in logs[:5]]" 2>/dev/null || true
        fi
    fi
    
    if [ "$published" -gt 0 ]; then
        log_info "✓ Published $published message(s)"
        # Check Russian text in published messages (D1)
        check_russian_text_in_published
        return 0
    else
        log_error "✗ No messages published"
        
        # Detailed diagnosis: why published=0?
        log_info "Diagnosing why published=0..."
        
        # Show skip breakdown from pipeline response
        skip_breakdown=$(echo "$pipeline_response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(json.dumps(data.get('skip_breakdown', {})))" 2>/dev/null || echo "{}")
        if [ -n "$skip_breakdown" ] && [ "$skip_breakdown" != "{}" ]; then
            log_info "Skip breakdown:"
            echo "$skip_breakdown" | python3 -c "import sys, json; data=json.load(sys.stdin); [print(f\"  {k}: {v}\") for k, v in sorted(data.items(), key=lambda x: x[1], reverse=True) if v > 0]" 2>/dev/null || true
        fi
        
        # Check health for translation
        if [ "$IN_CONTAINER" = true ]; then
            health_data=$(python3 << 'PYTHON_EOF'
import httpx
import json
import os
url = os.getenv('INTEL_HEALTH_URL', 'http://localhost:8000/api/v1/intel/health')
try:
    resp = httpx.get(url, timeout=5)
    data = resp.json()
    print(json.dumps(data))
except:
    print('{}')
PYTHON_EOF
)
            translation_ok=$(echo "$health_data" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('translation_ok', False))" 2>/dev/null || echo "false")
            telegram_ok=$(echo "$health_data" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('telegram_ok', False))" 2>/dev/null || echo "false")
        else
            health_data=$(curl -sS "${INTEL_HEALTH_URL}" 2>/dev/null || echo '{}')
            translation_ok=$(echo "$health_data" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('translation_ok', False))" 2>/dev/null || echo "false")
            telegram_ok=$(echo "$health_data" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('telegram_ok', False))" 2>/dev/null || echo "false")
        fi
        
        # ETAP 7: Enhanced diagnosis
        published_reason=$(echo "$pipeline_response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('published_reason', 'N/A'))" 2>/dev/null || echo "N/A")
        
        # Print diagnosis
        echo ""
        echo "  Diagnosis:"
        if [ "$eligible" -eq 0 ]; then
            echo "    ❌ No eligible events (collected: $collected, extracted: $extracted)"
            echo "       → Check relevance filter or significance thresholds"
            echo "       → Published reason: $published_reason"
        elif [ "$telegram_ok" != "true" ]; then
            echo "    ❌ Telegram not configured or unreachable"
            echo "       → Check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env"
        elif [ "$translation_ok" != "true" ]; then
            echo "    ❌ Translation service unreachable"
            echo "       → Check LibreTranslate container: docker compose ps libretranslate"
        elif [ "$skipped" -gt 0 ]; then
            echo "    ⚠️  $skipped events skipped (see reasons above)"
            echo "       → Check skip reasons breakdown"
            echo "       → Published reason: $published_reason"
        else
            echo "    ❓ Unknown reason (eligible: $eligible, skipped: $skipped)"
            echo "       → Published reason: $published_reason"
        fi
        
        # ETAP 7: Check if published >= 1 when eligible > 0
        if [ "$eligible" -gt 0 ] && [ "$published" -eq 0 ]; then
            log_error "✗ Eligible=$eligible but published=0 (architectural issue)"
            return 1
        fi
        
        return 1
    fi
}

# Main execution
main() {
    log_info "=== Intel Production Check ==="
    
    # Track failures
    failures=0
    
    # Check 0: Daily schedule
    check_daily_schedule
    
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
    
    # Final status with detailed output
    echo ""
    log_info "=== Final Statistics ==="
    echo "  Active sources: $source_count"
    echo "  Collected: ${collected:-0}"
    echo "  Relevant: ${relevant_count:-0}"
    echo "  Eligible: ${eligible_count:-0}"
    echo "  Published: ${published:-0}"
    echo "  Skipped: ${skipped:-0}"
    
    # Exit rules per requirements (D1: must have published>=1 AND Russian text valid)
    if [ "$failures" -eq 0 ] && [ "${published:-0}" -gt 0 ]; then
        # Final checks: Russian text validation, message format, and editorial quality
        russian_ok=true
        format_ok=true
        quality_ok=true
        
        if ! check_russian_text_in_published; then
            russian_ok=false
        fi
        
        if ! check_message_format; then
            format_ok=false
        fi
        
        if ! check_editorial_quality; then
            quality_ok=false
        fi
        
        if [ "$russian_ok" = "true" ] && [ "$format_ok" = "true" ] && [ "$quality_ok" = "true" ]; then
            log_info "=== Production Check: PASSED ==="
            log_info "✓ At least 1 message published"
            log_info "✓ All published messages are in Russian"
            log_info "✓ All published messages have correct format"
            log_info "✓ All published messages meet editorial quality standards"
            exit 0
        else
            log_error "=== Production Check: FAILED ==="
            log_error "✗ Published messages contain non-Russian text"
            exit 1
        fi
    elif [ "$failures" -eq 0 ] && [ "${eligible_count:-0}" -eq 0 ] && [ "${relevant_count:-0}" -le 10 ]; then
        log_warn "=== Production Check: PASSED (no new items) ==="
        log_warn "No eligible events and <= 10 relevant items (expected for clean state)"
        exit 0
    elif [ "$failures" -eq 0 ] && [ "${eligible_count:-0}" -eq 0 ] && [ "${relevant_count:-0}" -gt 10 ]; then
        log_error "=== Production Check: FAILED ==="
        log_error "0 eligible but >10 relevant (filtering issue)"
        exit 1
    else
        log_error "=== Production Check: FAILED ==="
        log_error "Failures: $failures"
        exit 1
    fi
}

# Run main
main "$@"
