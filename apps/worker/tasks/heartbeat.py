"""
Heartbeat задача для воркеров - записывает timestamp в Redis каждые 10-15 секунд.
"""
import os
import logging
from datetime import datetime
import redis

logger = logging.getLogger(__name__)

# Redis connection
REDIS_URL = os.getenv("REDIS_URL") or os.getenv("CELERY_BROKER_URL") or "redis://redis:6379/0"

# Heartbeat keys
HEARTBEAT_KEY_WORKER = "gs:heartbeat:worker"
HEARTBEAT_KEY_WORKER_TRENDS = "gs:heartbeat:worker_trends"

# Heartbeat interval (секунды)
HEARTBEAT_INTERVAL = 12  # Каждые 12 секунд


def get_redis_client():
    """Получить клиент Redis."""
    try:
        return redis.from_url(REDIS_URL, decode_responses=True)
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        return None


def send_heartbeat(worker_name: str = "worker"):
    """
    Отправляет heartbeat в Redis.
    
    Args:
        worker_name: "worker" или "worker_trends"
    """
    redis_client = get_redis_client()
    if not redis_client:
        logger.warning("Redis unavailable, heartbeat skipped")
        return False
    
    try:
        key = HEARTBEAT_KEY_WORKER if worker_name == "worker" else HEARTBEAT_KEY_WORKER_TRENDS
        timestamp = datetime.utcnow().isoformat()
        
        # Устанавливаем ключ с TTL 60 секунд (если heartbeat не придет - ключ исчезнет)
        redis_client.setex(key, 60, timestamp)
        
        logger.debug(f"Heartbeat sent: {worker_name} at {timestamp}")
        return True
    except Exception as e:
        logger.error(f"Failed to send heartbeat: {e}")
        return False


def check_heartbeat(worker_name: str = "worker") -> dict:
    """
    Проверяет heartbeat воркера.
    
    Returns:
        {
            "status": "OK" | "DOWN" | "UNKNOWN",
            "last_heartbeat": ISO timestamp или None,
            "age_seconds": int или None
        }
    """
    redis_client = get_redis_client()
    if not redis_client:
        return {
            "status": "UNKNOWN",
            "last_heartbeat": None,
            "age_seconds": None,
            "reason": "Redis недоступен"
        }
    
    try:
        key = HEARTBEAT_KEY_WORKER if worker_name == "worker" else HEARTBEAT_KEY_WORKER_TRENDS
        timestamp_str = redis_client.get(key)
        
        if not timestamp_str:
            return {
                "status": "DOWN",
                "last_heartbeat": None,
                "age_seconds": None,
                "reason": "Heartbeat не найден"
            }
        
        # Парсим timestamp
        try:
            last_heartbeat = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            now = datetime.utcnow()
            age_seconds = int((now - last_heartbeat.replace(tzinfo=None)).total_seconds())
            
            # Если heartbeat старше 60 секунд - воркер DOWN
            if age_seconds > 60:
                return {
                    "status": "DOWN",
                    "last_heartbeat": timestamp_str,
                    "age_seconds": age_seconds,
                    "reason": f"Heartbeat устарел ({age_seconds} сек назад)"
                }
            
            return {
                "status": "OK",
                "last_heartbeat": timestamp_str,
                "age_seconds": age_seconds,
                "reason": None
            }
        except ValueError as e:
            logger.error(f"Failed to parse heartbeat timestamp: {e}")
            return {
                "status": "UNKNOWN",
                "last_heartbeat": timestamp_str,
                "age_seconds": None,
                "reason": f"Ошибка парсинга timestamp: {e}"
            }
            
    except Exception as e:
        logger.error(f"Failed to check heartbeat: {e}")
        return {
            "status": "UNKNOWN",
            "last_heartbeat": None,
            "age_seconds": None,
            "reason": f"Ошибка проверки: {e}"
        }


def start_heartbeat_loop(worker_name: str = "worker"):
    """
    Запускает бесконечный цикл heartbeat (для использования в отдельном потоке).
    
    Args:
        worker_name: "worker" или "worker_trends"
    """
    import time
    
    logger.info(f"Starting heartbeat loop for {worker_name}")
    
    while True:
        try:
            send_heartbeat(worker_name)
            time.sleep(HEARTBEAT_INTERVAL)
        except KeyboardInterrupt:
            logger.info(f"Heartbeat loop stopped for {worker_name}")
            break
        except Exception as e:
            logger.error(f"Heartbeat loop error: {e}")
            time.sleep(HEARTBEAT_INTERVAL)
