import logging
import time
from datetime import datetime, timedelta, timezone
import hashlib
import redis
from icalendar import Calendar
import caldav

from app.config import settings
from app.db import SessionLocal, engine
from app import models, crud
from celery import Celery

# create local celery instance for the worker to submit tasks
celery = Celery('worker_sender', broker=settings.REDIS_URL, backend=settings.REDIS_URL)
celery.conf.accept_content = ['json']
celery.conf.result_serializer = 'json'
celery.conf.task_serializer = 'json'

# create tables
models.Base.metadata.create_all(bind=engine)

r = redis.Redis.from_url(settings.REDIS_URL)

WEBSITE = settings.CALDAV_WEBSITE
EMAIL = settings.CALDAV_EMAIL
PASSWORD = settings.CALDAV_PASSWORD


def get_principal(username, leg_token):
    try:
        client = caldav.DAVClient(url=WEBSITE, username=username, password=leg_token)
        principal = client.principal()
        return principal
    except Exception as e:
        print(f"Error getting principal: {e}")
        raise


def schedule_lesson(db, event_uid, summary, start_dt, end_dt, description):
    student = crud.get_or_create_student(db, summary)
    lesson, changed = crud.upsert_lesson(db, event_uid=event_uid, summary=summary, start=start_dt, end=end_dt, description=description, student=student)

    notify_time = start_dt - timedelta(minutes=30)
    now = datetime.now(timezone.utc)
    if notify_time <= now:
        return

    key = f"scheduled:{event_uid}"
    existing = r.hgetall(key)
    start_ts = int(start_dt.timestamp())
    if existing:
        old_start = int(existing.get(b'start_ts', b'0'))
        if old_start == start_ts:
            return
        # revoke old
        old_task_id = existing.get(b'task_id')
        if old_task_id:
            try:
                celery.control.revoke(old_task_id.decode(), terminate=True)
            except Exception:
                pass

    # schedule new
    eta = notify_time
    # send_task by name registered in celery worker
    res = celery.send_task('tasks.send_notify', args=[lesson.id], eta=eta)
    r.hset(key, mapping={"task_id": res.id, "start_ts": start_ts})


def parse_and_schedule():
    try:
        principal = get_principal(EMAIL, PASSWORD)
        cal = principal.calendar(name="Мои события")
        start_date = datetime.now(timezone.utc)
        end_date = start_date + timedelta(days=7)
        events = cal.search(start=start_date, end=end_date)
        db = SessionLocal()
        for evt in events:
            calobj = Calendar.from_ical(evt.data)
            for component in calobj.walk():
                if component.name == "VEVENT":
                    summary = str(component.get('summary'))
                    uid = str(component.get('uid') or hashlib.sha1((summary+str(component.get('dtstart'))).encode()).hexdigest())
                    start = component.get('dtstart').dt
                    end = component.get('dtend').dt
                    description = str(component.get('description') or '')
                    schedule_lesson(db, uid, summary, start, end, description)
        db.close()
    except Exception as e:
        print(f"Worker error in parse_and_schedule: {e}")


if __name__ == '__main__':
    # Suppress noisy CalDAV CRITICAL logs about 'Expected some valid XML...'
    class CaldavNoiseFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            msg = str(record.getMessage())
            return 'Expected some valid XML from the server' not in msg

    logging.getLogger().addFilter(CaldavNoiseFilter())
    while True:
        try:
            parse_and_schedule()
        except Exception as e:
            logging.error('Worker error: %s', e)
        time.sleep(settings.WORKER_POLL_SECONDS)
