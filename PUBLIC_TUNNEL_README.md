# Public Tunnel для Mobile доступа к Dashboard

## Описание

Система позволяет открывать дашборд Game Scout с телефона через публичный туннель (ngrok или Cloudflare), когда API работает на localhost:8000.

## Быстрый старт

### 1. Запуск туннеля

```bash
# С ngrok
ENABLE_PUBLIC_TUNNEL=1 PUBLIC_TUNNEL_PROVIDER=ngrok bash scripts/start_tunnel.sh

# С Cloudflare
ENABLE_PUBLIC_TUNNEL=1 PUBLIC_TUNNEL_PROVIDER=cloudflare bash scripts/start_tunnel.sh
```

### 2. Остановка туннеля

```bash
bash scripts/stop_tunnel.sh
```

### 3. Проверка работы

```bash
bash scripts/verify_public_demo.sh
```

## Переменные окружения

- `ENABLE_PUBLIC_TUNNEL=1` - включить публичный туннель
- `PUBLIC_TUNNEL_PROVIDER=ngrok|cloudflare` - провайдер туннеля
- `PUBLIC_TUNNEL_URL=https://...` - если задан вручную, используется как есть
- `PUBLIC_DEMO_TOKEN=your_secret_token` - токен для защиты (опционально)

## Защита токеном

Если установлен `PUBLIC_DEMO_TOKEN`, все запросы к `/dashboard` и `/api/v1/*` требуют:
- Header: `X-Demo-Token: <token>`
- или query parameter: `?token=<token>`

**Важно:** Если токен не установлен, в system summary будет предупреждение.

## API Endpoints

### GET /api/v1/admin/system/public_url

Возвращает информацию о публичном URL:

```json
{
  "enabled": true,
  "provider": "ngrok",
  "public_url": "https://xxxx.ngrok.io",
  "dashboard_url": "https://xxxx.ngrok.io/dashboard",
  "updated_at": "2026-01-27T18:00:00Z",
  "source": "runtime_file|env|none"
}
```

## UI

Публичный URL отображается на вкладке **📊 Система** в секции "Public Demo URL":
- Статус (ON/OFF)
- Provider
- Кликабельная ссылка на dashboard
- Кнопка Copy для копирования URL
- Предупреждение, если токен не установлен

## Файлы

- `scripts/start_tunnel.sh` - запуск туннеля
- `scripts/stop_tunnel.sh` - остановка туннеля
- `scripts/verify_public_demo.sh` - проверка работы
- `.runtime/public_tunnel_url.txt` - сохраненный URL туннеля
- `.runtime/ngrok.pid` / `.runtime/cloudflared.pid` - PID процессов

## Требования

- **ngrok**: `brew install ngrok/ngrok/ngrok`
- **cloudflared**: `brew install cloudflare/cloudflare/cloudflared`

## Troubleshooting

1. **Туннель не запускается**: Проверьте, что API доступен на `http://localhost:8000`
2. **URL не отображается**: Проверьте, что `ENABLE_PUBLIC_TUNNEL=1` установлен
3. **Токен не работает**: Убедитесь, что `PUBLIC_DEMO_TOKEN` установлен и передается в запросах
