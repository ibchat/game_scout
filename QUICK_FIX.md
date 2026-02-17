# Быстрое решение проблемы с Docker

## Проблема
Docker не установлен на вашем Mac, поэтому API не может запуститься.

## Решение

### Шаг 1: Установить Docker Desktop

**Вариант A: Через сайт (рекомендуется)**
1. Откройте https://www.docker.com/products/docker-desktop/
2. Скачайте Docker Desktop для Mac
3. Установите приложение
4. Запустите Docker Desktop из Applications

**Вариант B: Через Homebrew**
```bash
brew install --cask docker
open /Applications/Docker.app
```

### Шаг 2: Проверить установку

```bash
# Проверить что Docker работает
docker --version
docker ps

# Если команды работают, переходите к шагу 3
```

### Шаг 3: Запустить Game Scout

```bash
# Перейти в директорию проекта
cd /Users/mariya/Desktop/game_scout

# Запустить все сервисы
docker compose up -d

# Проверить статус
docker compose ps

# Открыть дашборд
open http://localhost:8000/dashboard
```

### Шаг 4: Запустить тесты

```bash
# Комплексный тест дашборда
bash scripts/test_dashboard_comprehensive.sh

# Или быстрая проверка
bash scripts/verify_dashboard.sh
```

## Проверка окружения

После установки Docker запустите:

```bash
bash scripts/check_environment.sh
```

Скрипт покажет что готово, а что нужно исправить.

## Дополнительная информация

- Полная инструкция: `DOCKER_SETUP.md`
- Инструкция по запуску: `DASHBOARD_START_INSTRUCTIONS.md`
- Отчет о тестировании: `DASHBOARD_TEST_REPORT.md`

## Если Docker установить нельзя

Можно запустить API локально, но это сложнее:
- Нужно установить PostgreSQL отдельно
- Нужно установить Redis отдельно
- Нужно настроить все зависимости

Рекомендуется использовать Docker - это самый простой способ.
