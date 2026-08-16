from celery import Celery
from celery.schedules import crontab

from app.core.config import settings
from app.core.logging import configure_logging

configure_logging()

celery = Celery(
    "trend_radar",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.pipeline"],
)

celery.conf.update(
    broker_connection_retry_on_startup=True,
    task_track_started=True,
    task_time_limit=15 * 60,
    task_soft_time_limit=13 * 60,
    worker_max_tasks_per_child=20,  # Chromium тече — перезапускаємо воркер регулярно
    timezone="UTC",
    enable_utc=True,
)

# Автоматичний збір кожні 6 годин (ТЗ, п.1)
celery.conf.beat_schedule = {
    "scheduled-scrape-every-6-hours": {
        "task": "app.tasks.pipeline.run_pipeline",
        "schedule": crontab(minute=0, hour=f"*/{settings.scrape_interval_hours}"),
        "kwargs": {"trigger": "schedule"},
    },
}
