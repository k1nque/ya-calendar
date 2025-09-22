import asyncio
import logging
from fastapi import FastAPI, HTTPException, Body
from aiogram import Bot, Dispatcher, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramForbiddenError
from app.config import settings
from app.db import SessionLocal, engine
from app import models, crud

models.Base.metadata.create_all(bind=engine)

bot = Bot(token=settings.TG_BOT_TOKEN)
dp = Dispatcher()
app = FastAPI()
logger = logging.getLogger(__name__)

@dp.message(F.text == '/start')
async def cmd_start(message: types.Message):
    # If admin starts the bot, just greet and do not request any mapping
    if message.from_user.id == settings.ADMIN_TELEGRAM_ID:
        await message.answer('Привет, администратор! Вы можете подтверждать привязки и получать служебные уведомления.')
        return

    await message.answer('Привет! Спасибо, что подключились. Жду подтверждения от администратора.')
    db = SessionLocal()
    students = crud.list_students(db)
    db.close()
    if not students:
        await bot.send_message(settings.ADMIN_TELEGRAM_ID, 'Нет учеников в базе. Пожалуйста, запустите воркер и попробуйте позже.')
        return
    kb = InlineKeyboardBuilder()
    for s in students:
        kb.button(text=s.summary, callback_data=f"map:{message.from_user.id}:{s.id}")
    kb.adjust(1)
    await bot.send_message(
        settings.ADMIN_TELEGRAM_ID,
        f"Пользователь @{message.from_user.username} ({message.from_user.id}) просит привязку. Выберите ученика:",
        reply_markup=kb.as_markup(),
    )

@dp.callback_query(F.data.startswith('map:'))
async def process_map(callback_query: types.CallbackQuery):
    data = callback_query.data.split(':')
    if len(data) != 3:
        await callback_query.answer('Неверные данные')
        return
    tg_user_id = data[1]
    student_id = int(data[2])
    db = SessionLocal()
    student = crud.get_student_by_id(db, student_id)
    crud.create_tg_link(db, tg_user_id, student_id)
    db.close()
    
    # Редактируем сообщение, убираем клавиатуру и меняем текст
    await callback_query.message.edit_text(
        f"Пользователь привязан к ученику: {student.summary}",
        reply_markup=None
    )
    await callback_query.answer()
    
    try:
        await bot.send_message(int(tg_user_id), 'Вам назначен ученик. Теперь вы будете получать уведомления.')
    except TelegramForbiddenError:
        pass

@app.post('/notify')
async def notify(lesson_id: int = Body(..., embed=True)):
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
            await bot.send_message(int(link.tg_user_id), text)
            sent += 1
        except Exception:
            # Ignore delivery errors for individual users
            pass
    return {"sent": sent}

@app.get('/health')
def health():
    return {"status": "ok"}

@app.on_event('startup')
async def on_startup():
    async def polling_loop():
        delay = 5
        while True:
            try:
                await dp.start_polling(bot)
                # If polling exits normally (shutdown), break loop
                break
            except Exception as e:
                logger.warning(f"Polling error: {e}. Retrying in {delay}s")
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60)

    asyncio.get_event_loop().create_task(polling_loop())
