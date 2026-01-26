#!/bin/bash
# Verify Brain v3 implementation
# Checks: confidence, stage, why_now, signals_used, titles, coverage

set -e

API_URL="${API_URL:-http://localhost:8000}"

echo "=== Brain v3 Verification ==="
echo ""

# 1. Check emerging endpoint returns v3 fields
echo "1. Checking emerging endpoint for v3 fields..."
EMERGING_RESPONSE=$(curl -s "${API_URL}/api/v1/trends/games/emerging?limit=5" || echo "{}")
HAS_CONFIDENCE=$(echo "$EMERGING_RESPONSE" | jq -r '.games[0].confidence_score // empty' 2>/dev/null || echo "")
HAS_STAGE=$(echo "$EMERGING_RESPONSE" | jq -r '.games[0].stage // empty' 2>/dev/null || echo "")
HAS_WHY_NOW=$(echo "$EMERGING_RESPONSE" | jq -r '.games[0].why_now // empty' 2>/dev/null || echo "")
HAS_SIGNALS_USED=$(echo "$EMERGING_RESPONSE" | jq -r '.games[0].signals_used // empty' 2>/dev/null || echo "")

if [ -n "$HAS_CONFIDENCE" ] && [ -n "$HAS_STAGE" ] && [ -n "$HAS_WHY_NOW" ]; then
    echo "✅ Brain v3 fields present: confidence_score, stage, why_now"
else
    echo "❌ Missing Brain v3 fields"
    echo "   confidence_score: ${HAS_CONFIDENCE:-MISSING}"
    echo "   stage: ${HAS_STAGE:-MISSING}"
    echo "   why_now: ${HAS_WHY_NOW:-MISSING}"
fi

if [ -n "$HAS_SIGNALS_USED" ]; then
    echo "✅ signals_used field present"
else
    echo "⚠️  signals_used field missing (may be empty array)"
fi

echo ""

# 2. Check titles are present
echo "2. Checking game titles..."
FIRST_GAME_NAME=$(echo "$EMERGING_RESPONSE" | jq -r '.games[0].name // empty' 2>/dev/null || echo "")
FIRST_GAME_TITLE=$(echo "$EMERGING_RESPONSE" | jq -r '.games[0].title // empty' 2>/dev/null || echo "")
FIRST_STEAM_URL=$(echo "$EMERGING_RESPONSE" | jq -r '.games[0].steam_url // empty' 2>/dev/null || echo "")

if [ -n "$FIRST_GAME_NAME" ] && [ "$FIRST_GAME_NAME" != "null" ] && ! echo "$FIRST_GAME_NAME" | grep -q "без названия"; then
    echo "✅ Game name present: $FIRST_GAME_NAME"
else
    echo "⚠️  Game name missing or fallback: ${FIRST_GAME_NAME:-MISSING}"
fi

if [ -n "$FIRST_STEAM_URL" ] && [ "$FIRST_STEAM_URL" != "null" ]; then
    echo "✅ Steam URL present: $FIRST_STEAM_URL"
else
    echo "❌ Steam URL missing"
fi

echo ""

# 3. Check signals coverage
echo "3. Checking signals coverage..."
SUMMARY_RESPONSE=$(curl -s "${API_URL}/api/v1/admin/system/summary" || echo "{}")
HAS_COVERAGE=$(echo "$SUMMARY_RESPONSE" | jq -r '.trends_today.signals_coverage // empty' 2>/dev/null || echo "")
HAS_FRESHNESS=$(echo "$SUMMARY_RESPONSE" | jq -r '.trends_today.signals_freshness // empty' 2>/dev/null || echo "")

if [ -n "$HAS_COVERAGE" ] && [ "$HAS_COVERAGE" != "null" ]; then
    echo "✅ signals_coverage present"
    STEAM_COVERAGE=$(echo "$SUMMARY_RESPONSE" | jq -r '.trends_today.signals_coverage.steam.pct // 0' 2>/dev/null || echo "0")
    REDDIT_COVERAGE=$(echo "$SUMMARY_RESPONSE" | jq -r '.trends_today.signals_coverage.reddit.pct // 0' 2>/dev/null || echo "0")
    YOUTUBE_COVERAGE=$(echo "$SUMMARY_RESPONSE" | jq -r '.trends_today.signals_coverage.youtube.pct // 0' 2>/dev/null || echo "0")
    echo "   Steam: ${STEAM_COVERAGE}%"
    echo "   Reddit: ${REDDIT_COVERAGE}%"
    echo "   YouTube: ${YOUTUBE_COVERAGE}%"
else
    echo "❌ signals_coverage missing"
fi

if [ -n "$HAS_FRESHNESS" ] && [ "$HAS_FRESHNESS" != "null" ]; then
    echo "✅ signals_freshness present"
else
    echo "❌ signals_freshness missing"
fi

echo ""

# 4. Check emerging influence
echo "4. Checking emerging influence calculation..."
EMERGING_INFLUENCE=$(echo "$SUMMARY_RESPONSE" | jq -r '.trends_today.emerging_influence // empty' 2>/dev/null || echo "")
if [ -n "$EMERGING_INFLUENCE" ] && [ "$EMERGING_INFLUENCE" != "null" ]; then
    echo "✅ emerging_influence present"
    COMPUTED_FROM=$(echo "$SUMMARY_RESPONSE" | jq -r '.trends_today.emerging_influence.computed_from // "unknown"' 2>/dev/null || echo "unknown")
    echo "   Computed from: $COMPUTED_FROM"
else
    echo "❌ emerging_influence missing"
fi

echo ""

# 5. Check scenario mode
echo "5. Checking scenario mode parameters..."
SCENARIO_RESPONSE=$(curl -s "${API_URL}/api/v1/trends/games/emerging?limit=1&min_score=0&min_confidence=0" || echo "{}")
HAS_SCENARIO=$(echo "$SCENARIO_RESPONSE" | jq -r '.scenario // empty' 2>/dev/null || echo "")
if [ -n "$HAS_SCENARIO" ] && [ "$HAS_SCENARIO" != "null" ]; then
    echo "✅ Scenario mode present"
    echo "$SCENARIO_RESPONSE" | jq '.scenario' 2>/dev/null || echo "   (could not parse)"
else
    echo "⚠️  Scenario mode missing (may be optional)"
fi

echo ""

# Summary
echo "=== Summary ==="
if [ -n "$HAS_CONFIDENCE" ] && [ -n "$HAS_STAGE" ] && [ -n "$HAS_COVERAGE" ]; then
    echo "✅ Brain v3 implementation verified"
    exit 0
else
    echo "❌ Some checks failed"
    exit 1
fi
