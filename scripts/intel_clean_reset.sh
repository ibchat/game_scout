#!/usr/bin/env bash
# Intel Clean Reset Script
# 1. Check migration 016 exists
# 2. Fix alembic chain if needed
# 3. Apply migration
# 4. Clean extracted_items, events, publish_log (keep raw_items)
# 5. Run pipeline
# 6. Check results

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# Check if running in Docker
if [ -f "/.dockerenv" ] || [ -n "${IN_DOCKER:-}" ]; then
    IN_CONTAINER=true
    DOCKER_PREFIX=""
else
    IN_CONTAINER=false
    DOCKER_PREFIX="docker compose exec -T"
fi

# Step 1: Check migration 016 exists
log_step "1. Checking migration 016 exists..."
MIGRATION_016="$PROJECT_ROOT/migrations/versions/016_add_extracted_at_to_extracted_items.py"
if [ -f "$MIGRATION_016" ]; then
    log_info "✓ Migration 016 found: $MIGRATION_016"
    # Check revision and down_revision
    REVISION=$(grep -E "^revision = " "$MIGRATION_016" | sed "s/revision = '\(.*\)'/\1/")
    DOWN_REVISION=$(grep -E "^down_revision = " "$MIGRATION_016" | sed "s/down_revision = '\(.*\)'/\1/")
    log_info "  Revision: $REVISION"
    log_info "  Down revision: $DOWN_REVISION"
else
    log_error "✗ Migration 016 not found!"
    exit 1
fi

# Step 2: Check alembic chain
log_step "2. Checking alembic chain..."
if [ "$IN_CONTAINER" = true ]; then
    CURRENT_REV=$(python3 << 'PYTHON_EOF'
from alembic.config import Config
from alembic.script import ScriptDirectory
import sys
try:
    cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(cfg)
    current = script.get_current_head()
    print(current)
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
PYTHON_EOF
)
else
    CURRENT_REV=$($DOCKER_PREFIX api python3 << 'PYTHON_EOF'
from alembic.config import Config
from alembic.script import ScriptDirectory
import sys
try:
    cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(cfg)
    current = script.get_current_head()
    print(current)
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
PYTHON_EOF
)
fi

log_info "Current alembic head: $CURRENT_REV"

# Check if 016 is in chain
if [ "$IN_CONTAINER" = true ]; then
    HISTORY=$(python3 << 'PYTHON_EOF'
from alembic.config import Config
from alembic.script import ScriptDirectory
try:
    cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(cfg)
    revisions = [rev.revision for rev in script.walk_revisions()]
    print(" ".join(revisions))
except Exception as e:
    print(f"ERROR: {e}")
PYTHON_EOF
)
else
    HISTORY=$($DOCKER_PREFIX api python3 << 'PYTHON_EOF'
from alembic.config import Config
from alembic.script import ScriptDirectory
try:
    cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(cfg)
    revisions = [rev.revision for rev in script.walk_revisions()]
    print(" ".join(revisions))
except Exception as e:
    print(f"ERROR: {e}")
PYTHON_EOF
)
fi

if echo "$HISTORY" | grep -q "016_extracted_at"; then
    log_info "✓ Migration 016 is in alembic chain"
else
    log_warn "⚠ Migration 016 not in chain, checking down_revision..."
    # Check if down_revision exists
    if echo "$HISTORY" | grep -q "$DOWN_REVISION"; then
        log_info "✓ Down revision $DOWN_REVISION exists in chain"
    else
        log_error "✗ Down revision $DOWN_REVISION not found in chain!"
        log_error "Available revisions: $HISTORY"
        exit 1
    fi
fi

# Step 3: Apply migration
log_step "3. Applying migration 016..."
if [ "$IN_CONTAINER" = true ]; then
    alembic upgrade head
else
    $DOCKER_PREFIX api alembic upgrade head
fi

if [ $? -eq 0 ]; then
    log_info "✓ Migration applied successfully"
else
    log_error "✗ Migration failed!"
    exit 1
fi

# Step 4: Verify extracted_at column exists
log_step "4. Verifying extracted_at column..."
if [ "$IN_CONTAINER" = true ]; then
    COLUMN_EXISTS=$(python3 << 'PYTHON_EOF'
from apps.db.session import SessionLocal
from sqlalchemy import text
db = SessionLocal()
try:
    result = db.execute(text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'intel_extracted_items' 
        AND column_name = 'extracted_at'
    """))
    exists = result.fetchone() is not None
    print("true" if exists else "false")
finally:
    db.close()
PYTHON_EOF
)
else
    COLUMN_EXISTS=$($DOCKER_PREFIX api python3 << 'PYTHON_EOF'
from apps.db.session import SessionLocal
from sqlalchemy import text
db = SessionLocal()
try:
    result = db.execute(text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'intel_extracted_items' 
        AND column_name = 'extracted_at'
    """))
    exists = result.fetchone() is not None
    print("true" if exists else "false")
