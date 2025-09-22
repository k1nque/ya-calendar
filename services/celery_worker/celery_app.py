from celery import Celery
from app.config import settings

# celery instance exported as `celery` for celery -A tasks
celery = Celery(
    'ya_calendar',
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)
celery.conf.task_serializer = 'json'
celery.conf.accept_content = ['json']
celery.conf.result_serializer = 'json'
celery.conf.timezone = 'UTC'
