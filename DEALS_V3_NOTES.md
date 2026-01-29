# Deals v3 Notes - YouTube API Key Configuration

## Инвентаризация (2026-01-28)

### A) Где используется YouTube API ключ

**Имя переменной окружения:**
- `YOUTUBE_API_KEY` (основной)
- `GOOGLE_API_KEY` (fallback, не используется в текущем коде)

**Места использования `os.getenv('YOUTUBE_API_KEY')`:**
1. `apps/worker/tasks/collect_youtube_trends.py:32`
2. `apps/worker/tasks/collect_youtube_events.py:34, 122`
3. `apps/worker/tasks/morning_scan.py:61`
4. `apps/worker/tasks/collect_youtube_comments.py:14`
5. `apps/worker/tasks/collect_youtube.py:39, 40` (также `YOUTUBE_MOCK_MODE`)

**Дополнительные переменные:**
- `YOUTUBE_MOCK_MODE` - включение mock режима (используется в `collect_youtube.py`)

### B) Docker Compose конфигурация

**Текущее состояние:**
- ✅ `api` контейнер: `env_file: - .env` + `YOUTUBE_API_KEY: ${YOUTUBE_API_KEY:-}`
- ✅ `worker` контейнер: `env_file: - .env` + `YOUTUBE_API_KEY: ${YOUTUBE_API_KEY:-}`
- ✅ `beat` контейнер: `env_file: - .env` + `YOUTUBE_API_KEY: ${YOUTUBE_API_KEY:-}`

**Вывод:** Ключ уже прокинут в оба контейнера через `.env` файл и явно через `environment:`.

### C) Единый источник конфигурации

**Создан файл:** `apps/worker/config/external_apis.py`

**Функции:**
- `get_youtube_api_key()` - получение ключа с поддержкой алиасов
- `get_youtube_mock_mode()` - проверка mock режима
- `assert_youtube_key()` - валидация ключа
- Константы: `YOUTUBE_API_KEY`, `YOUTUBE_MOCK_MODE`

**Логика:**
1. Приоритет: `YOUTUBE_API_KEY`
2. Fallback: `GOOGLE_API_KEY` (если YOUTUBE_API_KEY не найден)
3. Валидация: проверка на пустоту и placeholder значения

### D) Миграция кода

**Заменено:**
- Все `os.getenv('YOUTUBE_API_KEY')` → `from apps.worker.config.external_apis import YOUTUBE_API_KEY`
- Все `os.getenv('YOUTUBE_MOCK_MODE')` → `from apps.worker.config.external_apis import YOUTUBE_MOCK_MODE`

**Файлы обновлены:**
1. `apps/worker/tasks/collect_youtube_trends.py`
2. `apps/worker/tasks/collect_youtube_events.py`
3. `apps/worker/tasks/morning_scan.py`
4. `apps/worker/tasks/collect_youtube_comments.py`
5. `apps/worker/tasks/collect_youtube.py`

### E) Скрипт проверки

**Создан:** `scripts/verify_external_youtube.sh`

**Проверяет:**
1. Наличие ключа в контейнере `api`
2. Наличие ключа в контейнере `worker`
3. Валидность ключа (длина >= 20 символов)
4. Маскирует ключ в выводе (первые 4 символа + ***)

### F) DoD Checklist

- [x] `docker compose exec api env | grep -i YOUTUBE` - показывает ключ
- [x] `docker compose exec worker env | grep -i YOUTUBE` - показывает ключ
- [x] Нет прямых `os.getenv("YOUTUBE_API_KEY")` в бизнес-логике (кроме `external_apis.py`)
- [x] `bash scripts/verify_external_youtube.sh` → ✅ PASS

### G) Финальный статус (2026-01-28)

**Все задачи выполнены:**
1. ✅ Создан единый источник конфигурации `apps/worker/config/external_apis.py`
2. ✅ Заменены все `os.getenv('YOUTUBE_API_KEY')` на импорт из `external_apis.py`
3. ✅ Заменены все `os.getenv('YOUTUBE_MOCK_MODE')` на импорт из `external_apis.py`
4. ✅ Создан скрипт проверки `scripts/verify_external_youtube.sh`
5. ✅ Docker Compose уже правильно прокидывает ключ в оба контейнера

**Файлы обновлены:**
- `apps/worker/tasks/collect_youtube_trends.py`
- `apps/worker/tasks/collect_youtube_events.py`
- `apps/worker/tasks/morning_scan.py`
- `apps/worker/tasks/collect_youtube_comments.py`
- `apps/worker/tasks/collect_youtube.py`

**Команды для проверки:**
```bash
# Проверка ключа в контейнерах
docker compose exec api env | grep -i YOUTUBE
docker compose exec worker env | grep -i YOUTUBE

# Запуск скрипта проверки
bash scripts/verify_external_youtube.sh

# Перезапуск контейнеров (если нужно)
docker compose restart api worker
```
