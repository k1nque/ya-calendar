from base64 import b64encode
from datetime import datetime, timedelta
from icalendar import Calendar

import caldav


email = "kibaken337@yandex.ru"
password = "paextzohlvxayiqk"

token = b64encode(f"{email}:{password}".encode()).decode()

website = "https://caldav.yandex.ru/"


def get_principal(username, leg_token):
    client = caldav.DAVClient(url=website, username=username, password=leg_token)
    principal = client.principal()
    return principal

my_principal = get_principal(email, password)

calendar = my_principal.calendar(name="Мои события")
events = calendar.date_search(start=datetime.now(), end=datetime.now() + timedelta(days=7))
for evt in events:
    # print(evt.get_property(["X-TELEMOST-CONFERENCE"]))
    cal  = Calendar.from_ical(evt.data)
    for component in cal.walk():
        if component.name == "VEVENT":
            print("Summary:", component.get("summary")) # Имя фамилия ученика
            print("Start:", component.get("dtstart"))
            print("End:", component.get("dtend"))
            print("Description:", component.get("description")) # ссылка на урок