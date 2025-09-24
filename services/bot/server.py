"""FastAPI server for Telegram bot notifications.

Clean version after removing corrupted merge/noise.

Endpoints:
  POST /notify {"lesson_id": <int>} - send notification about a lesson to all linked TG users
  GET  /health - liveness probe

On startup: launches aiogram polling in background with exponential backoff.
"""
from __future__ import annotations

import asyncio
import logging
from fastapi import FastAPI, HTTPException, Body, Depends

from bot import bot, dp, logger  # logger configured in bot.py
from app.db import SessionLocal, engine
from app import models, crud

# Ensure DB schema is created (idempotent)
models.Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency providing a SQLAlchemy session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


app = FastAPI(title="YA Calendar Bot Server")

# Import handlers so they register with dispatcher
# Side-effect imports: they register handlers in the dispatcher.
import handlers.admin_handlers  # noqa: E402,F401  pylint: disable=unused-import
import handlers.user_handlers   # noqa: E402,F401  pylint: disable=unused-import

_polling_task: asyncio.Task | None = None


async def _polling_loop():
    """Run aiogram polling with exponential backoff on failure."""
    delay = 5
    max_delay = 60
    while True:
        try:
            await dp.start_polling(bot)
            break  # normal shutdown
        except Exception as e:  # noqa: BLE001
            logger.warning("Polling error: %s. Retrying in %s seconds", e, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, max_delay)


@app.on_event("startup")
async def on_startup():
    global _polling_task
    logger.info("Starting polling background task")
    _polling_task = asyncio.create_task(_polling_loop())


@app.on_event("shutdown")
async def on_shutdown():
    global _polling_task
    if _polling_task and not _polling_task.done():
        logger.info("Shutting down polling task")
        _polling_task.cancel()
        try:
            await _polling_task
        except asyncio.CancelledError:  # noqa: PERF203
            pass


@app.post("/notify")
async def notify(lesson_id: int = Body(..., embed=True), db=Depends(get_db)):
    """Send a notification about a lesson to all linked Telegram users.

    Body: {"lesson_id": <int>}
    Returns: {"sent": <int>}
    """
    lesson = crud.get_lesson(db, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="lesson not found")

    links = crud.get_links_for_student(db, lesson.student_id)
    text = f"Урок: {lesson.summary}\nНачало: {lesson.start}\nID: {lesson.id}"

    sent = 0
    for link in links:
        try:
            await bot.send_message(int(link.tg_user_id), text)
            sent += 1
        except Exception as e:  # noqa: BLE001
            logging.debug("Failed to deliver to %s: %s", link.tg_user_id, e)
            continue

    return {"sent": sent}


@app.post("/admin_notify")
async def admin_notify(message: str = Body(..., embed=True)):
    """Send notification message to admin.
    
    Body: {"message": "<text>"}
    Returns: {"sent": <bool>}
    """
    from app.config import settings
    
    try:
        await bot.send_message(settings.ADMIN_TELEGRAM_ID, message)
        return {"sent": True}
    except Exception as e:
        logging.warning("Failed to send admin notification: %s", e)
        return {"sent": False, "error": str(e)}


@app.get("/health")
def health():
    return {"status": "ok"}
