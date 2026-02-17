# Установка Docker для Game Scout

## Для macOS

### Вариант 1: Docker Desktop (рекомендуется)

1. **Скачать Docker Desktop:**
   - Перейдите на https://www.docker.com/products/docker-desktop/
   - Скачайте версию для Mac (Apple Silicon или Intel)
   - Установите приложение

2. **Запустить Docker Desktop:**
   - Откройте приложение Docker Desktop из Applications
   - Дождитесь полной загрузки (иконка в меню должна быть зеленой)

3. **Проверить установку:**
   ```bash
   docker --version
   docker compose version
   ```

4. **Запустить Game Scout:**
   ```bash
   cd /Users/mariya/Desktop/game_scout
   docker compose up -d
   ```

### Вариант 2: Homebrew

```bash
# Установить Docker через Homebrew
brew install --cask docker

# Запустить Docker Desktop
open /Applications/Docker.app

# Подождать пока Docker запустится, затем проверить
docker --version
```

## Проверка установки

После установки выполните:

```bash
# Проверить версию Docker
docker --version

# Проверить версию Docker Compose
docker compose version

# Проверить что Docker работает
docker ps
```

Если команды работают, можно запускать Game Scout!

## Быстрый старт после установки

```bash
# 1. Перейти в директорию проекта
cd /Users/mariya/Desktop/game_scout

# 2. Запустить все сервисы
docker compose up -d

# 3. Проверить статус
docker compose ps

# 4. Проверить логи API
docker compose logs -f api

# 5. Открыть дашборд
open http://localhost:8000/dashboard
```

## Решение проблем

### Docker не найден в PATH

Если после установки команда `docker` не работает:

1. Перезапустите терминал
2. Или добавьте в `~/.zshrc`:
   ```bash
   export PATH="/usr/local/bin:$PATH"
   ```

### Docker Desktop не запускается

1. Проверьте системные требования:
   - macOS 10.15 или новее
   - Минимум 4 GB RAM
   - Виртуализация включена

2. Перезапустите компьютер

3. Проверьте настройки безопасности в System Preferences

### Порт 8000 занят

Если порт 8000 уже используется:

```bash
# Найти процесс на порту 8000
lsof -i :8000

# Остановить процесс или изменить порт в docker-compose.yml
```

## Альтернатива: запуск без Docker

Если Docker установить нельзя, можно запустить API локально, но потребуется:
- PostgreSQL (установить отдельно)
- Redis (установить отдельно)
- Python 3.12
- Все зависимости из pyproject.toml

Это более сложный вариант, рекомендуется использовать Docker.
