#!/bin/bash
# Debug script to fetch Discord messages directly via REST API
# Helps diagnose why content might be empty (intents/permissions)

set -e

CHANNEL_ID="${1:-1467902661608341595}"  # Default: канал "основной"

echo "🔍 Discord Message Fetch Debug"
echo "================================"
echo "Channel ID: $CHANNEL_ID"
echo ""

# Проверяем и запускаем worker если нужно
WORKER_STATUS=$(docker compose ps worker --format "{{.Status}}" 2>/dev/null | head -1 || echo "not_running")

if [ -z "$WORKER_STATUS" ] || [ "$WORKER_STATUS" = "not_running" ] || echo "$WORKER_STATUS" | grep -qE "Exited|Restarting|not_running"; then
    echo "⚠️  Worker not running, starting..."
    docker compose up -d worker > /dev/null 2>&1
    sleep 2
    # Проверяем еще раз
    WORKER_STATUS=$(docker compose ps worker --format "{{.Status}}" 2>/dev/null | head -1 || echo "not_running")
    if echo "$WORKER_STATUS" | grep -qE "Exited|Restarting|not_running"; then
        echo "❌ ERROR: Failed to start worker (status: $WORKER_STATUS)"
        echo "   Check logs: docker compose logs worker"
        exit 1
    fi
    echo "✅ Worker started"
    echo ""
fi

# Выполняем Python скрипт внутри worker контейнера
docker compose exec -T worker python - <<PY
import os
import requests
import json
import sys

# Получаем CHANNEL_ID из аргументов или окружения
CHANNEL_ID = "${CHANNEL_ID}"

# Получаем токен
token = (os.getenv("DISCORD_BOT_TOKEN") or "").strip()
token_len = len(token)
token_prefix = token[:8] if len(token) >= 8 else "TOO_SHORT"

print(f"Token length: {token_len}")
print(f"Token prefix: {token_prefix[:6]}...")
print("")

if not token or token_len < 50:
    print("❌ ERROR: DISCORD_BOT_TOKEN not set or too short")
    sys.exit(1)

# Discord API endpoint
url = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages"
headers = {
    "Authorization": f"Bot {token}",
    "User-Agent": "GameScout/1.0"
}
params = {"limit": 5}

try:
    response = requests.get(url, headers=headers, params=params, timeout=15)
    status_code = response.status_code
    
    print(f"Status Code: {status_code}")
    print("")
    
    if status_code == 200:
        data = response.json()
        if isinstance(data, list):
            print(f"✅ Success: Found {len(data)} messages")
            print("")
            
            for i, msg in enumerate(data[:5], 1):
                msg_id = msg.get("id", "N/A")
                msg_type = msg.get("type", "N/A")
                author = msg.get("author", {})
                author_username = author.get("username", "N/A")
                content = msg.get("content", "")
                content_len = len(content)
                content_preview = content[:100] if content else ""
                embeds = msg.get("embeds", [])
                embeds_count = len(embeds)
                attachments = msg.get("attachments", [])
                attachments_count = len(attachments)
                timestamp = msg.get("timestamp", "N/A")
                
                print(f"Message {i}:")
                print(f"  ID: {msg_id}")
                print(f"  Type: {msg_type}")
                print(f"  Author: {author_username}")
                print(f"  Content length: {content_len}")
                print(f"  Content preview: {content_preview}")
                print(f"  Embeds count: {embeds_count}")
                print(f"  Attachments count: {attachments_count}")
                print(f"  Timestamp: {timestamp}")
                print("")
        else:
            print("❌ ERROR: Unexpected response format (not a list)")
            print(f"Response: {json.dumps(data, indent=2)}")
    elif status_code == 401:
        print("❌ ERROR: 401 Unauthorized - Invalid bot token")
        try:
            error_data = response.json()
            print(f"Error: {json.dumps(error_data, indent=2)}")
        except:
            print(f"Response: {response.text[:200]}")
    elif status_code == 403:
        print("❌ ERROR: 403 Forbidden - Missing permissions or Message Content Intent")
        try:
            error_data = response.json()
            print(f"Error: {json.dumps(error_data, indent=2)}")
        except:
            print(f"Response: {response.text[:200]}")
    elif status_code == 404:
        print("❌ ERROR: 404 Not Found - Channel not found or bot not in server")
        try:
            error_data = response.json()
            print(f"Error: {json.dumps(error_data, indent=2)}")
        except:
            print(f"Response: {response.text[:200]}")
    else:
        print(f"❌ ERROR: Unexpected status code {status_code}")
        try:
            error_data = response.json()
            print(f"Response: {json.dumps(error_data, indent=2)}")
        except:
            print(f"Response: {response.text[:200]}")
            
except Exception as e:
    print(f"❌ ERROR: Exception occurred: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
PY
