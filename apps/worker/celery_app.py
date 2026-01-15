from __future__ import annotations

import os
from celery import Celery

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

# Relaunch tasks
from apps.worker.tasks.collect_relaunch_steam import collect_relaunch_steam_task  # noqa: F401,E402
from apps.worker.tasks.compute_relaunch_scores import compute_relaunch_scores_task  # noqa: F401,E402
