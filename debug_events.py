import logging
from datetime import datetime, timedelta, timezone
import hashlib
from icalendar import Calendar
import caldav

from app.config import settings

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


def debug_parse_events():
    try:
        principal = get_principal(EMAIL, PASSWORD)
        cal = principal.calendar(name="Мои события")
        start_date = datetime.now(timezone.utc)
        end_date = start_date + timedelta(days=7)
        events = cal.search(start=start_date, end=end_date)
        print(f"Found {len(events)} events in the next 7 days:")
        for evt in events:
            calobj = Calendar.from_ical(evt.data)
            for component in calobj.walk():
                if component.name == "VEVENT":
                    summary = str(component.get('summary'))
                    uid = str(component.get('uid') or hashlib.sha1((summary+str(component.get('dtstart'))).encode()).hexdigest())
                    start = component.get('dtstart').dt
                    end = component.get('dtend').dt
                    description = str(component.get('description') or '')
                    print(f"Event UID: {uid}")
                    print(f"Summary: {summary}")
                    print(f"Start: {start}")
                    print(f"End: {end}")
                    print(f"Description: {description}")
                    print("-" * 50)
    except Exception as e:
        print(f"Error fetching events: {e}")


if __name__ == '__main__':
    # Suppress noisy CalDAV CRITICAL logs about 'Expected some valid XML...'
    class CaldavNoiseFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            msg = str(record.getMessage())
            return 'Expected some valid XML from the server' not in msg

    logging.getLogger().addFilter(CaldavNoiseFilter())
    debug_parse_events()