"""Celery application instance."""

from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery("reportapi", broker=settings.redis_url, backend=settings.redis_url)
celery_app.autodiscover_tasks(["app.worker"])

celery_app.conf.beat_schedule = {
    "run-due-schedules-every-minute": {
        "task": "app.worker.tasks.run_due_schedules",
        "schedule": crontab(minute="*"),
    },
}
celery_app.conf.timezone = "UTC"
