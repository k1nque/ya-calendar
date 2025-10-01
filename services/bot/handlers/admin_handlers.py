"""
Обработчики команд для администратора Telegram-бота
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from aiogram import F, types
from aiogram.exceptions import TelegramForbiddenError
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app import crud
from app.db import SessionLocal
from bot import bot, dp, logger
from filters import IsAdmin, IsAdminCallback

# Временное хранилище для установки точного значения оплаченных занятий
_PENDING_PAYMENT_SET: dict[int, int] = {}

# Ограничение на число уроков, показываемых администратору
_LESSONS_LIMIT: Final[int] = 20


def _format_students_list(students: Iterable, include_paid: bool = True) -> str:
    """Сформировать человекочитаемый список учеников."""
    lines: list[str] = []
    for student in students:
        status = "✅ Активен" if student.is_active else "❌ Неактивен"
        paid = f"\n  Оплаченных занятий: {student.paid_lessons_count}" if include_paid else ""
        lines.append(f"• {student.summary}\n  Статус: {status}{paid}")
    return "\n\n".join(lines)


def _build_students_keyboard(students, callback_template: str) -> InlineKeyboardBuilder:
    """Построить клавиатуру с учениками и произвольным шаблоном callback."""
    kb = InlineKeyboardBuilder()
    for student in students:
        status_display = "✅ Активен" if student.is_active else "❌ Неактивен"
        kb.button(
            text=f"{student.summary} ({status_display})",
            callback_data=f"{callback_template}:{student.id}",
        )
    kb.adjust(1)
    return kb


def _build_payment_keyboard(student_id: int) -> InlineKeyboardBuilder:
    """Клавиатура для управления количеством оплаченных занятий."""
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
    return kb


@dp.message(F.text == "/start", IsAdmin)
async def cmd_start_admin(message: types.Message) -> None:
    """Обработчик команды /start для администратора."""
    help_text = (
        "🔧 Привет, администратор!\n\n"
        "Доступные команды:\n"
        "/start — это сообщение\n"
        "/help — справка по командам\n"
        "/students — список всех учеников\n"
        "/inactive — управление активностью учеников\n"
        "/payment — управление оплаченными занятиями\n"
        "/lessons — предстоящие уроки\n"
        "\nВы также получаете уведомления о новых пользователях для привязки к ученикам."
    )
    await message.answer(help_text)


@dp.message(F.text == "/help", IsAdmin)
async def cmd_help_admin(message: types.Message) -> None:
    """Команда /help для администратора."""
    help_text = (
        "📖 Справка по командам администратора:\n\n"
        "/start — приветствие и список команд\n"
        "/students — показать всех учеников с их статусами и количеством оплаченных занятий\n"
        "/inactive — включить/выключить активность ученика\n"
        "/payment — добавить/убрать оплаченные занятия ученикам\n"
        "/lessons — показать ближайшие уроки (до 20)\n"
        "\n🔔 Автоматические уведомления:\n"
        "• При подключении нового пользователя вы получите сообщение с кнопками для привязки к ученику\n"
        "• Callback-кнопки для привязки пользователей работают только для вас"
    )
    await message.answer(help_text)


@dp.message(F.text == "/students", IsAdmin)
async def cmd_students(message: types.Message) -> None:
    """Показать список всех учеников."""
    db = SessionLocal()
    try:
        students = crud.list_students(db)
        if not students:
            await message.answer("Нет учеников в базе.")
            return
        response = "📚 Список всех учеников:\n\n" + _format_students_list(students)
        await message.answer(response)
    finally:
        db.close()


@dp.message(F.text == "/inactive", IsAdmin)
async def cmd_inactive(message: types.Message) -> None:
    """Показать клавиатуру для управления активностью учеников."""
    db = SessionLocal()
    try:
        students = crud.list_students(db)
        if not students:
            await message.answer("Нет учеников в базе.")
            return
        kb = _build_students_keyboard(students, "toggle_active")
        await message.answer(
            "Выберите ученика для изменения статуса активности:",
            reply_markup=kb.as_markup(),
        )
    finally:
        db.close()


@dp.message(F.text == "/lessons", IsAdmin)
async def cmd_lessons_admin(message: types.Message) -> None:
    """Показать список предстоящих уроков."""
    db = SessionLocal()
    try:
        lessons = crud.get_upcoming_lessons(db, limit=_LESSONS_LIMIT)
        if not lessons:
            await message.answer("📚 На данный момент нет запланированных уроков.")
            return

        response_lines = [
            f"📚 Все предстоящие уроки ({len(lessons)}):",
            "",
        ]
        for idx, lesson in enumerate(lessons, 1):
            start_str = lesson.start.strftime("%d.%m.%Y %H:%M")
            paid_mark = "✅" if lesson.is_paid else "⏳"
            student_name = lesson.student.summary if lesson.student else "Неизвестный"
            response_lines.append(f"{idx}. {paid_mark} {lesson.summary}")
            response_lines.append(f"   👤 {student_name}")
            response_lines.append(f"   📅 {start_str}")
            response_lines.append(f"   🆔 ID: {lesson.id}\n")
        await message.answer("\n".join(response_lines).strip())
    finally:
        db.close()


@dp.callback_query(F.data.startswith("map:"), IsAdminCallback)
async def process_map(callback_query: types.CallbackQuery) -> None:
    """Привязать Telegram-пользователя к ученику."""
    data = callback_query.data.split(":")
    if len(data) != 3:
        await callback_query.answer("Неверные данные")
        return

    tg_user_id = data[1]
    student_id = int(data[2])
    db = SessionLocal()
    try:
        student = crud.get_student_by_id(db, student_id)
        if not student:
            await callback_query.answer("Ученик не найден")
            return
        student_summary = student.summary
        crud.create_tg_link(db, tg_user_id, student_id)
        db.commit()
    finally:
        db.close()

    await callback_query.message.edit_text(
        f"Пользователь привязан к ученику: {student_summary}", reply_markup=None
    )
    await callback_query.answer()

    try:
        await bot.send_message(int(tg_user_id), "Вам назначен ученик. Теперь вы будете получать уведомления.")
    except TelegramForbiddenError:
        logger.warning("Не удалось отправить сообщение пользователю %s после привязки", tg_user_id)


@dp.callback_query(F.data.startswith("toggle_active:"), IsAdminCallback)
async def process_toggle_active(callback_query: types.CallbackQuery) -> None:
    """Переключить активность ученика."""
    data = callback_query.data.split(":")
    if len(data) != 2:
        await callback_query.answer("Неверные данные")
        return

    student_id = int(data[1])
    db = SessionLocal()
    try:
        student = crud.toggle_student_active_status(db, student_id)
        if not student:
            await callback_query.answer("Ошибка: ученик не найден")
            return
        student_summary = student.summary
        status_text = "активен" if student.is_active else "неактивен"
        students = crud.list_students(db)
        kb = _build_students_keyboard(students, "toggle_active")
    finally:
        db.close()

    await callback_query.message.edit_text(
        "Выберите ученика для изменения статуса активности:",
        reply_markup=kb.as_markup(),
    )
    await callback_query.answer(f"Статус ученика {student_summary} изменен: теперь {status_text}")


@dp.message(F.text == "/payment", IsAdmin)
async def cmd_payment(message: types.Message) -> None:
    """Команда /payment — управление оплаченными занятиями."""
    db = SessionLocal()
    try:
        students = crud.list_students(db)
        if not students:
            await message.answer("Нет учеников в базе.")
            return
        kb = InlineKeyboardBuilder()
        for student in students:
            kb.button(
                text=f"{student.summary} ({student.paid_lessons_count} оплачено)",
                callback_data=f"payment_select:{student.id}",
            )
        kb.adjust(1)
        await message.answer(
            "💰 Выберите ученика для управления оплаченными занятиями:",
            reply_markup=kb.as_markup(),
        )
    finally:
        db.close()


@dp.callback_query(F.data.startswith("payment_select:"), IsAdminCallback)
async def process_payment_select(callback_query: types.CallbackQuery) -> None:
    """Выбор ученика для изменения количества оплаченных занятий."""
    data = callback_query.data.split(":")
    if len(data) != 2:
        await callback_query.answer("Неверные данные")
        return

    student_id = int(data[1])
    db = SessionLocal()
    try:
        student = crud.get_student_by_id(db, student_id)
        if not student:
            await callback_query.answer("Ученик не найден")
            return
        student_summary = student.summary
        paid_count = student.paid_lessons_count
    finally:
        db.close()

    kb = _build_payment_keyboard(student_id)
    await callback_query.message.edit_text(
        f"💰 Ученик: {student_summary}\n"
        f"Оплаченных занятий: {paid_count}\n\n"
        f"Выберите действие:",
        reply_markup=kb.as_markup(),
    )
    await callback_query.answer()


async def _apply_paid_lessons_change(callback_query: types.CallbackQuery, student_id: int, new_count: int) -> None:
    """Обновить количество оплаченных занятий и обновить сообщение."""
    db = SessionLocal()
    try:
        updated_student = crud.update_student_paid_lessons(db, student_id, new_count)
        if not updated_student:
            await callback_query.answer("Ошибка при обновлении")
            return
        summary = updated_student.summary
        paid_count = updated_student.paid_lessons_count
    finally:
        db.close()

    kb = _build_payment_keyboard(student_id)
    await callback_query.message.edit_text(
        f"💰 Ученик: {summary}\n"
        f"Оплаченных занятий: {paid_count}\n\n"
        f"Выберите действие:",
        reply_markup=kb.as_markup(),
    )
    await callback_query.answer(f"Новое значение: {paid_count}")


@dp.callback_query(F.data.startswith("payment_add:"), IsAdminCallback)
async def process_payment_add(callback_query: types.CallbackQuery) -> None:
    """Добавление оплаченных занятий."""
    data = callback_query.data.split(":")
    if len(data) != 3:
        await callback_query.answer("Неверные данные")
        return
    student_id = int(data[1])
    add_count = int(data[2])

    db = SessionLocal()
    try:
        student = crud.get_student_by_id(db, student_id)
        if not student:
            await callback_query.answer("Ученик не найден")
            return
        new_count = student.paid_lessons_count + add_count
    finally:
        db.close()

    await _apply_paid_lessons_change(callback_query, student_id, new_count)


@dp.callback_query(F.data.startswith("payment_subtract:"), IsAdminCallback)
async def process_payment_subtract(callback_query: types.CallbackQuery) -> None:
    """Вычитание оплаченных занятий."""
    data = callback_query.data.split(":")
    if len(data) != 3:
        await callback_query.answer("Неверные данные")
        return
    student_id = int(data[1])
    subtract_count = int(data[2])

    db = SessionLocal()
    try:
        student = crud.get_student_by_id(db, student_id)
        if not student:
            await callback_query.answer("Ученик не найден")
            return
        new_count = max(0, student.paid_lessons_count - subtract_count)
    finally:
        db.close()

    await _apply_paid_lessons_change(callback_query, student_id, new_count)


@dp.callback_query(F.data == "payment_back", IsAdminCallback)
async def process_payment_back(callback_query: types.CallbackQuery) -> None:
    """Возврат к списку учеников в разделе /payment."""
    db = SessionLocal()
    try:
        students = crud.list_students(db)
        if not students:
            await callback_query.message.edit_text("Нет учеников в базе.")
            return
        kb = InlineKeyboardBuilder()
        for student in students:
            kb.button(
                text=f"{student.summary} ({student.paid_lessons_count} оплачено)",
                callback_data=f"payment_select:{student.id}",
            )
        kb.adjust(1)
    finally:
        db.close()

    await callback_query.message.edit_text(
        "💰 Выберите ученика для управления оплаченными занятиями:",
        reply_markup=kb.as_markup(),
    )
    await callback_query.answer()


@dp.callback_query(F.data.startswith("payment_set:"), IsAdminCallback)
async def process_payment_set(callback_query: types.CallbackQuery) -> None:
    """Подготовить установку точного значения оплаченных занятий."""
    data = callback_query.data.split(":")
    if len(data) != 2:
        await callback_query.answer("Неверные данные")
        return
    student_id = int(data[1])

    db = SessionLocal()
    try:
        student = crud.get_student_by_id(db, student_id)
        if not student:
            await callback_query.answer("Ученик не найден")
            return
        student_summary = student.summary
        paid_count = student.paid_lessons_count
    finally:
        db.close()

    admin_id = callback_query.from_user.id
    _PENDING_PAYMENT_SET[admin_id] = student_id

    await callback_query.message.answer(
        f"Введите новое количество оплаченных занятий для {student_summary}.\n"
        f"Текущее значение: {paid_count}.\n"
        "Отправьте целое число или /cancel для отмены.",
    )
    await callback_query.answer("Ожидаю новое значение")


@dp.message(IsAdmin, F.text == "/cancel")
async def process_payment_set_cancel(message: types.Message) -> None:
    """Отмена режима установки точного количества занятий."""
    if message.from_user.id in _PENDING_PAYMENT_SET:
        _PENDING_PAYMENT_SET.pop(message.from_user.id, None)
        await message.answer("Установка точного значения отменена.")


@dp.message(IsAdmin, F.text.regexp(r"^\d+$"))
async def process_payment_set_value(message: types.Message) -> None:
    """Получить новое значение количества оплаченных занятий от администратора."""
    admin_id = message.from_user.id
    if admin_id not in _PENDING_PAYMENT_SET:
        return

    new_value = int(message.text)
    student_id = _PENDING_PAYMENT_SET.pop(admin_id)

    db = SessionLocal()
    try:
        updated_student = crud.update_student_paid_lessons(db, student_id, new_value)
        if not updated_student:
            await message.answer("Ошибка при обновлении данных ученика.")
            return
    finally:
        db.close()

    kb = _build_payment_keyboard(student_id)
    await message.answer(
        f"💰 Ученик: {updated_student.summary}\n"
        f"Новое количество оплаченных занятий: {new_value}",
        reply_markup=kb.as_markup(),
    )
    logger.info(
        "Admin %s установил точное количество оплаченных занятий для ученика %s: %s",
        admin_id,
        updated_student.summary,
        new_value,
    )
