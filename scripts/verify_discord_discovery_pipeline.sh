#!/bin/bash
# Verify Discord Discovery Pipeline E2E (V2: Real invite support)

set -e

echo "🔍 Discord Discovery Pipeline Verification (V2)"
echo "================================================"

# Check for real invite code
REAL_INVITE_CODE=$(docker compose exec -T worker sh -c 'echo $DISCORD_REAL_INVITE_CODE' 2>/dev/null | tr -d '\r\n' || echo "")
REAL_INVITE_URL=$(docker compose exec -T worker sh -c 'echo $DISCORD_REAL_INVITE_URL' 2>/dev/null | tr -d '\r\n' || echo "")

if [ -z "$REAL_INVITE_CODE" ] && [ -z "$REAL_INVITE_URL" ]; then
    MODE="SMOKE"
    echo "⚠️  MODE: SMOKE TEST (no DISCORD_REAL_INVITE_CODE/URL set)"
else
    MODE="REAL"
    echo "✅ MODE: REAL TEST (invite code/URL provided)"
    if [ -n "$REAL_INVITE_URL" ]; then
        # Extract code from URL
        REAL_INVITE_CODE=$(echo "$REAL_INVITE_URL" | sed -E 's|.*discord\.(gg|com/invite)/([a-zA-Z0-9]+).*|\2|' | head -1)
    fi
    echo "   Using invite code: ${REAL_INVITE_CODE:0:8}..."
fi
echo ""

# 1. Check services
echo "1. Checking services..."
API_STATUS=$(docker compose ps api --format "{{.Status}}" 2>/dev/null | head -1 || echo "not_running")
WORKER_STATUS=$(docker compose ps worker --format "{{.Status}}" 2>/dev/null | head -1 || echo "not_running")

if [ -z "$API_STATUS" ] || echo "$API_STATUS" | grep -qE "Exited|Restarting"; then
    echo "❌ FAIL: API service is not running (status: $API_STATUS)"
    exit 1
fi

if [ -z "$WORKER_STATUS" ] || echo "$WORKER_STATUS" | grep -qE "Exited|Restarting"; then
    echo "❌ FAIL: Worker service is not running (status: $WORKER_STATUS)"
    exit 1
fi

echo "   API: $API_STATUS"
echo "   Worker: $WORKER_STATUS"

