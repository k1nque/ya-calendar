"""
Фильтры для Telegram бота
"""
from aiogram import types
from app.config import settings


def is_admin_filter():
    """Фильтр для проверки, является ли отправитель администратором"""
    def check(message: types.Message) -> bool:
        return message.from_user.id == settings.ADMIN_TELEGRAM_ID
    return check


def is_admin_callback_filter():
    """Фильтр для проверки, является ли отправитель callback-запроса администратором"""
    def check(callback_query: types.CallbackQuery) -> bool:
        return callback_query.from_user.id == settings.ADMIN_TELEGRAM_ID
    return check


# Создаем экземпляры фильтров
IsAdmin = is_admin_filter()
IsAdminCallback = is_admin_callback_filter()