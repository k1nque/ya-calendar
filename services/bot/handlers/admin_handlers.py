"""
Обработчики команд для администратора
"""
from aiogram import types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramForbiddenError

from bot import dp, bot
from filters import IsAdmin, IsAdminCallback
from app.db import SessionLocal
from app import crud


@dp.message(F.text == '/start', IsAdmin)
async def cmd_start_admin(message: types.Message):
    """Обработчик команды /start для администратора"""
    help_text = """
🔧 Привет, администратор! 

Доступные команды:
/start - это сообщение
/students - список всех учеников
/inactive - управление активностью учеников
/payment - управление оплаченными занятиями
/help - справка по командам

Вы также получаете уведомления о новых пользователях для привязки к ученикам.
    """
    await message.answer(help_text.strip())


@dp.message(F.text == '/help', IsAdmin)
async def cmd_help_admin(message: types.Message):
    """Команда /help для администратора"""
    help_text = """
📖 Справка по командам администратора:

/start - приветствие и список команд
/students - показать список всех учеников с их статусами и количеством оплаченных занятий
/inactive - управление активностью учеников (включить/выключить)
/payment - управление оплаченными занятиями учеников
/help - эта справка

🔔 Автоматические уведомления:
• При подключении нового пользователя вы получите сообщение с кнопками для привязки к ученику
• Callback-кнопки для привязки пользователей работают только для вас
    """
    await message.answer(help_text.strip())


@dp.message(F.text == '/students', IsAdmin)
async def cmd_students(message: types.Message):
    """Команда /students - показать список всех учеников (только для администратора)"""
    db = SessionLocal()
    try:
        students = crud.list_students(db)
        if not students:
            await message.answer("Нет учеников в базе.")
            return
        
        students_info = []
        for s in students:
            status = "✅ Активен" if s.is_active else "❌ Неактивен"
            paid_lessons = s.paid_lessons_count
            students_info.append(f"• {s.summary}\n  Статус: {status}\n  Оплаченных занятий: {paid_lessons}")
        
        response = "📚 Список всех учеников:\n\n" + "\n\n".join(students_info)
        await message.answer(response)
    finally:
        db.close()


@dp.message(F.text == '/inactive', IsAdmin)
async def cmd_inactive(message: types.Message):
    """Команда /inactive доступна только администратору"""
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


@dp.callback_query(F.data.startswith('map:'), IsAdminCallback)
async def process_map(callback_query: types.CallbackQuery):
    """Обработчик привязки пользователей к ученикам (только для администратора)"""
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


@dp.callback_query(F.data.startswith('toggle_active:'), IsAdminCallback)
async def process_toggle_active(callback_query: types.CallbackQuery):
    """Обработчик переключения статуса активности ученика (только для администратора)"""
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


@dp.message(F.text == '/payment', IsAdmin)
async def cmd_payment(message: types.Message):
    """Команда /payment - управление оплаченными занятиями (только для администратора)"""
    db = SessionLocal()
    try:
        students = crud.list_students(db)
        if not students:
            await message.answer("Нет учеников в базе.")
            return
        
        kb = InlineKeyboardBuilder()
        for s in students:
            paid_count = s.paid_lessons_count
            button_text = f"{s.summary} ({paid_count} оплачено)"
            kb.button(text=button_text, callback_data=f"payment_select:{s.id}")
        kb.adjust(1)
        
        await message.answer(
            "💰 Выберите ученика для управления оплаченными занятиями:", 
            reply_markup=kb.as_markup()
        )
    finally:
        db.close()


@dp.callback_query(F.data.startswith('payment_select:'), IsAdminCallback)
async def process_payment_select(callback_query: types.CallbackQuery):
    """Обработчик выбора ученика для управления платежами"""
    data = callback_query.data.split(':')
    if len(data) != 2:
        await callback_query.answer('Неверные данные')
        return
    
    student_id = int(data[1])
    db = SessionLocal()
    try:
        student = crud.get_student_by_id(db, student_id)
        if not student:
            await callback_query.answer('Ученик не найден')
            return
        
        student_summary = student.summary
        paid_count = student.paid_lessons_count
        
        kb = InlineKeyboardBuilder()
        # Кнопки для быстрого добавления
        kb.button(text="➕1", callback_data=f"payment_add:{student_id}:1")
        kb.button(text="➕4", callback_data=f"payment_add:{student_id}:4")
        kb.button(text="➕8", callback_data=f"payment_add:{student_id}:8")
        kb.button(text="➕12", callback_data=f"payment_add:{student_id}:12")
        # Кнопки для вычитания
        kb.button(text="➖1", callback_data=f"payment_subtract:{student_id}:1")
        kb.button(text="➖5", callback_data=f"payment_subtract:{student_id}:5")
        # Установить точное значение
        kb.button(text="🔢 Установить точно", callback_data=f"payment_set:{student_id}")
        # Назад к списку
        kb.button(text="🔙 Назад к списку", callback_data="payment_back")
        kb.adjust(4, 2, 1, 1)
        
        await callback_query.message.edit_text(
            f"💰 Ученик: {student_summary}\n"
            f"Оплаченных занятий: {paid_count}\n\n"
            f"Выберите действие:",
            reply_markup=kb.as_markup()
        )
    finally:
        db.close()
    await callback_query.answer()


