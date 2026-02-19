# Intel Telegram Setup Guide

## Telegram Bot Configuration

### Step 1: Create Bot Token

1. Open [@BotFather](https://t.me/botfather) in Telegram
2. Send `/newbot` command
3. Follow instructions to create bot
4. Save the bot token (format: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`)

### Step 2: Create Channel

1. Create a Telegram channel (private recommended for testing)
2. Add your bot as administrator with "Post messages" permission
3. Get channel chat ID:
   - Forward a message from channel to [@userinfobot](https://t.me/userinfobot)
   - Or use `getUpdates` API method

### Step 3: Configure Environment

Add to your `.env` file (NOT committed to git):

```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

**Example (DO NOT use these values - they are placeholders):**
```env
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=-1001234567890
```

**⚠️ SECURITY WARNING:**
- Never commit actual tokens to git
- Never hardcode tokens in `docker-compose.yml` (use `${TELEGRAM_BOT_TOKEN}`)
- If a token was previously committed, rotate it immediately via @BotFather

### Step 4: Verify Configuration

```bash
# Check health endpoint
curl http://localhost:8000/api/v1/intel/health

# Should return:
# {
#   "telegram_configured": true,
#   ...
# }
```

### Step 5: Test Pipeline (Dry Run)

```bash
# Run pipeline in dry_run mode (no actual publishing)
curl -X POST http://localhost:8000/api/v1/intel/pipeline/run \
  -H "Content-Type: application/json" \
  -d '{"sources": ["steam_rss"], "dry_run": true}'
```

### Step 6: Run Real Pipeline

```bash
# Run actual pipeline (will publish to Telegram)
curl -X POST http://localhost:8000/api/v1/intel/pipeline/run \
  -H "Content-Type: application/json" \
  -d '{"sources": ["steam_rss"], "dry_run": false}'
```

## Security Notes

- **Never commit `.env` file to git** (it's in `.gitignore`)
- **Never share bot token publicly**
- **Rotate token if compromised** (via @BotFather)

## Troubleshooting

**"Telegram not configured" error:**
- Check that `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set in `.env`
- Restart API container: `docker compose restart api`

**"Rate limit exceeded" error:**
- Check `intel_policy.yaml` limits: `max_posts_per_hour`, `max_posts_per_day`
- Wait for rate limit window to reset

**"Event already published" (skipped):**
- This is expected behavior (idempotency)
- Check `IntelPublishLog` table for published events

## Celery Beat Schedule

Pipeline runs automatically every 2 hours via Celery beat:

```python
# In apps/worker/celery_app.py
celery_app.conf.beat_schedule = {
    "publish-steam-intel": {
        "task": "publish_steam_intel",
        "schedule": crontab(minute="*/120"),  # Every 2 hours
    },
}
```

To run beat scheduler:
```bash
docker compose exec worker celery -A apps.worker.celery_app beat
```
