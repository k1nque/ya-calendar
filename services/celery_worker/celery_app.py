from celery import Celery
from app.config import settings
from app.logging_config import setup_root_logging
import logging

# Настраиваем логирование для celery worker
logger = setup_root_logging('celery_worker', log_level=logging.INFO)

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

logger.info("Celery worker initialized")
