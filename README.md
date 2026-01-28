# Game Scout

**Game Scout** — инвестиционная аналитическая платформа  
для выявления игр, которые **реально ищут издателя или инвестиции**.

Это:
- ❌ не рейтинг инди-игр
- ❌ не платформа трендов
- ❌ не витрина качества

---

## ЧТО ДЕЛАЕТ ПЛАТФОРМА

Game Scout отслеживает **внешние человеческие сигналы**
(Reddit, YouTube, Discord и др.),
чтобы находить проекты с **подтверждённым намерением сотрудничества**.

В Deals попадают **ТОЛЬКО** игры с Behavioral Intent Signal.

---

## КЛЮЧЕВЫЕ ПОНЯТИЯ

### Behavioral Intent Signal
Явное человеческое сообщение:
> «looking for publisher»,  
> «seeking funding»,  
> «pitch deck available» и т.п.

---

### Deals
Отфильтрованный список игр с реальным намерением,
а не «перспективность» или качество.

---

### Quality Score
Оценка готовности проекта,
**НЕ триггер** для попадания в Deals.

---

## Документация (канон)

**Канонические документы (источник истины):**
- [`docs/CURSOR_PROTOCOL.md`](docs/CURSOR_PROTOCOL.md) — протокол работы с платформой
- [`docs/PLATFORM_THESIS.md`](docs/PLATFORM_THESIS.md) — философия и принципы платформы
- [`docs/ANTI_PATTERNS.md`](docs/ANTI_PATTERNS.md) — антипаттерны и запрещённые практики

**Дополнительная документация:**
- [`QUICK_START.md`](QUICK_START.md) — быстрый старт
- [`CONFIGURATION.md`](CONFIGURATION.md) — конфигурация
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — архитектура системы

---

## Быстрый старт

```bash
# Запуск всех сервисов
docker compose up -d

# Проверка здоровья API
curl http://localhost:8000/api/v1/health

# Открыть дашборд
open http://localhost:8000/dashboard
```

**⚠️ Важно:** Не вставляйте в терминал текст из чата напрямую. Используйте готовые скрипты:
- `bash scripts/smoke.sh` — проверка стабильности API
- `bash scripts/ops_check.sh` — проверка состояния системы

---

## Структура проекта

- `apps/api/` — FastAPI приложение
- `apps/worker/` — Celery workers и задачи
- `apps/db/` — модели базы данных
- `migrations/` — миграции Alembic
- `scripts/` — вспомогательные скрипты
- `docs/` — каноническая документация

---

## Разработка

Перед внесением изменений обязательно прочитайте:
1. [`docs/CURSOR_PROTOCOL.md`](docs/CURSOR_PROTOCOL.md)
2. [`docs/PLATFORM_THESIS.md`](docs/PLATFORM_THESIS.md)
3. [`docs/ANTI_PATTERNS.md`](docs/ANTI_PATTERNS.md)

---

## СЛОИ СИСТЕМЫ

- `apps/worker/`  
  Сбор сигналов, скоринг, аналитика

- `apps/api/`  
  API, Deals list, Deals detail, диагностика

- `apps/api/static/`  
  Dashboard UI

---

## ОБЯЗАТЕЛЬНО К ПРОЧТЕНИЮ

- **docs/CURSOR_PROTOCOL.md**  
  Канонические правила логики платформы и работы AI-агентов.  
  Любые изменения без учёта этого файла считаются ошибкой.

---

## ЧЕГО ДЕЛАТЬ НЕЛЬЗЯ

- добавлять игры в Deals по качеству
- выводить intent из популярности
- обходить Behavioral Intent
- менять логику без явного запроса

---

## СТАТУС ПРОЕКТА

Платформа в активной разработке.  
Behavioral Intent — фундамент и не подлежит упрощению.

---

## API

- `/api/v1/deals/list`
- `/api/v1/deals/{app_id}/detail`
- `/api/v1/deals/diagnostics`

---

Game Scout — это инструмент поддержки инвестиционных решений,  
а не медиа-продукт и не discovery-движок.
