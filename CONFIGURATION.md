# Game Scout Configuration Guide

## Quick Start

1. Copy `.env.example` to `.env`:
```bash
   cp .env.example .env
```

2. Configure required services:
   - **Database**: PostgreSQL (default config works with Docker)
   - **Redis**: Redis (default config works with Docker)

3. Start all services:
```bash
   bash scripts/up_all.sh
   # or manually:
   docker compose up -d postgres redis api beat worker worker_trends
```

4. Optional: Add API keys for full functionality

## Required Configuration

### Services Overview

Game Scout requires these services to be running:

- **postgres**: PostgreSQL database (stores all data)
- **redis**: Redis cache and Celery message broker
- **api**: FastAPI web server (REST API)
- **worker**: Celery worker (processes background tasks for Reddit/YouTube/TikTok/Twitter/Discord)
- **beat**: Celery beat scheduler (runs scheduled tasks)
- **worker_trends**: Trends analysis worker (optional, for trends pipeline)

**Important**: Without `worker` running, data collection from external sources (YouTube, TikTok, Twitter, Reddit, Discord) will not work. The `beat` service schedules periodic tasks, but they require `worker` to execute.

### Database & Redis
These work out-of-box with Docker Compose:
```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@postgres:5432/game_scout
REDIS_URL=redis://redis:6379/0
```

## Optional Configuration

### YouTube Data API (for video collection)

**Without API key**: System uses mock data (good for testing)

**With API key**:
1. Go to https://console.cloud.google.com/
2. Create a project
3. Enable YouTube Data API v3
4. Create credentials (API key)
5. Add to `.env`:
```env
   YOUTUBE_API_KEY=your_actual_key_here
   YOUTUBE_MOCK_MODE=false
```

### Anthropic API (for comment analysis)

**Without API key**: Comment analysis is skipped (system still works)

**With API key**:
1. Go to https://console.anthropic.com/
2. Create API key
3. Add to `.env`:
```env
   ANTHROPIC_API_KEY=your_actual_key_here
```

### TikTok Collection

**Default mode**: Scraping (no API needed, may be blocked)

---

## Intel Module Configuration

**Intel** is a news and signal collection system for Steam games. It collects mentions/news from external sources, processes them, and can publish to Telegram.

### Enabling Intel

Intel is **disabled by default** for safety. To enable:

```env
INTEL_ENABLED=true
```

### Feature Flags

```env
# Enable Intel module (required)
INTEL_ENABLED=false

# Dry-run mode: processes data but doesn't publish (recommended for testing)
INTEL_DRY_RUN=true

# Auto-publish to Telegram (requires INTEL_ENABLED=true and INTEL_DRY_RUN=false)
INTEL_AUTO_PUBLISH=false

# Only auto-publish "safe" event types (release, patch_major, discount)
INTEL_AUTO_PUBLISH_SAFE_ONLY=true
```

### Rate Limits

```env
# Maximum posts per hour/day
INTEL_MAX_POSTS_PER_HOUR=5
INTEL_MAX_POSTS_PER_DAY=30
```

### Source Filtering

```env
# Only allow sources from allowlist (recommended)
INTEL_SOURCES_ALLOWLIST_ONLY=true
```

### LLM Configuration

Intel uses separate LLM settings from main pipeline:

```env
INTEL_LLM_PROVIDER=anthropic
INTEL_LLM_MODEL_FAST=claude-3-5-haiku-20241022
INTEL_LLM_MODEL_STRONG=claude-3-5-sonnet-20241022
```

### Telegram Setup

