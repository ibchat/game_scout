# Discord Bot Token Setup Guide

## Что такое Discord Bot Token?

Discord Bot Token — это секретный ключ, который позволяет вашему боту подключаться к Discord API и выполнять действия от имени бота (читать сообщения, отправлять сообщения, получать информацию о серверах и каналах).

**Важно:** Токен — это секретная информация. Никогда не публикуйте его в открытом доступе (GitHub, публичные репозитории, скриншоты).

---

## Где получить Discord Bot Token?

### Шаг 1: Создайте Discord Application

1. Перейдите на [Discord Developer Portal](https://discord.com/developers/applications)
2. Войдите в свой аккаунт Discord
3. Нажмите **"New Application"**
4. Введите название приложения (например, "Game Scout Bot")
5. Нажмите **"Create"**

### Шаг 2: Создайте Bot

1. В меню слева выберите **"Bot"**
2. Нажмите **"Add Bot"** → **"Yes, do it!"**
3. (Опционально) Загрузите аватар и измените имя бота

### Шаг 3: Получите Token

1. В разделе **"Bot"** найдите секцию **"Token"**
2. Нажмите **"Reset Token"** или **"Copy"** (если токен уже создан)
3. **Скопируйте токен** — он будет показан только один раз!

### Шаг 4: Настройте Bot Permissions

1. В разделе **"Bot"** прокрутите вниз до **"Privileged Gateway Intents"**
2. Включите **"MESSAGE CONTENT INTENT"** (обязательно для чтения содержимого сообщений)
3. В разделе **"OAuth2" → "URL Generator"** выберите:
   - **Scopes:** `bot`
   - **Bot Permissions:** 
     - `Read Messages/View Channels`
     - `Read Message History`
     - `Send Messages` (опционально)

### Шаг 5: Добавьте бота на сервер

1. Используйте сгенерированный OAuth2 URL
2. Выберите сервер, на который хотите добавить бота
3. Подтвердите разрешения

---

## Примеры: Placeholder vs Реальный токен

### ❌ Placeholder (невалидный)

```
DISCORD_BOT_TOKEN=PASTE_REAL_DISCORD_BOT_TOKEN_HERE
DISCORD_BOT_TOKEN=PUT_REAL_TOKEN_HERE
DISCORD_BOT_TOKEN=paste_your_real_discord_bot_token_here
```

**Характеристики:**
- Содержит слова `paste_real`, `put_real`, `your_real`, `token_here`
- Длина обычно < 50 символов
- Это шаблон, а не реальный токен

### ✅ Реальный токен (валидный)

```
DISCORD_BOT_TOKEN=MTIzNDU2Nzg5MGFiY2RlZjEyMzQ1Njc4OTBhYmNkZWYxMjM0NTY3ODkwYWJjZGVm
```

**Характеристики:**
- Длина >= 50 символов
- Состоит из букв, цифр, символов (обычно Base64-подобная строка)
- НЕ содержит слова `paste_real`, `put_real`, `your_real`, `token_here`
- Выглядит как случайная строка

**Пример формата реального токена:**
- Начинается с цифр (ID бота)
- Содержит точку `.`
- После точки — длинная случайная строка
- Общая длина: 59-70+ символов

---

## Настройка в Game Scout

### 1. Откройте файл `.env`

```bash
nano .env
# или
vim .env
```

### 2. Найдите строку `DISCORD_BOT_TOKEN`

Если её нет, добавьте:

```bash
DISCORD_BOT_TOKEN=ваш_реальный_токен_здесь
```

### 3. Замените placeholder на реальный токен

**Было:**
```
DISCORD_BOT_TOKEN=PASTE_REAL_DISCORD_BOT_TOKEN_HERE
```

**Стало:**
```
DISCORD_BOT_TOKEN=MTIzNDU2Nzg5MGFiY2RlZjEyMzQ1Njc4OTBhYmNkZWYxMjM0NTY3ODkwYWJjZGVm
```

### 4. Пересоздайте контейнеры

```bash
bash scripts/recreate_env_services.sh
```

Или вручную:

```bash
docker compose up -d --force-recreate --no-deps api worker
```

### 5. Проверьте настройку

```bash
bash scripts/verify_discord_token_flow.sh
```

---

## Чеклист: Почему `/api/v1/deals/signals/collect_discord` возвращает `skipped`?

Если endpoint возвращает:

```json
{
  "status": "ok",
  "result": {
    "status": "skipped",
    "errors": ["DISCORD_BOT_TOKEN not configured. See docs/DISCORD_BOT_TOKEN_SETUP.md"]
  }
}
```

Проверьте:

- [ ] **Токен установлен в `.env`?**
  - Откройте `.env` и проверьте наличие строки `DISCORD_BOT_TOKEN=...`
  
- [ ] **Токен не является placeholder?**
  - Убедитесь, что значение НЕ содержит `PASTE_REAL_DISCORD_BOT_TOKEN_HERE`, `PUT_REAL_TOKEN_HERE` и т.п.
  - Проверьте: `grep DISCORD_BOT_TOKEN .env`
  
- [ ] **Токен достаточной длины?**
  - Реальный токен обычно >= 50 символов
  - Проверьте: `docker compose exec -T worker sh -c 'echo ${#DISCORD_BOT_TOKEN}'`
  
- [ ] **Контейнеры пересозданы после изменения `.env`?**
  - Запустите: `bash scripts/recreate_env_services.sh`
  - Или: `docker compose up -d --force-recreate --no-deps api worker`
  
- [ ] **Токен валидный в контейнере?**
  - Проверьте: `docker compose exec -T worker python - <<'PY'
import os
from apps.worker.tasks.collect_discord_signals import is_discord_token_configured
t=(os.getenv("DISCORD_BOT_TOKEN") or "").strip()
print("configured:", is_discord_token_configured(t))
PY`
  
- [ ] **Токен не содержит запрещённые слова?**
  - Убедитесь, что токен НЕ содержит (case-insensitive): `put_real`, `paste_real`, `your_real`, `token_here`

---

## Безопасность

### ⚠️ Важные правила:

1. **Никогда не коммитьте `.env` в Git**
   - Файл `.env` должен быть в `.gitignore`
   - Используйте `.env.example` для шаблонов

2. **Не публикуйте токен**
   - Не отправляйте токен в чаты, email, публичные репозитории
   - Если токен скомпрометирован — немедленно сбросьте его в Discord Developer Portal

3. **Регулярно проверяйте доступ**
   - Периодически проверяйте, какие серверы и каналы доступны боту
   - Удаляйте неиспользуемые разрешения

4. **Используйте разные токены для разных окружений**
   - Development, Staging, Production должны иметь разные токены

---

## Troubleshooting

### Проблема: "Invalid token" от Discord API

**Решение:**
- Проверьте, что токен скопирован полностью (без пробелов в начале/конце)
- Убедитесь, что токен не истёк (сбросьте токен в Discord Developer Portal)
- Проверьте, что бот добавлен на сервер с нужными разрешениями

### Проблема: "Missing Access" при чтении каналов

**Решение:**
- Убедитесь, что бот добавлен на сервер
- Проверьте, что у бота есть разрешение `Read Messages/View Channels`
- Убедитесь, что включён `MESSAGE CONTENT INTENT` в настройках бота

### Проблема: Токен валидный, но endpoint всё равно `skipped`

**Решение:**
- Пересоздайте контейнеры: `bash scripts/recreate_env_services.sh`
- Проверьте логи: `docker compose logs worker | grep -i discord`
- Запустите verify скрипт: `bash scripts/verify_discord_token_flow.sh`

---

## Дополнительные ресурсы

- [Discord Developer Portal](https://discord.com/developers/applications)
- [Discord API Documentation](https://discord.com/developers/docs/intro)
- [Discord.py Documentation](https://discordpy.readthedocs.io/)