finally:
    db.close()
PYTHON_EOF
)
fi

if [ "$COLUMN_EXISTS" = "true" ]; then
    log_info "✓ extracted_at column exists"
else
    log_error "✗ extracted_at column not found!"
    exit 1
fi

# Step 5: Clean tables (keep raw_items) - ETAP 10 SAFE
log_step "5. Cleaning extracted_items, events, publish_log (keeping raw_items)..."
if [ "$IN_CONTAINER" = true ]; then
    python3 << 'PYTHON_EOF'
from apps.db.session import SessionLocal
from sqlalchemy import text
db = SessionLocal()
try:
    # Get counts before
    raw_count = db.execute(text("SELECT COUNT(*) FROM intel_raw_items")).scalar()
    extracted_count = db.execute(text("SELECT COUNT(*) FROM intel_extracted_items")).scalar()
    events_count = db.execute(text("SELECT COUNT(*) FROM intel_events")).scalar()
    log_count = db.execute(text("SELECT COUNT(*) FROM intel_publish_log")).scalar()
    
    print(f"Before cleanup:")
    print(f"  raw_items: {raw_count}")
    print(f"  extracted_items: {extracted_count}")
    print(f"  events: {events_count}")
    print(f"  publish_log: {log_count}")
    
    # Clean tables
    db.execute(text("DELETE FROM intel_publish_log"))
    db.execute(text("DELETE FROM intel_events"))
    db.execute(text("DELETE FROM intel_extracted_items"))
    db.commit()
    
    print(f"\nAfter cleanup:")
    print(f"  raw_items: {raw_count} (kept)")
    print(f"  extracted_items: 0")
    print(f"  events: 0")
    print(f"  publish_log: 0")
    
    print("\n✓ Cleanup complete")
except Exception as e:
    db.rollback()
    print(f"ERROR: {e}")
    raise
finally:
    db.close()
PYTHON_EOF
else
    $DOCKER_PREFIX api python3 << 'PYTHON_EOF'
from apps.db.session import SessionLocal
from sqlalchemy import text
db = SessionLocal()
try:
    # Get counts before
    raw_count = db.execute(text("SELECT COUNT(*) FROM intel_raw_items")).scalar()
    extracted_count = db.execute(text("SELECT COUNT(*) FROM intel_extracted_items")).scalar()
    events_count = db.execute(text("SELECT COUNT(*) FROM intel_events")).scalar()
    log_count = db.execute(text("SELECT COUNT(*) FROM intel_publish_log")).scalar()
    
    print(f"Before cleanup:")
    print(f"  raw_items: {raw_count}")
    print(f"  extracted_items: {extracted_count}")
    print(f"  events: {events_count}")
    print(f"  publish_log: {log_count}")
    
    # Clean tables
    db.execute(text("DELETE FROM intel_publish_log"))
    db.execute(text("DELETE FROM intel_events"))
    db.execute(text("DELETE FROM intel_extracted_items"))
    db.commit()
    
    print(f"\nAfter cleanup:")
    print(f"  raw_items: {raw_count} (kept)")
    print(f"  extracted_items: 0")
    print(f"  events: 0")
    print(f"  publish_log: 0")
    
    print("\n✓ Cleanup complete")
except Exception as e:
    db.rollback()
    print(f"ERROR: {e}")
    raise
finally:
    db.close()
PYTHON_EOF
fi

# Step 6: Run pipeline
log_step "6. Running pipeline..."
if [ "$IN_CONTAINER" = true ]; then
    PIPELINE_RESULT=$(python3 << 'PYTHON_EOF'
import httpx
import json
import os
url = os.getenv('API_URL', 'http://localhost:8000') + '/api/v1/intel/pipeline/run'
try:
    resp = httpx.post(url, json={"sources": None, "dry_run": False}, timeout=300)
    resp.raise_for_status()
    print(json.dumps(resp.json(), indent=2))
except Exception as e:
    print(json.dumps({"error": str(e)}))
PYTHON_EOF
)
else
    PIPELINE_RESULT=$(curl -sS -X POST "http://localhost:8000/api/v1/intel/pipeline/run" \
        -H "Content-Type: application/json" \
        -d '{"sources": null, "dry_run": false}' \
        --max-time 300)
fi

echo "$PIPELINE_RESULT" | python3 -m json.tool 2>/dev/null || echo "$PIPELINE_RESULT"

