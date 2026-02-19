# Настройка OpenAI для перевода

## Быстрая настройка

### 1. Получите API ключ OpenAI
- Зарегистрируйтесь на https://platform.openai.com/
- Создайте API ключ в разделе API Keys
- Скопируйте ключ (начинается с `sk-...`)

### 2. Добавьте в `.env` файл

```env
# Используем OpenAI вместо Anthropic
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...ваш_ключ...

# Опционально: выберите модель (по умолчанию gpt-4o-mini)
LLM_MODEL=gpt-4o-mini
# Или для лучшего качества:
# LLM_MODEL=gpt-4o
```

### 3. Перезапустите контейнеры

```bash
docker compose restart api
```

### 4. Проверьте работу

```bash
docker compose exec -T api python3 << 'EOF'
from apps.worker.llm.client import get_llm_client
client = get_llm_client()
print(f"✅ LLM Client: {client.provider}, model: {client.model}" if client else "❌ Not configured")
EOF
```

### 5. Запустите pipeline

```bash
bash scripts/run_intel_pipeline.sh
```

## Модели OpenAI

Рекомендуемые модели для перевода:
- **gpt-4o-mini** (по умолчанию) - быстрая и дешёвая, хорошее качество
- **gpt-4o** - лучшее качество, но дороже
- **gpt-3.5-turbo** - самый дешёвый вариант

## Сравнение с Anthropic

| Параметр | OpenAI | Anthropic |
|----------|--------|-----------|
| Скорость | Быстрее | Медленнее |
| Качество перевода | Отлично | Отлично |
| Стоимость | Дешевле | Дороже |
| Доступность | Проще получить ключ | Требует одобрения |

## Troubleshooting

**"OPENAI_API_KEY not set"**
- Проверьте, что ключ добавлен в `.env`
- Убедитесь, что `.env` файл не в `.gitignore` (но сам файл должен быть)
- Перезапустите контейнеры

**"openai package not installed"**
- Установите: `pip install openai` (в контейнере уже должно быть)

**Перевод не работает**
- Проверьте баланс на аккаунте OpenAI
- Убедитесь, что модель доступна (gpt-4o-mini всегда доступна)