@dp.callback_query(F.data.startswith('payment_add:'), IsAdminCallback)
async def process_payment_add(callback_query: types.CallbackQuery):
    """Обработчик добавления оплаченных занятий"""
    data = callback_query.data.split(':')
    if len(data) != 3:
        await callback_query.answer('Неверные данные')
        return
    
    student_id = int(data[1])
    add_count = int(data[2])
    
    db = SessionLocal()
    try:
        student = crud.get_student_by_id(db, student_id)
        if not student:
            await callback_query.answer('Ученик не найден')
            return
        
        new_count = student.paid_lessons_count + add_count
        updated_student = crud.update_student_paid_lessons(db, student_id, new_count)
        
        if updated_student:
            await callback_query.answer(f"Добавлено {add_count} занятий. Всего: {new_count}")
            # Обновляем сообщение
            kb = InlineKeyboardBuilder()
            kb.button(text="➕1", callback_data=f"payment_add:{student_id}:1")
            kb.button(text="➕4", callback_data=f"payment_add:{student_id}:4")
            kb.button(text="➕8", callback_data=f"payment_add:{student_id}:8")
            kb.button(text="➕12", callback_data=f"payment_add:{student_id}:12")
            kb.button(text="➖1", callback_data=f"payment_subtract:{student_id}:1")
            kb.button(text="➖5", callback_data=f"payment_subtract:{student_id}:5")
            kb.button(text="🔢 Установить точно", callback_data=f"payment_set:{student_id}")
            kb.button(text="🔙 Назад к списку", callback_data="payment_back")
            kb.adjust(4, 2, 1, 1)
            
            await callback_query.message.edit_text(
                f"💰 Ученик: {updated_student.summary}\n"
                f"Оплаченных занятий: {new_count}\n\n"
                f"Выберите действие:",
                reply_markup=kb.as_markup()
            )
        else:
            await callback_query.answer('Ошибка при обновлении')
    finally:
        db.close()


@dp.callback_query(F.data.startswith('payment_subtract:'), IsAdminCallback)
async def process_payment_subtract(callback_query: types.CallbackQuery):
    """Обработчик вычитания оплаченных занятий"""
    data = callback_query.data.split(':')
    if len(data) != 3:
        await callback_query.answer('Неверные данные')
        return
    
    student_id = int(data[1])
    subtract_count = int(data[2])
    
    db = SessionLocal()
    try:
        student = crud.get_student_by_id(db, student_id)
        if not student:
            await callback_query.answer('Ученик не найден')
            return
        
        new_count = max(0, student.paid_lessons_count - subtract_count)
        updated_student = crud.update_student_paid_lessons(db, student_id, new_count)
        
        if updated_student:
            await callback_query.answer(f"Вычтено {subtract_count} занятий. Всего: {new_count}")
            # Обновляем сообщение
            kb = InlineKeyboardBuilder()
            kb.button(text="➕1", callback_data=f"payment_add:{student_id}:1")
            kb.button(text="➕4", callback_data=f"payment_add:{student_id}:4")
            kb.button(text="➕8", callback_data=f"payment_add:{student_id}:8")
            kb.button(text="➕12", callback_data=f"payment_add:{student_id}:12")
            kb.button(text="➖1", callback_data=f"payment_subtract:{student_id}:1")
            kb.button(text="➖5", callback_data=f"payment_subtract:{student_id}:5")
            kb.button(text="🔢 Установить точно", callback_data=f"payment_set:{student_id}")
            kb.button(text="🔙 Назад к списку", callback_data="payment_back")
            kb.adjust(4, 2, 1, 1)
            
            await callback_query.message.edit_text(
                f"💰 Ученик: {updated_student.summary}\n"
                f"Оплаченных занятий: {new_count}\n\n"
                f"Выберите действие:",
                reply_markup=kb.as_markup()
            )
        else:
            await callback_query.answer('Ошибка при обновлении')
    finally:
        db.close()


@dp.callback_query(F.data == 'payment_back', IsAdminCallback)
async def process_payment_back(callback_query: types.CallbackQuery):
    """Возврат к списку учеников для управления платежами"""
    db = SessionLocal()
    try:
        students = crud.list_students(db)
        if not students:
            await callback_query.message.edit_text("Нет учеников в базе.")
            return
        
        kb = InlineKeyboardBuilder()
        for s in students:
            paid_count = s.paid_lessons_count
            button_text = f"{s.summary} ({paid_count} оплачено)"
            kb.button(text=button_text, callback_data=f"payment_select:{s.id}")
        kb.adjust(1)
        
        await callback_query.message.edit_text(
            "💰 Выберите ученика для управления оплаченными занятиями:", 
            reply_markup=kb.as_markup()
        )
    finally:
        db.close()
    await callback_query.answer()