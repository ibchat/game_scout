from celery import Celery
from celery.schedules import crontab
import os

# Get Redis URL from environment
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Create Celery app
celery_app = Celery(
    "game_scout",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "apps.worker.tasks.collect_steam",
        "apps.worker.tasks.collect_itch",
        "apps.worker.tasks.compute_trends",
        "apps.worker.tasks.score_pitch",
        "apps.worker.tasks.export_sheets",
    ]
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=os.getenv("TZ", "Europe/Madrid"),
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
)

# Beat schedule - daily jobs at 07:00 Europe/Madrid
celery_app.conf.beat_schedule = {
    "collect-steam-daily": {
        "task": "apps.worker.tasks.collect_steam.collect_steam_task",
        "schedule": crontab(hour=7, minute=0),
    },
    "collect-itch-daily": {
        "task": "apps.worker.tasks.collect_itch.collect_itch_task",
        "schedule": crontab(hour=7, minute=10),
    },
    "compute-trends-daily": {
        "task": "apps.worker.tasks.compute_trends.compute_trends_task",
        "schedule": crontab(hour=7, minute=20),
    },
    "export-sheets-daily": {
        "task": "apps.worker.tasks.export_sheets.export_sheets_task",
        "schedule": crontab(hour=7, minute=30),
    },
}
## # from apps.worker.tasks import deep_analysis

# Import all tasks to register them
from apps.worker.tasks.collect_wishlist_ranks import collect_wishlist_ranks_task  # noqa
from apps.worker.tasks.collect_youtube import collect_youtube_task  # noqa
from apps.worker.tasks.collect_tiktok import collect_tiktok_task  # noqa
from apps.worker.tasks.analyze_video_comments import analyze_video_comments_task  # noqa
from apps.worker.tasks.score_game_investment import score_game_investment_task  # noqa
from apps.worker.tasks.daily_pipeline import daily_pipeline_task  # noqa
from apps.worker.tasks.morning_scan import morning_scan_task  # noqa
