# Telegram Chat ID Setup

## Quick Setup

To get your Telegram channel chat ID, you have several options:

### Option 1: Using getUpdates API (Recommended)

1. Add the bot to your channel as administrator with "Post messages" permission
2. Send a test message to the channel (or forward a message from channel to the bot)
3. Run the helper script:

```bash
# Replace <YOUR_BOT_TOKEN> with your actual token from @BotFather
docker compose exec -T api python scripts/get_telegram_chat_id.py <YOUR_BOT_TOKEN>
```

The script will show all recent chats, including channel IDs.

### Option 2: Using @userinfobot

1. Forward a message from your channel to [@userinfobot](https://t.me/userinfobot)
2. The bot will reply with the channel chat ID (format: `-1001234567890`)

### Option 3: Manual Configuration (Recommended)

1. Get the chat ID using one of the methods above
2. Add to `.env` file (NOT committed to git):

```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=-1001234567890  # Your channel chat ID here
```

3. Restart the API container:

```bash
docker compose up -d --force-recreate api
```

**⚠️ SECURITY:**
- Never hardcode tokens in `docker-compose.yml` (use `${TELEGRAM_BOT_TOKEN}`)
- Always use `.env` file for secrets (already in `.gitignore`)

### Option 4: Auto-Detection (If bot received messages)

The system will automatically try to detect chat_id from bot updates. If the bot has received messages from the channel, it will auto-detect the chat_id.

To trigger auto-detection:
1. Add bot to channel as administrator
2. Send a message to the channel
3. The system will detect the chat_id automatically

## Verification

After setting up, check the health endpoint:

```bash
curl http://localhost:8000/api/v1/intel/health | jq .telegram_ok
```

Should return `true` if everything is configured correctly.

## Notes

- Channel chat IDs typically start with `-100` (e.g., `-1001234567890`)
- Private channel IDs are negative numbers
- Public channels can use `@channel_username` format, but numeric ID is preferred
- **Never commit tokens or chat IDs to git** - always use `.env` file (already in `.gitignore`)
- If a token was previously committed, rotate it immediately via @BotFather
