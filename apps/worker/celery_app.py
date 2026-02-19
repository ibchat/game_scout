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

# Intel schedule mode: daily or hourly
INTEL_SCHEDULE_MODE = os.getenv("INTEL_SCHEDULE_MODE", "daily")  # daily or hourly
INTEL_DAILY_RUN_HOUR = int(os.getenv("INTEL_DAILY_RUN_HOUR", "9"))
INTEL_DAILY_RUN_TZ = os.getenv("INTEL_DAILY_RUN_TZ", "Europe/Madrid")

# Set timezone for Intel daily runs
if INTEL_SCHEDULE_MODE == "daily":
    celery_timezone = INTEL_DAILY_RUN_TZ
else:
    celery_timezone = os.getenv("CELERY_TIMEZONE", "UTC")

celery_app.conf.update(
    timezone=celery_timezone,
    enable_utc=False if INTEL_SCHEDULE_MODE == "daily" else True,  # Use local timezone for daily
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

# Deal Intent tasks
from apps.worker.tasks.collect_deal_intent_signals_reddit import collect_deal_intent_signals_reddit_task  # noqa: F401,E402
from apps.worker.tasks.collect_discord_signals import collect_discord_signals_task  # noqa: F401,E402

# Discord Discovery tasks
from apps.worker.tasks.discover_discord_invites import discover_discord_invites_task  # noqa: F401,E402
from apps.worker.tasks.resolve_discord_invite import resolve_discord_invite_task  # noqa: F401,E402
from apps.worker.tasks.rank_discord_candidates import rank_discord_candidates_task  # noqa: F401,E402
from apps.worker.tasks.sync_guild_channels import sync_guild_channels_task  # noqa: F401,E402

# Intel tasks
from apps.worker.tasks.publish_steam_intel import publish_steam_intel_task  # noqa: F401,E402

# Beat schedule - periodic tasks
from celery.schedules import crontab

# Intel schedule: daily at 09:05 Europe/Madrid or hourly (every 2 hours)
INTEL_DAILY_RUN_MINUTE = int(os.getenv("INTEL_DAILY_RUN_MINUTE", "5"))  # Default 09:05

if INTEL_SCHEDULE_MODE == "daily":
    celery_app.conf.beat_schedule = {
        "publish-steam-intel-daily": {
            "task": "publish_steam_intel",
            "schedule": crontab(hour=INTEL_DAILY_RUN_HOUR, minute=INTEL_DAILY_RUN_MINUTE),  # Daily at 09:05 Europe/Madrid
        },
    }
else:
    # Hourly mode (legacy): disabled by default, can be enabled via INTEL_RUN_MODE=hourly
    # Only enable if explicitly requested
    if os.getenv("INTEL_RUN_MODE") == "hourly":
        celery_app.conf.beat_schedule = {
            "publish-steam-intel": {
                "task": "publish_steam_intel",
                "schedule": crontab(minute="*/120"),  # Every 2 hours
            },
        }
