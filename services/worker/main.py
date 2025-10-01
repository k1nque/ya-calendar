import logging
import time
from datetime import date, datetime, timedelta, timezone
import hashlib
import redis
from icalendar import Calendar
import caldav
from dateutil.rrule import (
    WEEKLY,
    MO,
    TU,
    WE,
    TH,
    FR,
    SA,
    SU,
    rrule,
    weekday as rrule_weekday,
)

from app.config import settings
from app.db import SessionLocal, engine
from app import models, crud
from app.logging_config import setup_root_logging
from celery import Celery

# Настраиваем логирование для worker
logger = setup_root_logging('worker', log_level=logging.INFO)

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
        logger.debug(f"Connecting to CalDAV server for user: {username}")
        client = caldav.DAVClient(url=WEBSITE, username=username, password=leg_token)
        principal = client.principal()
        logger.info(f"Successfully connected to CalDAV for user: {username}")
        return principal
    except Exception as e:
        logger.error(f"Error getting principal for {username}: {e}", exc_info=True)
        raise


def schedule_lesson(db, event_uid, summary, start_dt, end_dt):
    logger.debug(f"Scheduling lesson: {summary} (UID: {event_uid}), Start: {start_dt}, End: {end_dt}")
    student = crud.get_or_create_student(db, summary)
    lesson, changed = crud.upsert_lesson(db, event_uid=event_uid, summary=summary, start=start_dt, end=end_dt, student=student)

    if changed:
        logger.info(f"Lesson updated: {summary} for student {student.summary} (ID: {lesson.id})")
    
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
                logger.debug(f"Notification already scheduled for lesson {event_uid}")
                pass
            else:
                # revoke old
                old_task_id = existing.get(b'task_id')
                if old_task_id:
                    try:
                        celery.control.revoke(old_task_id.decode(), terminate=True)
                        logger.info(f"Revoked old notification task {old_task_id.decode()} for lesson {event_uid}")
                    except Exception as e:
                        logger.warning(f"Failed to revoke old task {old_task_id}: {e}")
                # schedule new notification
                eta = notify_time
                res = celery.send_task('tasks.send_notify', args=[lesson.id], eta=eta)
                r.hset(key, mapping={"task_id": res.id, "start_ts": start_ts})
                logger.info(f"Scheduled notification for lesson {event_uid} at {notify_time} (task_id: {res.id})")
        else:
            # schedule new notification
            eta = notify_time
            res = celery.send_task('tasks.send_notify', args=[lesson.id], eta=eta)
            r.hset(key, mapping={"task_id": res.id, "start_ts": start_ts})
            logger.info(f"Scheduled notification for lesson {event_uid} at {notify_time} (task_id: {res.id})")

    # Schedule lesson deduction after completion (new logic)
    if deduct_time > now:
        deduct_key = f"deduct:{event_uid}"
        existing_deduct = r.hgetall(deduct_key)
        end_ts = int(end_dt.timestamp())
        
        if existing_deduct:
            old_end = int(existing_deduct.get(b'end_ts', b'0'))
            if old_end == end_ts:
                # Already scheduled for this end time, skip
                logger.debug(f"Deduction already scheduled for lesson {event_uid}")
                return
            else:
                # revoke old deduct task
                old_deduct_task_id = existing_deduct.get(b'deduct_task_id')
                if old_deduct_task_id:
                    try:
                        celery.control.revoke(old_deduct_task_id.decode(), terminate=True)
                        logger.info(f"Revoked old deduction task {old_deduct_task_id.decode()} for lesson {event_uid}")
                    except Exception as e:
                        logger.warning(f"Failed to revoke old deduct task {old_deduct_task_id}: {e}")
        
        # schedule new deduct task
        eta_deduct = deduct_time
        res_deduct = celery.send_task('tasks.deduct_lesson_after_completion', args=[lesson.id], eta=eta_deduct)
        r.hset(deduct_key, mapping={"deduct_task_id": res_deduct.id, "end_ts": end_ts})
        logger.info(f"Scheduled deduction for lesson {event_uid} at {deduct_time} (task_id: {res_deduct.id})")


ICAL_WEEKDAY_MAP = {
    "MO": MO,
    "TU": TU,
    "WE": WE,
    "TH": TH,
    "FR": FR,
    "SA": SA,
    "SU": SU,
}


def _ensure_datetime(value, fallback_tz):
    """Normalize ical values to timezone-aware datetime."""
    if isinstance(value, datetime):
        if value.tzinfo:
            return value
        if fallback_tz:
            return value.replace(tzinfo=fallback_tz)
        return value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        dt = datetime.combine(value, datetime.min.time())
        if fallback_tz:
            return dt.replace(tzinfo=fallback_tz)
        return dt.replace(tzinfo=timezone.utc)
    raise TypeError(f"Unsupported date value: {value!r}")


def _build_occurrence_uid(base_uid: str, occurrence_start: datetime) -> str:
    """Build stable UID for a particular occurrence (one per day)."""
    occurrence_date = occurrence_start.astimezone(timezone.utc).strftime("%Y%m%d")
    return f"{base_uid}#{occurrence_date}"


