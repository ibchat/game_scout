# Intel Pipeline Runbook

## Quick Start (One Command)

```bash
bash scripts/gs-dev.sh
```

This command:
1. Ensures Docker services are running
2. Runs dev supervisor (guardrails, migrations, tests, smoke)
3. Runs Intel production check
4. Exits with code 0 if STABLE, 1 if FAILED

## Production Check

Standalone production check script:

```bash
docker compose exec api bash scripts/intel_production_check.sh
```

Or from host (if script is accessible):

```bash
bash scripts/intel_production_check.sh
```

## Manual Pipeline Run

### Dry Run (Test)

```bash
curl -X POST http://localhost:8000/api/v1/intel/pipeline/run \
  -H "Content-Type: application/json" \
  -d '{"sources": ["Steam RSS test"], "dry_run": true}'
```

### Real Run

```bash
curl -X POST http://localhost:8000/api/v1/intel/pipeline/run \
  -H "Content-Type: application/json" \
  -d '{"sources": ["Steam RSS test"], "dry_run": false}'
```

## Telegram Test

### Check Access (Dry Run)

```bash
curl -X POST http://localhost:8000/api/v1/intel/telegram/test \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true}'
```

### Send Test Message

```bash
curl -X POST http://localhost:8000/api/v1/intel/telegram/test \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false, "text": "🧪 Test message"}'
```

## Health Check

```bash
curl http://localhost:8000/api/v1/intel/health | python3 -m json.tool
```

Expected:
- `enabled: true`
- `telegram_ok: true`
- `db_ok: true`

## Pipeline Status

```bash
curl http://localhost:8000/api/v1/intel/pipeline/status | python3 -m json.tool
```

## Automated Runs

Pipeline runs automatically every 2 hours via Celery Beat:
- Task: `publish_steam_intel`
- Schedule: Every 2 hours (`crontab(minute="*/120")`)
- Uses all enabled RSS sources automatically

Check logs:
```bash
docker compose logs worker beat | grep -i "publish_steam_intel"
```

## Troubleshooting

### No publications (published=0)

1. Check health: `curl http://localhost:8000/api/v1/intel/health`
2. Check pipeline status: `curl http://localhost:8000/api/v1/intel/pipeline/status`
3. Check skipped reasons:
   ```sql
   SELECT error, COUNT(*) FROM intel_publish_log WHERE status = 'skipped' GROUP BY error;
   ```
4. Check eligible events:
   ```sql
   SELECT COUNT(*) FROM intel_events WHERE autopublish_eligible = true;
   ```

### Briefs not generated

1. Check events have content:
   ```sql
   SELECT id, title_ru, what_happened_ru FROM intel_events WHERE autopublish_eligible = true LIMIT 5;
   ```
2. Check logs: `docker compose logs api | grep -i "brief"`

### Telegram errors

1. Check token: `docker compose exec api printenv | grep TELEGRAM`
2. Test access: `curl -X POST http://localhost:8000/api/v1/intel/telegram/test -H "Content-Type: application/json" -d '{"dry_run": true}'`
3. Check publish logs:
   ```sql
   SELECT status, error FROM intel_publish_log WHERE status = 'failed' ORDER BY published_at DESC LIMIT 5;
   ```

## Security

⚠️ **IMPORTANT**: Telegram token must NOT be in git.

Guardrail check:
```bash
bash scripts/guardrail.sh
```

If token leak detected:
1. Remove token from tracked files
2. Use `.env` file (already in `.gitignore`)
3. Rotate token via @BotFather
