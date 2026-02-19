# Intel Pipeline - Быстрый запуск

## Проверка и запуск парсера

После настройки токена в `.env`, запустите:

```bash
bash scripts/run_intel_pipeline.sh
```

Скрипт автоматически:
- ✅ Проверит health (Intel enabled, Telegram OK, DB OK)
- ✅ Проверит источники (создаст если нужно)
- ✅ Запустит pipeline и опубликует новости в Telegram
- ✅ Покажет результаты

## Или вручную через API

### 1. Проверка health:
```bash
curl http://localhost:8000/api/v1/intel/health | jq
```

Должно быть:
- `"enabled": true`
- `"telegram_ok": true`
- `"db_ok": true`

### 2. Проверка источников:
```bash
docker compose exec -T api python3 << 'EOF'
from apps.db.session import SessionLocal
from apps.intel.db.models import IntelSource
db = SessionLocal()
count = db.query(IntelSource).filter(IntelSource.is_enabled == True).count()
print(f"Active sources: {count}")
db.close()
EOF
```

Если 0, создайте источники:
```bash
curl -X POST http://localhost:8000/api/v1/intel/sources/seed
```

### 3. Запуск pipeline:
```bash
curl -X POST http://localhost:8000/api/v1/intel/pipeline/run \
  -H "Content-Type: application/json" \
  -d '{"sources": [], "dry_run": false}' | jq
```

Параметры:
- `"sources": []` - использовать все активные источники
- `"dry_run": false` - реальная публикация в Telegram

### 4. Проверка результатов:
```bash
curl http://localhost:8000/api/v1/intel/pipeline/status | jq
```

## Автоматический запуск (Celery Beat)

Pipeline запускается автоматически каждые 2 часа через Celery Beat.

Проверьте, что beat запущен:
```bash
docker compose ps beat
```

Если нет, запустите:
```bash
docker compose up -d beat
```

## Troubleshooting

**"Telegram not configured":**
- Проверьте `.env` файл: `TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID`
- Перезапустите контейнер: `docker compose restart api`

**"No active sources":**
- Запустите: `curl -X POST http://localhost:8000/api/v1/intel/sources/seed`

**"No eligible events":**
- Это нормально, если все новости уже опубликованы
- Проверьте фильтры в `apps/intel/policy/intel_policy.yaml`

**"Published: 0, Skipped: X":**
- Проверьте логи: `docker compose logs api | grep -i intel`
- Проверьте `intel_publish_logs` таблицу для причин skip
