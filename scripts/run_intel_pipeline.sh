#!/usr/bin/env bash
# Quick script to check Intel health and run pipeline
# Usage: bash scripts/run_intel_pipeline.sh

set -euo pipefail

echo "=== Intel Pipeline Runner ==="
echo ""

# Check if Docker is running
if ! docker compose ps api &>/dev/null | grep -q "Up"; then
    echo "❌ API container is not running"
    echo "Start with: docker compose up -d"
    exit 1
fi

echo "1. Checking health..."
HEALTH=$(docker compose exec -T api python3 << 'PYTHON_EOF'
import httpx
import json
try:
    resp = httpx.get('http://localhost:8000/api/v1/intel/health', timeout=10)
    health = resp.json()
    print(json.dumps(health))
except Exception as e:
    print(json.dumps({'error': str(e)}))
PYTHON_EOF
)

ENABLED=$(echo "$HEALTH" | python3 -c "import sys, json; print(json.load(sys.stdin).get('enabled', False))" 2>/dev/null || echo "false")
TELEGRAM_OK=$(echo "$HEALTH" | python3 -c "import sys, json; print(json.load(sys.stdin).get('telegram_ok', False))" 2>/dev/null || echo "false")
DB_OK=$(echo "$HEALTH" | python3 -c "import sys, json; print(json.load(sys.stdin).get('db_ok', False))" 2>/dev/null || echo "false")

if [ "$ENABLED" != "true" ]; then
    echo "❌ Intel module is disabled"
    echo "Set INTEL_ENABLED=true in .env"
    exit 1
fi

if [ "$TELEGRAM_OK" != "true" ]; then
    TELEGRAM_ERROR=$(echo "$HEALTH" | python3 -c "import sys, json; print(json.load(sys.stdin).get('telegram_error', 'Unknown error'))" 2>/dev/null || echo "Unknown")
    echo "❌ Telegram not configured: $TELEGRAM_ERROR"
    echo "Check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env"
    exit 1
fi

if [ "$DB_OK" != "true" ]; then
    echo "❌ Database connection failed"
    exit 1
fi

echo "✅ Health check passed"
echo ""

# Check sources
echo "2. Checking sources..."
SOURCE_COUNT=$(docker compose exec -T api python3 << 'PYTHON_EOF'
from apps.db.session import SessionLocal
from apps.intel.db.models import IntelSource
db = SessionLocal()
count = db.query(IntelSource).filter(IntelSource.is_enabled == True).count()
print(count)
db.close()
PYTHON_EOF
)

if [ "$SOURCE_COUNT" -eq 0 ]; then
    echo "⚠️  No active sources found"
    echo "Seeding sources..."
    docker compose exec -T api python3 << 'PYTHON_EOF'
import httpx
resp = httpx.post('http://localhost:8000/api/v1/intel/sources/seed', timeout=30)
print(resp.json())
PYTHON_EOF
    SOURCE_COUNT=$(docker compose exec -T api python3 << 'PYTHON_EOF'
from apps.db.session import SessionLocal
from apps.intel.db.models import IntelSource
db = SessionLocal()
count = db.query(IntelSource).filter(IntelSource.is_enabled == True).count()
print(count)
db.close()
PYTHON_EOF
)
fi

echo "✅ Found $SOURCE_COUNT active sources"
echo ""

# Run pipeline
echo "3. Running pipeline (this may take a few minutes)..."
echo ""

PIPELINE_RESULT=$(docker compose exec -T api python3 << 'PYTHON_EOF'
import httpx
import json
try:
    resp = httpx.post(
        'http://localhost:8000/api/v1/intel/pipeline/run',
        json={'sources': [], 'dry_run': False},
        timeout=300
    )
    resp.raise_for_status()
    result = resp.json()
    print(json.dumps(result))
except Exception as e:
    print(json.dumps({'error': str(e)}))
PYTHON_EOF
)

PUBLISHED=$(echo "$PIPELINE_RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('published', 0))" 2>/dev/null || echo "0")
SKIPPED=$(echo "$PIPELINE_RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('skipped', 0))" 2>/dev/null || echo "0")
ELIGIBLE=$(echo "$PIPELINE_RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('eligible_count', 0))" 2>/dev/null || echo "0")
COLLECTED=$(echo "$PIPELINE_RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('collected', 0))" 2>/dev/null || echo "0")

echo "=== Pipeline Results ==="
echo "  Collected: $COLLECTED"
echo "  Eligible: $ELIGIBLE"
echo "  Published: $PUBLISHED"
echo "  Skipped: $SKIPPED"
echo ""

if [ "$PUBLISHED" -gt 0 ]; then
    echo "✅ SUCCESS: $PUBLISHED message(s) published to Telegram!"
    echo "Check your Telegram channel to see the news."
elif [ "$ELIGIBLE" -gt 0 ]; then
    echo "⚠️  $ELIGIBLE eligible events but none published."
    echo "Check skip reasons in the response above."
else
    echo "⚠️  No eligible events found."
    echo "This may be normal if all recent news was already published."
fi

echo ""
echo "Full response:"
echo "$PIPELINE_RESULT" | python3 -m json.tool 2>/dev/null || echo "$PIPELINE_RESULT"
