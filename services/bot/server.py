import asyncio
from fastapi import FastAPI, HTTPException
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.exceptions import TelegramForbiddenError
from app.config import settings
from app.db import SessionLocal, engine
from app import models, crud

models.Base.metadata.create_all(bind=engine)

bot = Bot(token=settings.TG_BOT_TOKEN)
dp = Dispatcher()
app = FastAPI()

@dp.message(F.text == '/start')
async def cmd_start(message: types.Message):
    await message.answer('Привет! Спасибо, что подключились. Жду подтверждения от администратора.')
    db = SessionLocal()
    students = crud.list_students(db)
    db.close()
    if not students:
        await bot.send_message(settings.ADMIN_TELEGRAM_ID, 'Нет учеников в базе. Пожалуйста, запустите воркер и попробуйте позже.')
        return
    kb = InlineKeyboardMarkup(row_width=1)
    for s in students:
        kb.add(InlineKeyboardButton(text=s.summary, callback_data=f"map:{message.from_user.id}:{s.id}"))
    await bot.send_message(settings.ADMIN_TELEGRAM_ID, f"Пользователь @{message.from_user.username} ({message.from_user.id}) просит привязку. Выберите ученика:", reply_markup=kb)

@dp.callback_query(F.text == 'map:')
async def process_map(callback_query: types.CallbackQuery):
    data = callback_query.data.split(':')
    if len(data) != 3:
        await callback_query.answer('Неверные данные')
        return
    tg_user_id = data[1]
    student_id = int(data[2])
    db = SessionLocal()
    crud.create_tg_link(db, tg_user_id, student_id)
    db.close()
    await callback_query.answer('Привязка сохранена')
    try:
        await bot.send_message(int(tg_user_id), 'Вам назначен ученик. Теперь вы будете получать уведомления.')
    except TelegramForbiddenError:
        pass

@app.post('/notify')
def notify(lesson_id: int):
    db = SessionLocal()
    lesson = crud.get_lesson(db, lesson_id)
    if not lesson:
        db.close()
        raise HTTPException(status_code=404, detail='lesson not found')
    links = crud.get_links_for_student(db, lesson.student_id)
    db.close()
    text = f"Урок: {lesson.summary}\nНачало: {lesson.start}\nСсылка: {lesson.description}"
    sent = 0
    for link in links:
        try:
            asyncio.get_event_loop().create_task(bot.send_message(int(link.tg_user_id), text))
            sent += 1
        except Exception:
            pass
    return {"sent": sent}

@app.on_event('startup')
async def on_startup():
    loop = asyncio.get_event_loop()
    loop.create_task(dp.start_polling(bot))
