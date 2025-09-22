# YA Calendar Bot Suite

This repository contains a microservices stack (worker, celery, bot) to poll a CalDAV calendar, schedule notifications 30 minutes before lessons,
and send them to Telegram accounts mapped to students.

Services
- worker: polls CalDAV and schedules Celery tasks
- celery: executes tasks and calls bot HTTP endpoint
- bot: aiogram-based Telegram bot + FastAPI endpoint that sends messages
- postgres and redis via docker-compose

Setup
1. Copy `.env.example` to `.env` and fill values.
2. Build and run with docker-compose:

```bash
docker compose up --build
```

Notes
- Database tables are created automatically on service startup using SQLAlchemy models.
- Celery broker and backend use Redis.

Requirements coverage
- Worker: implemented in `services/worker/main.py` — polls CalDAV, upserts lessons, schedules celery tasks 30 minutes before start, stores scheduled task meta in Redis.
- Celery worker: `services/celery_worker` — runs tasks that call bot HTTP endpoint to deliver notifications.
- Telegram bot: `services/bot/app.py` — aiogram bot with `/start` flow (notifies admin to map account) and FastAPI `/notify` endpoint.
- PostgresDB: configured in `docker-compose.yml`, models in `app/models.py`, CRUD in `app/crud.py`.
- Redis: configured in `docker-compose.yml`, used as Celery broker and worker cache.

What's next / possible improvements
- Add unit tests and CI pipeline.
- Improve error handling and add observability (logging/metrics).
- Use Alembic for migrations instead of `create_all`.