def expand_component_occurrences(component, summary: str, window_start: datetime, window_end: datetime):
    """Expand VEVENT into concrete occurrences within the window."""
    raw_start = component.get('dtstart')
    if raw_start is None:
        logger.warning("Skipping event without DTSTART: %s", summary)
        return []

    base_start = _ensure_datetime(raw_start.dt, None)
    raw_end = component.get('dtend')

    if raw_end is None:
        duration = timedelta(hours=1)
        base_end = base_start + duration
        logger.debug("Event %s missing DTEND; using fallback duration 1h", summary)
    else:
        base_end = _ensure_datetime(raw_end.dt, base_start.tzinfo)
        duration = base_end - base_start

    raw_uid = component.get('uid')
    base_uid = str(raw_uid) if raw_uid else hashlib.sha1((summary + str(base_start)).encode()).hexdigest()

    rrule_field = component.get('rrule')
    if not rrule_field:
        if base_end < window_start or base_start > window_end:
            return []
        return [(_build_occurrence_uid(base_uid, base_start), base_start, base_end)]

    freq_values = rrule_field.get('FREQ')
    freq_value = freq_values[0].upper() if freq_values else None
    if freq_value != 'WEEKLY':
        logger.debug("Unsupported RRULE frequency %s for event %s; using single occurrence", freq_value, summary)
        if base_end < window_start or base_start > window_end:
            return []
        return [(_build_occurrence_uid(base_uid, base_start), base_start, base_end)]

    interval = int(rrule_field.get('INTERVAL', [1])[0])
    byday_values = rrule_field.get('BYDAY') or []
    byweekday = tuple(ICAL_WEEKDAY_MAP[day] for day in byday_values if day in ICAL_WEEKDAY_MAP)
    if not byweekday:
        byweekday = (rrule_weekday(base_start.weekday()),)

    if base_start.tzinfo:
        window_start_local = window_start.astimezone(base_start.tzinfo)
        window_end_local = window_end.astimezone(base_start.tzinfo)
    else:
        window_start_local = window_start.replace(tzinfo=None)
        window_end_local = window_end.replace(tzinfo=None)

    until_values = rrule_field.get('UNTIL')
    until_candidate = None
    if until_values:
        raw_until = until_values[0]
        if hasattr(raw_until, 'dt'):
            raw_until = raw_until.dt
        until_candidate = _ensure_datetime(raw_until, base_start.tzinfo)

    count_values = rrule_field.get('COUNT')
    rule_kwargs = {
        'freq': WEEKLY,
        'dtstart': base_start,
        'interval': interval,
        'byweekday': byweekday,
    }
    if count_values:
        rule_kwargs['count'] = int(count_values[0])
    else:
        until_limit = window_end_local
        if until_candidate:
            until_limit = min(until_candidate, window_end_local)
        rule_kwargs['until'] = until_limit

    recurrence = rrule(**rule_kwargs)
    occurrence_starts = recurrence.between(window_start_local, window_end_local, inc=True)

    # Ensure dtstart included if it falls inside window but between() misses it due to timezone math
    if window_start_local <= base_start <= window_end_local and base_start not in occurrence_starts:
        occurrence_starts.insert(0, base_start)

    occurrences = []
    for occ_start in occurrence_starts:
        occ_end = occ_start + duration
        occurrence_uid = _build_occurrence_uid(base_uid, occ_start)
        occurrences.append((occurrence_uid, occ_start, occ_end))

    return occurrences


def parse_and_schedule():
    try:
        logger.info("Starting calendar parsing and scheduling...")
        principal = get_principal(EMAIL, PASSWORD)
        cal = principal.calendar(name="Мои события")
        start_date = datetime.now(timezone.utc)
        end_date = start_date + timedelta(days=7)
        logger.info(f"Fetching events from {start_date} to {end_date}")
        events = cal.search(start=start_date, end=end_date)
        logger.info(f"Found {len(events)} events")
        
        db = SessionLocal()
        events_processed = 0
        for evt in events:
            calobj = Calendar.from_ical(evt.data)
            for component in calobj.walk():
                if component.name == "VEVENT":
                    summary = str(component.get('summary'))
                    occurrences = expand_component_occurrences(component, summary, start_date, end_date)
                    if not occurrences:
                        logger.debug("No occurrences within window for event %s", summary)
                        continue
                    for occurrence_uid, start, end in occurrences:
                        schedule_lesson(db, occurrence_uid, summary, start, end)
                        events_processed += 1
        
        logger.info(f"Successfully processed {events_processed} events")
        db.close()
    except Exception as e:
        logger.error(f"Worker error in parse_and_schedule: {e}", exc_info=True)


if __name__ == '__main__':
    # Suppress noisy CalDAV CRITICAL logs about 'Expected some valid XML...'
    class CaldavNoiseFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            msg = str(record.getMessage())
            return 'Expected some valid XML from the server' not in msg

    logging.getLogger().addFilter(CaldavNoiseFilter())
    
    logger.info("=" * 60)
    logger.info("Worker started")
    logger.info(f"Polling interval: {settings.WORKER_POLL_SECONDS} seconds")
    logger.info("=" * 60)
    
    while True:
        try:
            logger.info(f'Worker running parse_and_schedule at {datetime.now()}')
            parse_and_schedule()
            logger.info(f'Worker completed cycle, sleeping for {settings.WORKER_POLL_SECONDS} seconds')
        except Exception as e:
            logger.error(f'Worker error: {e}', exc_info=True)
        time.sleep(settings.WORKER_POLL_SECONDS)
