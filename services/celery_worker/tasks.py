import requests
from celery_app import celery


@celery.task(bind=True, name='tasks.send_notify')
def send_notify(self, lesson_id: int):
    """Call bot service HTTP endpoint to notify users about lesson_id"""
    url = "http://bot:8080/notify"
    try:
        resp = requests.post(url, json={"lesson_id": lesson_id}, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        raise self.retry(exc=e, countdown=60)
    return True
