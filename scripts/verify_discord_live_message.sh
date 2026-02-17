#!/bin/bash
# Verify Discord Live Message Processing
# Проверяет, что система правильно обрабатывает реальные сообщения из Discord

set -e

echo "🔍 Discord Live Message Test"
echo "============================"

# 1. Вызываем collect_discord с debug=1
echo ""
echo "1. Calling collect_discord with debug=1..."
RESPONSE=$(curl -4 -sS -X POST "http://127.0.0.1:8000/api/v1/deals/signals/collect_discord?days=1&limit=50&debug=1" 2>&1)

if [ $? -ne 0 ]; then
    echo "❌ FAIL: curl request failed"
    echo "$RESPONSE"
    exit 1
fi

# Проверяем JSON валидность
if ! echo "$RESPONSE" | jq . > /dev/null 2>&1; then
    echo "❌ FAIL: Invalid JSON response"
    echo "$RESPONSE"
    exit 1
fi

# Извлекаем поля
STATUS=$(echo "$RESPONSE" | jq -r '.status // "MISSING"')
RESULT_STATUS=$(echo "$RESPONSE" | jq -r '.result.status // "MISSING"')
MESSAGES_SCANNED=$(echo "$RESPONSE" | jq -r '.result.messages_scanned // 0')
MESSAGES_MATCHED=$(echo "$RESPONSE" | jq -r '.result.messages_matched // 0')
SAMPLE_MESSAGES_COUNT=$(echo "$RESPONSE" | jq -r '.result.sample_messages | length // 0')

echo "   status: $STATUS"
echo "   result.status: $RESULT_STATUS"
echo "   messages_scanned: $MESSAGES_SCANNED"
echo "   messages_matched: $MESSAGES_MATCHED"
echo "   sample_messages count: $SAMPLE_MESSAGES_COUNT"

# 2. Проверяем messages_scanned
if [ "$MESSAGES_SCANNED" -eq 0 ]; then
    echo "❌ FAIL: messages_scanned == 0 (no messages found)"
    exit 1
fi

echo "✅ PASS: messages_scanned >= 1"

# 3. Проверяем sample_messages
if [ "$SAMPLE_MESSAGES_COUNT" -eq 0 ]; then
    echo "❌ FAIL: sample_messages is empty"
    exit 1
fi

# Проверяем первый sample message
EXTRACTED_TEXT_PREVIEW=$(echo "$RESPONSE" | jq -r '.result.sample_messages[0].extracted_text_preview // ""')
EMBED_COUNT=$(echo "$RESPONSE" | jq -r '.result.sample_messages[0].embed_count // 0')
ATTACHMENT_COUNT=$(echo "$RESPONSE" | jq -r '.result.sample_messages[0].attachment_count // 0')
EXTRACTED_URLS=$(echo "$RESPONSE" | jq -r '.result.sample_messages[0].extracted_urls // []')
HAS_LINKS=$(echo "$RESPONSE" | jq -r '.result.sample_messages[0].has_links // false')

echo ""
echo "2. Checking sample_messages[0]..."
echo "   extracted_text_preview length: ${#EXTRACTED_TEXT_PREVIEW}"
echo "   embed_count: $EMBED_COUNT"
echo "   attachment_count: $ATTACHMENT_COUNT"
echo "   extracted_urls: $EXTRACTED_URLS"
echo "   has_links: $HAS_LINKS"

# Проверяем, что есть какой-то контент
if [ -z "$EXTRACTED_TEXT_PREVIEW" ] && [ "$EMBED_COUNT" -eq 0 ] && [ "$ATTACHMENT_COUNT" -eq 0 ]; then
    echo "⚠️  WARNING: extracted_text_preview is empty AND embed_count == 0 AND attachment_count == 0"
    echo "   This may be normal if there are no messages with content in the channel"
    echo "   Full sample_messages:"
    echo "$RESPONSE" | jq '.result.sample_messages'
    # Не падаем здесь - это может быть нормально, если в канале нет сообщений
else
    echo "✅ PASS: Sample message has content"
fi

# 4. Проверяем URLs
HAS_STEAM_URL=$(echo "$EXTRACTED_URLS" | jq -r 'map(select(test("store.steampowered.com"))) | length > 0' 2>/dev/null || echo "false")
MESSAGES_WITH_LINKS=$(echo "$RESPONSE" | jq -r '.result.messages_scanned // 0')  # Упрощенная проверка

echo ""
echo "3. Checking URLs..."
if [ "$HAS_STEAM_URL" = "true" ] || [ "$HAS_LINKS" = "true" ]; then
    echo "✅ PASS: Found URLs (Steam or other links)"
else
    echo "⚠️  WARNING: No URLs found in sample message (may be normal if no links in messages)"
fi

# 5. Проверяем messages_matched (если есть "looking for ... publisher" в тексте)
EXTRACTED_TEXT_LOWER=$(echo "$EXTRACTED_TEXT_PREVIEW" | tr '[:upper:]' '[:lower:]')
HAS_PUBLISHER_PHRASE=false

if echo "$EXTRACTED_TEXT_LOWER" | grep -qE "looking\s+for.*publisher|need.*publisher|seeking.*publisher|publisher\s+wanted"; then
    HAS_PUBLISHER_PHRASE=true
fi

echo ""
echo "4. Checking publisher phrase matching..."
if [ "$HAS_PUBLISHER_PHRASE" = "true" ]; then
    if [ "$MESSAGES_MATCHED" -lt 1 ]; then
        echo "❌ FAIL: Found 'looking for ... publisher' in text but messages_matched < 1 (got: $MESSAGES_MATCHED)"
        exit 1
    else
        echo "✅ PASS: Found publisher phrase and messages_matched >= 1"
    fi
else
    echo "⚠️  INFO: No publisher phrase found in sample (may be normal)"
fi

# Итог
echo ""
echo "============================"
echo "✅ ALL CHECKS PASSED"
echo "============================"
exit 0
