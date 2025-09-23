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
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

@dp.message(F.text == '/start')
async def cmd_start(message: types.Message):
    # If admin starts the bot, just greet and do not request any mapping
    if message.from_user.id == settings.ADMIN_TELEGRAM_ID:
        await message.answer('Привет, администратор! Вы можете подтверждать привязки и получать служебные уведомления.')
        return

    db = SessionLocal()
    try:
        # Проверяем, есть ли уже привязка у этого пользователя
        student = crud.get_student_by_tg_user_id(db, str(message.from_user.id))
        logger.debug(f"Existing link for user {message.from_user.id}: {student}")
        if student:
            # Сохраняем summary до закрытия сессии
            student_summary = student.summary
            db.close()
            await message.answer(f'Привет! Вы уже привязаны к ученику: {student_summary}. Вы будете получать уведомления о занятиях.')
            return

        await message.answer('Привет! Спасибо, что подключились. Жду подтверждения от администратора.')
        students = crud.list_students(db)
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
    finally:
        db.close()

@dp.callback_query(F.data.startswith('map:'))
async def process_map(callback_query: types.CallbackQuery):
    data = callback_query.data.split(':')
    if len(data) != 3:
        await callback_query.answer('Неверные данные')
        return
    tg_user_id = data[1]
    student_id = int(data[2])
    db = SessionLocal()
    try:
        student = crud.get_student_by_id(db, student_id)
        if not student:
            await callback_query.answer('Ученик не найден')
            return
        
        # Сохраняем summary до закрытия сессии
        student_summary = student.summary
        crud.create_tg_link(db, tg_user_id, student_id)
        db.commit()
    finally:
        db.close()
    
    # Редактируем сообщение, убираем клавиатуру и меняем текст
    await callback_query.message.edit_text(
        f"Пользователь привязан к ученику: {student_summary}",
        reply_markup=None
    )
    await callback_query.answer()
    
    try:
        await bot.send_message(int(tg_user_id), 'Вам назначен ученик. Теперь вы будете получать уведомления.')
    except TelegramForbiddenError:
        pass

@dp.message(F.text == '/inactive')
async def cmd_inactive(message: types.Message):
    # Показать список учеников для изменения статуса активности
    db = SessionLocal()
    try:
        students = crud.list_students(db)
        if not students:
            await message.answer("Нет учеников в базе.")
            return
        kb = InlineKeyboardBuilder()
        for s in students:
            status_text = "✅ Активен" if s.is_active else "❌ Неактивен"
            button_text = f"{s.summary} ({status_text})"
            kb.button(text=button_text, callback_data=f"toggle_active:{s.id}")
        kb.adjust(1)
        await message.answer("Выберите ученика для изменения статуса активности:", reply_markup=kb.as_markup())
    finally:
        db.close()

@dp.callback_query(F.data.startswith('toggle_active:'))
async def process_toggle_active(callback_query: types.CallbackQuery):
    data = callback_query.data.split(':')
    if len(data) != 2:
        await callback_query.answer('Неверные данные')
        return
    student_id = int(data[1])
    db = SessionLocal()
    try:
        student = crud.toggle_student_active_status(db, student_id)
        if not student:
            await callback_query.answer('Ошибка: ученик не найден')
            return
        
        # Сохраняем данные до закрытия сессии
        student_summary = student.summary
        student_is_active = student.is_active
        
        status_text = "активен" if student_is_active else "неактивен"
        await callback_query.answer(
            f"Статус ученика {student_summary} изменен: теперь {status_text}"
        )
        
        # Обновить клавиатуру с новым статусом
        students = crud.list_students(db)
        kb = InlineKeyboardBuilder()
        for s in students:
            status_display = "✅ Активен" if s.is_active else "❌ Неактивен"
            button_text = f"{s.summary} ({status_display})"
            kb.button(text=button_text, callback_data=f"toggle_active:{s.id}")
        kb.adjust(1)
        await callback_query.message.edit_text(
            "Выберите ученика для изменения статуса активности:", 
            reply_markup=kb.as_markup()
        )
    finally:
        db.close()

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