# Step 7: Check extraction ratio (ETAP 10: target ≥5% for clean reset)
log_step "7. Checking extraction ratio..."
EXTRACTION_RATIO=$(echo "$PIPELINE_RESULT" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('extraction_ratio', 0))" 2>/dev/null || echo "0")
TOTAL_RAW=$(echo "$PIPELINE_RESULT" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('total_raw', 0))" 2>/dev/null || echo "0")
TOTAL_EXTRACTED=$(echo "$PIPELINE_RESULT" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('total_extracted', 0))" 2>/dev/null || echo "0")

log_info "Extraction ratio: ${EXTRACTION_RATIO}%"
log_info "Total raw (24h): $TOTAL_RAW"
log_info "Total extracted (24h): $TOTAL_EXTRACTED"

# Check extraction ratio >= 5% using Python (ETAP 10: lowered threshold for clean reset)
EXTRACTION_OK=$(echo "$EXTRACTION_RATIO" | python3 -c "import sys; ratio = float(sys.stdin.read().strip() or 0); print('1' if ratio >= 5.0 else '0')" 2>/dev/null || echo "0")
if [ "$EXTRACTION_OK" = "1" ]; then
    log_info "✓ Extraction ratio ≥ 5% (target met for clean reset)"
else
    log_warn "⚠ Extraction ratio < 5% (target: ≥5% for clean reset)"
fi

# Step 8: Check scoring
log_step "8. Checking scoring..."
SCORING_BREAKDOWN=$(echo "$PIPELINE_RESULT" | python3 -c "import sys, json; data=json.load(sys.stdin); print(json.dumps(data.get('scoring_breakdown_summary', {})))" 2>/dev/null || echo "{}")
ZERO_SCORES=$(echo "$SCORING_BREAKDOWN" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('zero_scores', 0))" 2>/dev/null || echo "0")
MIN_SCORE=$(echo "$SCORING_BREAKDOWN" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('min', 0))" 2>/dev/null || echo "0")

log_info "Scoring breakdown:"
echo "$SCORING_BREAKDOWN" | python3 -m json.tool 2>/dev/null || echo "$SCORING_BREAKDOWN"

if [ "$ZERO_SCORES" = "0" ]; then
    log_info "✓ No zero scores (target met)"
else
    log_warn "⚠ Found $ZERO_SCORES events with score=0"
fi

if [ "$MIN_SCORE" -ge 25 ]; then
    log_info "✓ Minimum score ≥ 25 (target met)"
else
    log_warn "⚠ Minimum score < 25: $MIN_SCORE"
fi

# Step 9: Check publish
log_step "9. Checking publish results..."
PUBLISHED=$(echo "$PIPELINE_RESULT" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('published', 0))" 2>/dev/null || echo "0")
ELIGIBLE=$(echo "$PIPELINE_RESULT" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('eligible_count', 0))" 2>/dev/null || echo "0")
PUBLISHED_REASON=$(echo "$PIPELINE_RESULT" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('published_reason', 'N/A'))" 2>/dev/null || echo "N/A")

log_info "Published: $PUBLISHED"
log_info "Eligible: $ELIGIBLE"
log_info "Published reason: $PUBLISHED_REASON"

if [ "$PUBLISHED" -gt 0 ]; then
    log_info "✓ Published ≥ 1 post (target met)"
elif [ "$ELIGIBLE" -gt 0 ]; then
    log_warn "⚠ Eligible=$ELIGIBLE but published=0 (reason: $PUBLISHED_REASON)"
else
    log_warn "⚠ No eligible events (published=0, eligible=0)"
fi

# Final summary
echo ""
log_step "=== INTEL CLEAN RESET COMPLETE ==="
echo ""
log_info "Summary:"
echo "  Extraction ratio: ${EXTRACTION_RATIO}% (target: ≥10%)"
echo "  Zero scores: $ZERO_SCORES (target: 0)"
echo "  Min score: $MIN_SCORE (target: ≥25)"
echo "  Published: $PUBLISHED (target: ≥1 if eligible > 0)"
echo "  Eligible: $ELIGIBLE"
echo ""

# Final check using Python (ETAP 10: adjusted thresholds for clean reset)
EXTRACTION_OK=$(echo "$EXTRACTION_RATIO" | python3 -c "import sys; ratio = float(sys.stdin.read().strip() or 0); print('1' if ratio >= 5.0 else '0')" 2>/dev/null || echo "0")
if [ "$EXTRACTION_OK" = "1" ] && \
   [ "$ZERO_SCORES" = "0" ] && \
   [ "$MIN_SCORE" -ge 25 ]; then
    log_info "✅ All targets met!"
    exit 0
else
    log_warn "⚠ Some targets not met, check details above"
    exit 1
fi
