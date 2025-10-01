"""
Обработчики команд для обычных пользователей
"""
from aiogram import types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import dp, bot, logger
from app.config import settings
from app.db import SessionLocal
from app import crud


@dp.message(F.text == '/start')
async def cmd_start_user(message: types.Message):
    """Обработчик команды /start для обычных пользователей"""
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


@dp.message(F.text == '/lessons')
async def cmd_lessons(message: types.Message):
    """Показать список предстоящих уроков для пользователя"""
    db = SessionLocal()
    try:
        # Проверяем, привязан ли пользователь к ученику
        student = crud.get_student_by_tg_user_id(db, str(message.from_user.id))
        
        if not student:
            await message.answer(
                '❌ Вы не привязаны ни к одному ученику.\n'
                'Используйте /start для подключения.'
            )
            return
        
        # Получаем предстоящие уроки для этого ученика
        lessons = crud.get_lessons_for_student(db, student.id, upcoming_only=True, limit=10)
        
        if not lessons:
            await message.answer(
                f'📚 {student.summary}\n\n'
                f'На данный момент нет запланированных уроков.\n'
                f'Оплаченных занятий: {student.paid_lessons_count}'
            )
            return
        
        # Формируем сообщение со списком уроков
        response = f'📚 Предстоящие уроки для {student.summary}\n'
        response += f'💳 Оплаченных занятий: {student.paid_lessons_count}\n\n'
        
        for i, lesson in enumerate(lessons, 1):
            # Форматируем дату и время
            start_str = lesson.start.strftime('%d.%m.%Y %H:%M')
            paid_mark = '✅' if lesson.is_paid else '⏳'
            
            response += f'{i}. {paid_mark} {lesson.summary}\n'
            response += f'   📅 {start_str}\n'
            response += f'   🆔 ID: {lesson.id}\n\n'
        
        await message.answer(response)
        
    finally:
        db.close()