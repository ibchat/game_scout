# TZ_DISCORD_INGESTION_STUB — Discord Signal Ingestion (Stub)

## Цель
Подготовить план для будущей реализации сбора Deal Intent Signals из Discord.

## Часть D — Discord (Vector next, без кода сейчас)

### D1) Каналы для мониторинга

**Рекомендуемые каналы:**
- `#looking-for-publisher` (gamedev серверы)
- `#business` (gamedev серверы)
- `#publishing` (gamedev серверы)
- `#funding` (gamedev серверы)
- `#marketing` (gamedev серверы)
- `#partnerships` (gamedev серверы)

**Серверы:**
- GameDev серверы (Discord Game Developers, Indie Game Developers, etc.)
- Publisher серверы (если есть публичные каналы)
- Festival серверы (Next Fest, Steam Fest, etc.)

### D2) Паттерны для обнаружения

**Publisher intent:**
- "looking for publisher"
- "seeking publisher"
- "publisher wanted"
- "need publisher"
- "publishing partner"

**Funding intent:**
- "looking for funding"
- "seeking investment"
- "investor wanted"
- "need funding"

**Marketing help:**
- "need marketing help"
- "marketing support"
- "help with marketing"
- "seeking marketing partner"

### D3) Извлечение app_id

**Правила:**
- ТОЛЬКО Steam links: `store.steampowered.com/app/<app_id>`
- ТОЛЬКО Steam links: `steamcommunity.com/app/<app_id>`
- НЕ извлекать из других источников (itch.io, etc.)

**Формат ссылок:**
- `https://store.steampowered.com/app/123456/`
- `https://steamcommunity.com/app/123456/`
- `store.steampowered.com/app/123456` (без протокола)

### D4) Структура данных

**Таблица:** `deal_intent_signal`

**Поля:**
- `app_id` (BIGINT) - извлеченный из ссылки
- `source` = `"discord"`
- `url` = permalink сообщения или канала
- `text` = текст сообщения
- `signal_type` = `"behavioral_intent"` или `"intent_keyword"`
- `published_at` = timestamp сообщения
- `created_at` = now()

**Idempotency:**
- `ON CONFLICT (source, url) DO NOTHING`

### D5) Реализация (будущее)

**Требования:**
- Discord Bot Token (для доступа к каналам)
- Rate limiting (Discord API limits)
- Обработка permissions (read message history)
- Обработка deleted messages
- Обработка edited messages (опционально)

**Технические детали:**
- Использовать `discord.py` или `discord.js`
- Webhook для real-time обновлений (опционально)
- Batch processing для исторических данных

### D6) Интеграция с pipeline

**Последовательность:**
1. Discord signals → `deal_intent_signal`
2. `enrich_from_recent_signals` → обогащение метаданных
3. `/api/v1/deals/list` → витрина

**Частота:**
- Real-time (webhook) - опционально
- Daily scan - обязательно
- Historical scan - один раз при запуске

---

## Примечания

- Этот документ является stub и не требует реализации сейчас
- Реализация будет добавлена в будущем как Vector C или Vector D
- Все паттерны и правила должны быть согласованы с TZ_SIGNAL_INGESTION_MASTER.md
