# TZ: Synthetic UI Check (DEALS) — минимальные и безопасные изменения

Цель: иметь 1–3 синтетические записи, которые гарантированно попадают в /api/v1/deals/list и помогают проверять UI (таблица, карточка, сигналы, вердикт). Изменения должны быть минимальные, не ломать текущий pipeline и не менять логику скоринга.

## Инварианты (НЕ ТРОГАТЬ)
- Не менять SQL-гейты в deals/list (кроме добавления НЕОБЯЗАТЕЛЬНОГО фильтра synthetic_only).
- Не менять analyze_deal_intent / scorer.
- Не менять таблицы и миграции.
- Не вводить новые зависимости.
- Не трогать dashboard.

## Что уже есть (контекст)
В БД уже есть тест-кейс:
- app_id=1410400 (Kejora) присутствует в /api/v1/deals/list
- verdict=early_request
- сигналы:
  - intent_keyword, reddit, текст с [SYNTHETIC]...
  - behavioral_intent, reddit, текст с [SYNTHETIC]...

Проверка SQL:
SELECT signal_type, source, confidence, published_at, left(text,120) FROM deal_intent_signal WHERE app_id=1410400;

## Deliverable A — один безопасный флаг synthetic_only в /api/v1/deals/list
Добавить query-param:
- synthetic_only: bool = false

Поведение:
- Если synthetic_only=false: НИЧЕГО НЕ МЕНЯЕТСЯ.
- Если synthetic_only=true: endpoint возвращает ТОЛЬКО игры, у которых есть хотя бы 1 сигнал с признаком синтетики.

Признак синтетики (строго один из):
- deal_intent_signal.text ILIKE '[SYNTHETIC]%'
ИЛИ
- deal_intent_signal.url ILIKE '%synthetic_%'
(использовать только эти 2, без “умных” эвристик)

Реализация (минимальная):
1) В deals_v1.py добавить параметр в функцию list.
2) В SQL запрос на выборку rows добавить дополнительный WHERE блок только при synthetic_only=true:

AND EXISTS (
  SELECT 1 FROM deal_intent_signal s
  WHERE s.app_id = d.app_id
    AND (
      s.text ILIKE '[SYNTHETIC]%%'
      OR s.url ILIKE '%%synthetic_%%'
    )
)

ВАЖНО:
- Не менять порядок сортировки.
- Не менять LIMIT.
- Не трогать min_intent_score/min_quality_score.

## Deliverable B — admin endpoint для генерации synthetic (опционально, но полезно)
Если это уже есть — не делать. Если нет — добавить ОДИН endpoint:
POST /api/v1/deals/synthetic/seed

Требования:
- Защита: simplest: hidden flag env var ENABLE_SYNTHETIC_SEED=true; если false → 404.
- Идемпотентность: повторный вызов не дублирует (использовать ON CONFLICT DO NOTHING для deal_intent_game; для signals — проверять url uniqueness вручную SELECT before INSERT).
- Создает:
  - deal_intent_game для app_id=999999, stage='demo', release_date=CURRENT_DATE, steam_name='SYNTHETIC TEST GAME'
  - 2 сигнала в deal_intent_signal для app_id=999999:
    - intent_keyword, source=reddit, url содержит synthetic_, published_at=now, text начинается с [SYNTHETIC]
    - behavioral_intent, source=reddit, url содержит synthetic_, published_at=now, text начинается с [SYNTHETIC]
- НЕ трогать скоринг таблиц. Не пересчитывать intent_score/quality_score — это UI проверка.

## Проверки (обязательные команды)
После изменений Cursor обязан выполнить и приложить вывод:

1) Синтаксис:
python -m py_compile apps/api/routers/deals_v1.py

2) Перезапуск:
docker compose restart api && sleep 2

3) Health:
curl -4 -sS "http://127.0.0.1:8000/api/v1/health" | jq .

4) Synthetic only:
curl -4 -sS "http://127.0.0.1:8000/api/v1/deals/list?limit=50&synthetic_only=true" | jq '.count, .games[0].app_id, .games[0].title'

Ожидание:
- count >= 1
- app_id=999999 или 1410400 (если синтетика заведена там)
- title не пустой

5) Default unchanged:
curl -4 -sS "http://127.0.0.1:8000/api/v1/deals/list?limit=50" | jq '.status,.count'

Ожидание:
- endpoint работает
- count НЕ становится 0 из-за изменений synthetic_only

## Ограничения на изменения файлов
Разрешено менять:
- apps/api/routers/deals_v1.py
- при необходимости: apps/api/main.py (только если нужен include_router для нового synthetic endpoint)

Запрещено менять:
- любые файлы в apps/worker/analysis (кроме если чинится баг, но это отдельное ТЗ)
- migrations
- docker compose
- dashboard

## Commit message
feat: add synthetic_only filter for deals list
(если добавляется endpoint seed — допиши: + admin seed endpoint)