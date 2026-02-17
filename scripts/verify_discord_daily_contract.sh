#!/usr/bin/env bash
set -e

echo "=== Verify Discord Daily Contract ==="

# 1. Вызываем endpoint
echo "1. Calling collect_discord endpoint..."
RESPONSE=$(curl -4 -sS -X POST "http://127.0.0.1:8000/api/v1/deals/signals/collect_discord?days=1&limit=50" 2>&1)

if [[ -z "$RESPONSE" ]]; then
  echo "❌ FAIL: Empty response from endpoint"
  exit 1
fi

# 2. Проверяем JSON структуру (все обязательные поля)
echo "2. Checking response structure..."

# Проверяем, что это валидный JSON
if ! echo "$RESPONSE" | jq . > /dev/null 2>&1; then
  echo "❌ FAIL: Invalid JSON response"
  echo "Response: $RESPONSE"
  exit 1
fi

# Проверяем наличие обязательных полей через has()
HAS_STATUS=$(echo "$RESPONSE" | jq -r 'has("status")' 2>/dev/null || echo "false")
HAS_RESULT=$(echo "$RESPONSE" | jq -r 'has("result")' 2>/dev/null || echo "false")
HAS_RESULT_STATUS=$(echo "$RESPONSE" | jq -r '.result | has("status")' 2>/dev/null || echo "false")
HAS_MESSAGES_SCANNED=$(echo "$RESPONSE" | jq -r '.result | has("messages_scanned")' 2>/dev/null || echo "false")
HAS_MESSAGES_MATCHED=$(echo "$RESPONSE" | jq -r '.result | has("messages_matched")' 2>/dev/null || echo "false")
HAS_SIGNALS_SAVED=$(echo "$RESPONSE" | jq -r '.result | has("signals_saved")' 2>/dev/null || echo "false")
HAS_APP_IDS_DISCOVERED=$(echo "$RESPONSE" | jq -r '.result | has("app_ids_discovered")' 2>/dev/null || echo "false")
HAS_RATE_LIMITED=$(echo "$RESPONSE" | jq -r '.result | has("rate_limited")' 2>/dev/null || echo "false")
HAS_ERRORS=$(echo "$RESPONSE" | jq -r '.result | has("errors")' 2>/dev/null || echo "false")

if [[ "$HAS_STATUS" != "true" ]]; then
  echo "❌ FAIL: Missing 'status' field"
  echo "Response: $RESPONSE"
  exit 1
fi

if [[ "$HAS_RESULT" != "true" ]] || [[ "$HAS_RESULT_STATUS" != "true" ]] || \
   [[ "$HAS_MESSAGES_SCANNED" != "true" ]] || [[ "$HAS_MESSAGES_MATCHED" != "true" ]] || \
   [[ "$HAS_SIGNALS_SAVED" != "true" ]] || [[ "$HAS_APP_IDS_DISCOVERED" != "true" ]] || \
   [[ "$HAS_RATE_LIMITED" != "true" ]] || [[ "$HAS_ERRORS" != "true" ]]; then
  echo "❌ FAIL: Missing required fields in result"
  echo "Response: $RESPONSE"
  exit 1
fi

# Проверяем, что errors - это массив
ERRORS_TYPE=$(echo "$RESPONSE" | jq -r '.result.errors | type' 2>/dev/null || echo "NOT_ARRAY")
if [[ "$ERRORS_TYPE" != "array" ]]; then
  echo "❌ FAIL: result.errors is not an array (type: $ERRORS_TYPE)"
  exit 1
fi

# Получаем значения для дальнейшей проверки
RESULT_STATUS=$(echo "$RESPONSE" | jq -r '.result.status' 2>/dev/null || echo "")

echo "✅ Response structure OK"

# 3. Определяем режим (placeholder vs real token)
TOKEN_VALUE=$(docker compose exec -T worker sh -c 'env | grep "^DISCORD_BOT_TOKEN=" || echo ""' 2>&1 | grep -v "time=" | grep -v "level=" | sed 's/^DISCORD_BOT_TOKEN=//' || echo "")

IS_PLACEHOLDER=false
PLACEHOLDERS=("PUT_REAL_TOKEN_HERE" "PASTE_REAL_DISCORD_BOT_TOKEN_HERE" "REAL_TOKEN" "YOUR_REAL_TOKEN" "<EMPTY>")

for placeholder in "${PLACEHOLDERS[@]}"; do
  if [[ "$TOKEN_VALUE" == "$placeholder" ]]; then
    IS_PLACEHOLDER=true
    break
  fi
done

if [[ ${#TOKEN_VALUE} -lt 20 ]]; then
  IS_PLACEHOLDER=true
fi

# 4. Проверяем логику в зависимости от режима
echo "3. Checking token configuration logic..."

if [[ "$IS_PLACEHOLDER" == "true" ]]; then
  echo "   Token is placeholder: $TOKEN_VALUE"
  # Если токен placeholder - должен быть skipped с "not configured"
  if [[ "$RESULT_STATUS" != "skipped" ]]; then
    echo "❌ FAIL: Expected result.status='skipped' for placeholder token, got '$RESULT_STATUS'"
    exit 1
  fi
  
  ERROR_TEXT=$(echo "$RESPONSE" | jq -r '.result.errors[0] // ""' 2>/dev/null || echo "")
  if [[ "$ERROR_TEXT" != *"not configured"* ]]; then
    echo "❌ FAIL: Expected 'not configured' in errors for placeholder token"
    echo "   Errors: $ERROR_TEXT"
    exit 1
  fi
  
  echo "✅ Placeholder token logic OK (skipped with 'not configured')"
else
  echo "   Token looks valid (length: ${#TOKEN_VALUE})"
  # Если токен валидный - НЕ должен быть skipped по причине "not configured"
  ERROR_TEXT=$(echo "$RESPONSE" | jq -r '.result.errors[] // ""' 2>/dev/null | grep -i "not configured" || echo "")
  
  if [[ -n "$ERROR_TEXT" ]]; then
    echo "❌ FAIL: Found 'not configured' error for valid token"
    echo "   Errors: $(echo "$RESPONSE" | jq -r '.result.errors' 2>/dev/null)"
    exit 1
  fi
  
  # Допускается "ok" или "error" (например, если Discord auth/network), но не "skipped" из-за токена
  if [[ "$RESULT_STATUS" == "skipped" ]]; then
    # Проверяем, что skipped не из-за токена
    ERROR_TEXT=$(echo "$RESPONSE" | jq -r '.result.errors[] // ""' 2>/dev/null | grep -i "not configured" || echo "")
    if [[ -n "$ERROR_TEXT" ]]; then
      echo "❌ FAIL: Valid token but got 'skipped' with 'not configured'"
      exit 1
    fi
  fi
  
  echo "✅ Valid token logic OK (no 'not configured' error)"
fi

echo "✅ PASS: Contract verification complete"
