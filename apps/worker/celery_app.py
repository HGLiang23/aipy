from celery import Celery

from aipy.shared.config import get_settings

settings = get_settings()

celery_app = Celery("aipy", broker=settings.celery.broker_url)
celery_app.conf.update(
    accept_content=["json"],
    enable_utc=True,
    result_backend=None,
    task_ignore_result=True,
    task_serializer="json",
    timezone="UTC",
)