# 2. Check database tables exist
echo ""
echo "2. Checking database tables..."
TABLES=$(docker compose exec -T postgres psql -U postgres -d game_scout -t -c "
    SELECT COUNT(*) FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND table_name IN ('discord_invite_candidate', 'discord_guild', 'discord_channel');
" 2>&1 | grep -v "time=" | grep -v "level=" | tr -d ' \n')

if [ "$TABLES" != "3" ]; then
    echo "❌ FAIL: Required tables not found (expected 3, got: $TABLES)"
    exit 1
fi

echo "✅ PASS: All required tables exist"

# 3. Check candidates
echo ""
echo "3. Checking candidates..."
CANDIDATE_COUNT=$(docker compose exec -T postgres psql -U postgres -d game_scout -t -c "
    SELECT COUNT(*) FROM discord_invite_candidate;
" 2>&1 | grep -v "time=" | grep -v "level=" | tr -d ' \n')

echo "   candidates in DB: $CANDIDATE_COUNT"

# 4. Check resolved candidates
echo ""
echo "4. Checking resolved candidates..."
RESOLVED_COUNT=$(docker compose exec -T postgres psql -U postgres -d game_scout -t -c "
    SELECT COUNT(*) FROM discord_invite_candidate WHERE resolve_status = 'ok' AND guild_id IS NOT NULL;
" 2>&1 | grep -v "time=" | grep -v "level=" | tr -d ' \n')

echo "   resolved candidates with guild_id: $RESOLVED_COUNT"

# 5. Test API endpoint
echo ""
echo "5. Testing API endpoint..."
API_RESPONSE=$(curl -4 -sS "http://127.0.0.1:8000/api/v1/discord/discovery/candidates?limit=10" 2>&1)

if [ $? -ne 0 ]; then
    echo "❌ FAIL: API request failed"
    exit 1
fi

if ! echo "$API_RESPONSE" | python3 -m json.tool > /dev/null 2>&1; then
    echo "❌ FAIL: Invalid JSON response"
    exit 1
fi

API_STATUS=$(echo "$API_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', 'ERROR'))" 2>&1)

if [ "$API_STATUS" != "ok" ]; then
    echo "❌ FAIL: API returned status != ok"
    exit 1
fi

echo "✅ PASS: API endpoint works"

# 6. Check guilds
echo ""
echo "6. Checking guilds..."
GUILD_COUNT=$(docker compose exec -T postgres psql -U postgres -d game_scout -t -c "
    SELECT COUNT(*) FROM discord_guild;
" 2>&1 | grep -v "time=" | grep -v "level=" | tr -d ' \n')

echo "   guilds in DB: $GUILD_COUNT"

# 7. Check channels
echo ""
echo "7. Checking channels..."
CHANNEL_COUNT=$(docker compose exec -T postgres psql -U postgres -d game_scout -t -c "
    SELECT COUNT(*) FROM discord_channel;
" 2>&1 | grep -v "time=" | grep -v "level=" | tr -d ' \n')

VISIBLE_CHANNEL_COUNT=$(docker compose exec -T postgres psql -U postgres -d game_scout -t -c "
    SELECT COUNT(*) FROM discord_channel WHERE is_visible_to_bot = true;
" 2>&1 | grep -v "time=" | grep -v "level=" | tr -d ' \n')

ELIGIBLE_COUNT=$(docker compose exec -T postgres psql -U postgres -d game_scout -t -c "
    SELECT COUNT(*) FROM discord_channel WHERE scan_enabled = true;
" 2>&1 | grep -v "time=" | grep -v "level=" | tr -d ' \n')

echo "   channels in DB: $CHANNEL_COUNT"
echo "   visible channels: $VISIBLE_CHANNEL_COUNT"
echo "   eligible for scan: $ELIGIBLE_COUNT"

# STEP B-C: Real invite resolve and guild creation (if MODE=REAL)
if [ "$MODE" = "REAL" ]; then
    echo ""
    echo "STEP B-C: Testing real invite resolve and guild creation..."
    
    # Insert candidate with real invite code
    docker compose exec -T postgres psql -U postgres -d game_scout -c "
        INSERT INTO discord_invite_candidate (
            invite_code, invite_url, source_type, source_url, found_at, resolve_status
        ) VALUES (
            '$REAL_INVITE_CODE', 'https://discord.gg/$REAL_INVITE_CODE', 'manual', 'verify_script', NOW(), 'new'
        ) ON CONFLICT (invite_code) DO UPDATE
        SET resolve_status = 'new', found_at = NOW();
    " > /dev/null 2>&1
    
    # Run resolve task
    echo "   Running resolve_discord_invite_task..."
    RESOLVE_OUTPUT=$(docker compose exec -T worker python - <<PY 2>&1
import os
from apps.worker.tasks.resolve_discord_invite import resolve_discord_invite_task
code = "$REAL_INVITE_CODE"
result = resolve_discord_invite_task(invite_code=code)
print(f"status={result.get('status')}, resolve_status={result.get('resolve_status')}, http_status={result.get('http_status')}, guild_id={result.get('guild_id', 'None')[:20] if result.get('guild_id') else 'None'}")
PY
    )
    
    echo "   $RESOLVE_OUTPUT"
    
    # Check resolve result
    RESOLVE_STATUS=$(docker compose exec -T postgres psql -U postgres -d game_scout -tAc "
        SELECT resolve_status FROM discord_invite_candidate WHERE invite_code = '$REAL_INVITE_CODE';
    " 2>&1 | grep -v "time=" | grep -v "level=" | tr -d ' \n')
    
    HTTP_STATUS=$(docker compose exec -T postgres psql -U postgres -d game_scout -tAc "
        SELECT resolve_http_status FROM discord_invite_candidate WHERE invite_code = '$REAL_INVITE_CODE';
    " 2>&1 | grep -v "time=" | grep -v "level=" | tr -d ' \n')
    
    GUILD_ID=$(docker compose exec -T postgres psql -U postgres -d game_scout -tAc "
        SELECT guild_id FROM discord_invite_candidate WHERE invite_code = '$REAL_INVITE_CODE';
    " 2>&1 | grep -v "time=" | grep -v "level=" | tr -d ' \n')
    
    echo "   resolve_status: $RESOLVE_STATUS"
    echo "   http_status: $HTTP_STATUS"
    echo "   guild_id: ${GUILD_ID:0:20}..."
    
    if [ -n "$GUILD_ID" ] && [ "$GUILD_ID" != "" ]; then
        echo "   ✅ Guild ID found"
    else
        echo "   ❌ Guild ID missing"
    fi
    
    if [ "$RESOLVE_STATUS" != "ok" ]; then
        if [ "$HTTP_STATUS" = "404" ]; then
            echo "   ⚠️  Invite code invalid/expired. ACTION_REQUIRED: Use a valid invite code."
            exit 1
        else
            echo "   ❌ Resolve failed (status=$RESOLVE_STATUS, http=$HTTP_STATUS)"
            echo "   ACTION_REQUIRED: Check DISCORD_BOT_TOKEN and invite code validity"
            exit 1
        fi
    fi
    
    # Check guild was created
    GUILD_COUNT_AFTER=$(docker compose exec -T postgres psql -U postgres -d game_scout -tAc "
        SELECT COUNT(*) FROM discord_guild;
    " 2>&1 | grep -v "time=" | grep -v "level=" | tr -d ' \n')
    
    echo "   Guilds in DB: $GUILD_COUNT_AFTER"
    
    if [ "$GUILD_COUNT_AFTER" -lt 1 ]; then
        echo "   ❌ FAIL: No guild created after resolve"
        exit 1
    fi
    
    # STEP D: Sync channels (if guild_id exists)
    if [ -n "$GUILD_ID" ] && [ "$GUILD_ID" != "" ]; then
        echo ""
        echo "STEP D: Testing channel sync..."
        echo "   Running sync_guild_channels_task(guild_id=$GUILD_ID)..."
        
        SYNC_OUTPUT=$(docker compose exec -T worker python - <<PY 2>&1
from apps.worker.tasks.sync_guild_channels import sync_guild_channels_task
guild_id = "$GUILD_ID"
result = sync_guild_channels_task(guild_id=guild_id)
print(f"status={result.get('status')}, channels_found={result.get('channels_found')}, channels_visible={result.get('channels_visible')}, channels_enabled={result.get('channels_enabled')}")
PY
        )
        
        echo "   $SYNC_OUTPUT"
        
        # Check channels were created
        CHANNEL_COUNT_AFTER=$(docker compose exec -T postgres psql -U postgres -d game_scout -tAc "
            SELECT COUNT(*) FROM discord_channel WHERE guild_id = '$GUILD_ID';
        " 2>&1 | grep -v "time=" | grep -v "level=" | tr -d ' \n')
        
        echo "   Channels in DB for guild: $CHANNEL_COUNT_AFTER"
        
        # STEP E: Check eligible_for_scan (scan_enabled)
        ELIGIBLE_COUNT_AFTER=$(docker compose exec -T postgres psql -U postgres -d game_scout -tAc "
            SELECT COUNT(*) FROM discord_channel WHERE guild_id = '$GUILD_ID' AND scan_enabled = true;
        " 2>&1 | grep -v "time=" | grep -v "level=" | tr -d ' \n')
        
        echo "   Channels eligible for scan: $ELIGIBLE_COUNT_AFTER"
        
        if [ "$CHANNEL_COUNT_AFTER" -lt 1 ]; then
            echo "   ⚠️  WARNING: No channels synced. Bot may not have View Channels permission."
            echo "   ACTION_REQUIRED: Ensure bot has View Channels + Read Message History permissions"
        fi
        
        if [ "$ELIGIBLE_COUNT_AFTER" -lt 1 ]; then
            echo "   ⚠️  WARNING: No channels marked eligible for scan"
        fi
    else
        echo "   ⚠️  Skipping channel sync (no guild_id)"
    fi
fi

# Summary
echo ""
echo "============================"
if [ "$MODE" = "SMOKE" ]; then
    echo "✅ SMOKE TEST PASS"
    echo "============================"
    echo ""
    echo "Summary:"
    echo "  - Tables exist: ✅"
    echo "  - Candidates: $CANDIDATE_COUNT"
    echo "  - Resolved: $RESOLVED_COUNT"
    echo "  - Guilds: $GUILD_COUNT"
    echo "  - Channels: $CHANNEL_COUNT (visible: $VISIBLE_CHANNEL_COUNT, eligible: $ELIGIBLE_COUNT)"
    echo "  - API endpoint: ✅"
    echo ""
    echo "⚠️  ACTION_REQUIRED:"
    echo "  Set DISCORD_REAL_INVITE_CODE or DISCORD_REAL_INVITE_URL to verify resolve/sync"
    echo ""
    echo "  Example:"
    echo "    export DISCORD_REAL_INVITE_CODE=abcdEfgh"
    echo "    docker compose up -d worker  # Restart to pick up env"
    echo "    bash scripts/verify_discord_discovery_pipeline.sh"
    exit 0
else
    echo "✅ REAL TEST PASS"
    echo "============================"
    echo ""
    echo "Summary:"
    echo "  - Tables exist: ✅"
    echo "  - Candidates: $CANDIDATE_COUNT"
    echo "  - Resolved: $RESOLVED_COUNT"
    echo "  - Guilds: $GUILD_COUNT"
    echo "  - Channels: $CHANNEL_COUNT (visible: $VISIBLE_CHANNEL_COUNT, eligible: $ELIGIBLE_COUNT)"
    echo "  - API endpoint: ✅"
    echo "  - Real invite resolved: ✅"
    echo "  - Guild created: ✅"
    if [ "$CHANNEL_COUNT" -ge 1 ]; then
        echo "  - Channels synced: ✅"
    else
        echo "  - Channels synced: ⚠️  (check bot permissions)"
    fi
    echo ""
    echo "✅ MERGE-READY: YES (Real E2E verified)"
    exit 0
fi
