from __future__ import annotations

import os
import threading
from celery import Celery
from celery.signals import worker_ready, worker_shutting_down

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL") or os.getenv("REDIS_URL") or "redis://redis:6379/0"
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND") or os.getenv("REDIS_URL") or "redis://redis:6379/1"

celery_app = Celery(
    "game_scout_worker",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    timezone=os.getenv("CELERY_TIMEZONE", "UTC"),
    enable_utc=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=int(os.getenv("CELERY_RESULT_EXPIRES", "3600")),
    task_track_started=True,
    worker_send_task_events=True,
    task_send_sent_event=True,
)

# Heartbeat для worker
_heartbeat_thread = None

@worker_ready.connect
def worker_ready_handler(sender=None, **kwargs):
    """Запускаем heartbeat при старте воркера."""
    global _heartbeat_thread
    from apps.worker.tasks.heartbeat import start_heartbeat_loop
    
    _heartbeat_thread = threading.Thread(
        target=start_heartbeat_loop,
        args=("worker",),
        daemon=True
    )
    _heartbeat_thread.start()
    import logging
    logger = logging.getLogger(__name__)
    logger.info("Heartbeat thread started for worker")

@worker_shutting_down.connect
def worker_shutting_down_handler(sender=None, **kwargs):
    """Останавливаем heartbeat при остановке воркера."""
    import logging
    logger = logging.getLogger(__name__)
    logger.info("Worker shutting down, heartbeat will stop")

# Relaunch tasks
from apps.worker.tasks.collect_relaunch_steam import collect_relaunch_steam_task  # noqa: F401,E402
from apps.worker.tasks.compute_relaunch_scores import compute_relaunch_scores_task  # noqa: F401,E402
