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


def schedule_lesson(db, event_uid, summary, start_dt, end_dt):
    student = crud.get_or_create_student(db, summary)
    lesson, changed = crud.upsert_lesson(db, event_uid=event_uid, summary=summary, start=start_dt, end=end_dt, student=student)

    notify_time = start_dt - timedelta(minutes=30)
    deduct_time = end_dt  # Списание после окончания урока
    now = datetime.now(timezone.utc)
    
    # Schedule notification (existing logic)
    if notify_time > now:
        key = f"scheduled:{event_uid}"
        existing = r.hgetall(key)
        start_ts = int(start_dt.timestamp())
        if existing:
            old_start = int(existing.get(b'start_ts', b'0'))
            if old_start == start_ts:
                # Already scheduled for this start time, skip notification scheduling
                pass
            else:
                # revoke old
                old_task_id = existing.get(b'task_id')
                if old_task_id:
                    try:
                        celery.control.revoke(old_task_id.decode(), terminate=True)
                    except Exception:
                        pass
                # schedule new notification
                eta = notify_time
                res = celery.send_task('tasks.send_notify', args=[lesson.id], eta=eta)
                r.hset(key, mapping={"task_id": res.id, "start_ts": start_ts})
        else:
            # schedule new notification
            eta = notify_time
            res = celery.send_task('tasks.send_notify', args=[lesson.id], eta=eta)
            r.hset(key, mapping={"task_id": res.id, "start_ts": start_ts})

    # Schedule lesson deduction after completion (new logic)
    if deduct_time > now:
        deduct_key = f"deduct:{event_uid}"
        existing_deduct = r.hgetall(deduct_key)
        end_ts = int(end_dt.timestamp())
        
        if existing_deduct:
            old_end = int(existing_deduct.get(b'end_ts', b'0'))
            if old_end == end_ts:
                # Already scheduled for this end time, skip
                return
            else:
                # revoke old deduct task
                old_deduct_task_id = existing_deduct.get(b'deduct_task_id')
                if old_deduct_task_id:
                    try:
                        celery.control.revoke(old_deduct_task_id.decode(), terminate=True)
                    except Exception:
                        pass
        
        # schedule new deduct task
        eta_deduct = deduct_time
        res_deduct = celery.send_task('tasks.deduct_lesson_after_completion', args=[lesson.id], eta=eta_deduct)
        r.hset(deduct_key, mapping={"deduct_task_id": res_deduct.id, "end_ts": end_ts})


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
                    schedule_lesson(db, uid, summary, start, end)
        db.close()
    except Exception as e:
        logging.error(f"Worker error in parse_and_schedule: {e}")


if __name__ == '__main__':
    # Suppress noisy CalDAV CRITICAL logs about 'Expected some valid XML...'
    class CaldavNoiseFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            msg = str(record.getMessage())
            return 'Expected some valid XML from the server' not in msg

    logging.getLogger().addFilter(CaldavNoiseFilter())
    while True:
        try:
            logging.info('Worker running parse_and_schedule at %s', datetime.now())
            parse_and_schedule()
        except Exception as e:
            logging.error('Worker error: %s', e)
        time.sleep(settings.WORKER_POLL_SECONDS)
