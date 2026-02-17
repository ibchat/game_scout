#!/bin/bash
# Verify Discord Live Fetch - проверяет, что можно читать сообщения из Discord
# Детерминированный тест для диагностики проблем с intents/permissions

set -e

echo "🔍 Discord Live Fetch Verification"
echo "=================================="

# 1. Запускаем debug скрипт
echo ""
echo "1. Running debug_discord_fetch_messages.sh..."
OUTPUT=$(bash scripts/debug_discord_fetch_messages.sh 2>&1)
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo "❌ FAIL: debug_discord_fetch_messages.sh failed with exit code $EXIT_CODE"
    echo "$OUTPUT"
    exit 1
fi

echo "$OUTPUT"
echo ""

# 2. Проверяем токен (placeholder или реальный)
TOKEN_INFO=$(echo "$OUTPUT" | grep -E "Token length|Token prefix" || echo "")
TOKEN_LEN=$(echo "$OUTPUT" | grep "Token length:" | awk '{print $3}' || echo "0")

if [ -z "$TOKEN_INFO" ]; then
    echo "❌ FAIL: Could not extract token info from output"
    exit 1
fi

echo "2. Checking token..."
echo "   $TOKEN_INFO"

# Проверяем, не placeholder ли токен
if [ "$TOKEN_LEN" -lt 50 ]; then
    echo "⚠️  SKIP: Token too short (likely placeholder)"
    echo "   Token length: $TOKEN_LEN (expected >= 50)"
    echo "   Exiting with code 0 (not a failure, just placeholder)"
    exit 0
fi

TOKEN_PREFIX=$(echo "$OUTPUT" | grep "Token prefix:" | awk '{print $3}' | cut -d'.' -f1 || echo "")
if echo "$TOKEN_PREFIX" | grep -qiE "PASTE|PUT|REAL|PLACEHOLDER"; then
    echo "⚠️  SKIP: Token appears to be placeholder"
    echo "   Token prefix: $TOKEN_PREFIX"
    echo "   Exiting with code 0 (not a failure, just placeholder)"
    exit 0
fi

echo "✅ PASS: Token looks valid"

# 3. Проверяем status code
echo ""
echo "3. Checking API status code..."
STATUS_CODE=$(echo "$OUTPUT" | grep "Status Code:" | awk '{print $3}' || echo "")

if [ -z "$STATUS_CODE" ]; then
    echo "❌ FAIL: Could not extract status code from output"
    exit 1
fi

echo "   Status Code: $STATUS_CODE"

if [ "$STATUS_CODE" != "200" ]; then
    echo "❌ FAIL: Status code != 200 (got: $STATUS_CODE)"
    case "$STATUS_CODE" in
        401)
            echo "   Reason: 401 Unauthorized - Invalid bot token"
            ;;
        403)
            echo "   Reason: 403 Forbidden - Missing permissions or Message Content Intent"
            ;;
        404)
            echo "   Reason: 404 Not Found - Channel not found or bot not in server"
            ;;
        *)
            echo "   Reason: Unexpected status code"
            ;;
    esac
    exit 1
fi

echo "✅ PASS: Status code is 200"

# 4. Проверяем количество сообщений
echo ""
echo "4. Checking messages..."
MESSAGES_COUNT=$(echo "$OUTPUT" | grep -E "Success: Found [0-9]+ messages" | awk '{print $3}' || echo "0")

if [ -z "$MESSAGES_COUNT" ] || [ "$MESSAGES_COUNT" = "0" ]; then
    echo "❌ FAIL: No messages found (messages == 0)"
    exit 1
fi

echo "   Messages found: $MESSAGES_COUNT"
echo "✅ PASS: Messages found >= 1"

# 5. Проверяем content_len, embeds_count, attachments_count
echo ""
echo "5. Checking message content..."
ALL_CONTENT_EMPTY=true
ALL_EMBEDS_EMPTY=true
ALL_ATTACHMENTS_EMPTY=true

# Извлекаем информацию о сообщениях
for i in 1 2 3 4 5; do
    CONTENT_LEN=$(echo "$OUTPUT" | grep -A 10 "Message $i:" | grep "Content length:" | awk '{print $3}' || echo "0")
    EMBEDS_COUNT=$(echo "$OUTPUT" | grep -A 10 "Message $i:" | grep "Embeds count:" | awk '{print $3}' || echo "0")
    ATTACHMENTS_COUNT=$(echo "$OUTPUT" | grep -A 10 "Message $i:" | grep "Attachments count:" | awk '{print $3}' || echo "0")
    
    if [ -n "$CONTENT_LEN" ] && [ "$CONTENT_LEN" != "0" ]; then
        ALL_CONTENT_EMPTY=false
    fi
    if [ -n "$EMBEDS_COUNT" ] && [ "$EMBEDS_COUNT" != "0" ]; then
        ALL_EMBEDS_EMPTY=false
    fi
    if [ -n "$ATTACHMENTS_COUNT" ] && [ "$ATTACHMENTS_COUNT" != "0" ]; then
        ALL_ATTACHMENTS_EMPTY=false
    fi
done

if [ "$ALL_CONTENT_EMPTY" = "true" ] && [ "$ALL_EMBEDS_EMPTY" = "true" ] && [ "$ALL_ATTACHMENTS_EMPTY" = "true" ]; then
    echo "❌ FAIL: All messages have content_len==0 AND embeds_count==0 AND attachments_count==0"
    echo "   Likely missing Message Content Intent"
    exit 1
fi

if [ "$ALL_CONTENT_EMPTY" = "true" ] && [ "$ALL_EMBEDS_EMPTY" = "false" ]; then
    echo "⚠️  WARNING: All content is empty, but embeds exist (no_text_only_embeds)"
    echo "   This is normal for messages with only embeds"
fi

echo "✅ PASS: Messages have content or embeds/attachments"

# Итог
echo ""
echo "=================================="
echo "✅ ALL CHECKS PASSED"
echo "=================================="
exit 0
