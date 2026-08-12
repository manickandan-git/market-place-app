from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "inventory_service",
    broker=settings.celery_broker_url,
    include=["app.tasks"],
)

celery_app.conf.beat_schedule = {
    "expire-reservations": {
        "task": "app.tasks.expire_reservations",
        "schedule": settings.expire_sweeper_interval_seconds,
    },
}
