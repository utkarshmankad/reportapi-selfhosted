"""Celery application instance."""

from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery("reportapi", broker=settings.redis_url, backend=settings.redis_url)
celery_app.autodiscover_tasks(["app.worker"])

celery_app.conf.beat_schedule = {
    "dispatch-due-schedules-every-minute": {
        "task": "app.worker.tasks.dispatch_due_schedules",
        "schedule": crontab(minute="*"),
    },
    "recover-stuck-report-jobs-every-5-minutes": {
        "task": "app.worker.tasks.recover_stuck_report_jobs",
        "schedule": crontab(minute="*/5"),
    },
    "dispatch-pending-webhook-deliveries-every-minute": {
        "task": "app.worker.tasks.dispatch_pending_webhook_deliveries",
        "schedule": crontab(minute="*"),
    },
}
celery_app.conf.timezone = "UTC"
