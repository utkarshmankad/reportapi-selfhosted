"""Celery application instance."""
from celery import Celery
from app.config import settings

celery_app = Celery("reportapi", broker=settings.redis_url, backend=settings.redis_url)