1. Create a Telegram bot via [@BotFather](https://t.me/botfather)
2. Get bot token
3. Create a channel (private recommended for testing)
4. Add bot as admin with "Post messages" permission
5. Get chat ID (use `getUpdates` API or check channel posts)

```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

### Pipeline Configuration

```env
# How often to collect new items (in minutes)
INTEL_COLLECT_INTERVAL_MINUTES=60

# Batch size for processing
INTEL_PIPELINE_BATCH_SIZE=50
```

### Recommended Setup Flow

1. **Testing mode** (safe):
   ```env
   INTEL_ENABLED=true
   INTEL_DRY_RUN=true
   INTEL_AUTO_PUBLISH=false
   ```

2. **Manual review mode**:
   ```env
   INTEL_ENABLED=true
   INTEL_DRY_RUN=false
   INTEL_AUTO_PUBLISH=false
   ```
   Review events in dashboard, publish manually.

3. **Safe auto-publish**:
   ```env
   INTEL_ENABLED=true
   INTEL_DRY_RUN=false
   INTEL_AUTO_PUBLISH=true
   INTEL_AUTO_PUBLISH_SAFE_ONLY=true
   ```

### Adding Sources

Sources are managed via API or database. See Intel dashboard tab for UI.

### Debugging

Check logs:
```bash
docker compose logs worker | grep intel
docker compose logs beat | grep intel
```

---

## Guardrails

Quality gates are enforced via `scripts/guardrail.sh` to ensure:
- No unexpected file deletions
- Alembic migration chain validity
- Python syntax correctness
- No unauthorized changes to existing migrations

### Running Guardrails

```bash
bash scripts/guardrail.sh
```

**Always run guardrails before committing** to ensure code quality and prevent breaking changes.

Guardrails check:
1. No unexpected file deletions
2. Alembic chain validity (single head)
3. Python syntax in Intel module
4. No changes to existing migrations (001-008)

See `.cursor/rules/guardrails.md` and `SPECS/WORKFLOW.md` for full workflow rules.

---

## Dev Orchestrator (Autopilot C+)

Single-command development orchestrator that runs all checks and validations, with optional automatic fixes.

### Quick Start

**One-button mode (recommended):**

```bash
bash scripts/gs-dev.sh
```

**With automatic fixes:**

```bash
bash scripts/gs-dev.sh --autofix
```

**Diagnostic mode (verify setup without running tests):**

```bash
bash scripts/verify_autopilot.sh
```

This command:
1. Ensures Docker services are running
2. Waits for API readiness (up to 60 seconds)
3. Runs dev_supervisor with all checks:
   - Guardrails (file deletions, migration changes, Python syntax)
   - Migration chain validation
   - Alembic upgrade head
   - Intel contract validation
   - Contract tests (pytest)
   - Orchestrator smoke test (RSS collection to intel_raw_items)
4. Returns exit code 0 if all checks pass (STABLE)

**With automatic fixes:**

```bash
./scripts/gs-dev.sh --autofix
```

This mode:
- Runs all checks as above
- If any check fails, attempts to apply safe automatic fixes
- Retries checks after fixes (max 2 iterations)
- Commits fixes automatically with "autofix: ..." messages
- Returns exit code 0 if checks pass after fixes

### What Gets Checked

- **Guardrails**: File deletions, migration changes, Python syntax
- **Migration Chain**: Alembic chain validity, upgrade head
- **Contract Validation**: Intel module contracts, policy engine
- **Contract Tests**: pytest tests_contract/
- **Smoke Test**: Actual RSS collection to intel_raw_items (verifies DB writes)

### Automatic Fixes (Whitelist)

When `--autofix` is enabled, the system can automatically fix:

1. **Missing import subprocess** in orchestrator_smoke.py
2. **Missing git** in Dockerfiles (for guardrail.sh)
3. **Missing pytest** in pyproject.toml
4. **Missing smoke script** (creates scripts/intel_smoke_collect_rss.py)
5. **Missing Intel router** in apps/api/main.py (if health endpoint 404)

All fixes are:
- **Idempotent**: Safe to apply multiple times
- **Committed**: Each fix creates a git commit
- **Safe**: Never deletes files or modifies migrations

### Exit Codes

- `0`: All checks passed (STABLE)
- `1`: One or more checks failed (FAILED)
- `2`: Script run inside container (must run on host)

### Troubleshooting

**If checks fail:**

1. Check the supervisor report output (printed at the end)
2. Look for specific error messages in the report
3. Try running with `--autofix` to attempt automatic fixes
4. Check Docker logs: `docker compose logs api`

**If health endpoint returns 404:**

- Verify Intel router is included in `apps/api/main.py`
- Check that `INTEL_ENABLED=true` in `.env` (if required)
- Run with `--autofix` to automatically add router inclusion

**If smoke test fails:**

- Verify database is accessible: `docker compose exec -T api python -c "from apps.db.session import SessionLocal; db = SessionLocal(); print('DB OK')"`
- Check IntelSource exists: `docker compose exec -T api python scripts/intel_smoke_collect_rss.py`
- Verify network access (RSS feed must be reachable)

### Running Individual Checks

You can also run checks individually inside Docker:

```bash
# Run guardrails
docker compose exec -T api bash scripts/guardrail.sh

# Run smoke test
docker compose exec -T api python scripts/intel_smoke_collect_rss.py

# Run contract tests
docker compose exec -T api python -m pytest tests_contract/ -v

# Run supervisor manually
docker compose exec -T api python dev_supervisor/run.py

# Run supervisor with autofix
docker compose exec -T api python dev_supervisor/run.py --autofix
```

**API mode** (if you have TikTok API access):
```env
TIKTOK_MODE=api
TIKTOK_API_URL=your_tiktok_api_url
TIKTOK_API_KEY=your_tiktok_api_key
```

## Feature Matrix

| Feature | Works Without APIs | Full Functionality |
|---------|-------------------|-------------------|
| Steam Collection | ✅ Yes | ✅ Yes |
| Itch Collection | ✅ Yes | ✅ Yes |
| Wishlist Ranks (EWI) | ✅ Yes | ✅ Yes |
| YouTube Videos | ⚠️ Mock data | ✅ Real data |
| TikTok Videos | ⚠️ Mock/scraped | ✅ API data |
| Comment Analysis | ❌ Skipped | ✅ Full LLM analysis |
| Investment Scoring | ✅ Yes (basic) | ✅ Yes (full) |

## Testing Configuration

To verify your configuration:
```bash
# Verify all services are running
bash scripts/verify_workers_and_sources.sh

# Test database connection
docker-compose exec postgres psql -U postgres -d game_scout -c "SELECT 1;"

# Test Redis connection
docker-compose exec redis redis-cli ping

# Test YouTube (if configured)
curl -X POST "http://localhost:8000/api/v1/narrative/test-youtube-collector?game_id=YOUR_GAME_ID"

# Test investment scoring
curl -X POST "http://localhost:8000/api/v1/narrative/test-investment-scoring?game_id=YOUR_GAME_ID"

# View analytics dashboard
curl http://localhost:8000/api/v1/analytics/dashboard
```

## Advanced Configuration

### Custom Scoring Weights

Adjust investment scoring formulas in `.env`:
```env
PP_WEIGHT=0.4   # Product Potential importance
GTM_WEIGHT=0.3  # Go-to-Market importance
GAP_WEIGHT=0.3  # GAP (difference) importance
```

### Collection Limits

Control how much data is collected:
```env
STEAM_COLLECTION_LIMIT=100
ITCH_COLLECTION_LIMIT=50
WISHLIST_RANK_LIMIT=100
COMMENT_SAMPLE_SIZE=200
```

### Schedule Configuration

Celery Beat schedules are configured in `apps/worker/celery_app.py`:
- Steam collection: 07:00 daily
- Itch collection: 07:15 daily
- Wishlist ranks: 06:30 daily

To change schedules, modify the `celery_beat_schedule` in `celery_app.py`.

## Troubleshooting

### "YouTube API key not configured"
- System will use mock data
- Add real API key to `.env` for actual YouTube data

### "LLM API key not configured"
- Comment analysis will be skipped
- Add Anthropic API key to `.env` for full analysis

### "TikTok scraping blocked"
- TikTok actively blocks scrapers
- System will generate mock data
- Consider getting official TikTok API access

### Database connection errors
- Ensure PostgreSQL container is running: `docker-compose ps`
- Check DATABASE_URL in `.env`
- Restart containers: `docker-compose restart`

## Production Deployment

For production use:

1. **Security**:
```env
   DEBUG=false
   # Use strong passwords for database
   # Restrict CORS origins in main.py
```

2. **Performance**:
```env
   # Increase worker concurrency
   # Add connection pooling
   # Enable Redis persistence
```

3. **Monitoring**:
   - Enable Celery events
   - Add logging aggregation
   - Set up health checks

4. **Backup**:
   - Regular PostgreSQL backups
   - Environment file backup
   - Redis snapshot configuration
