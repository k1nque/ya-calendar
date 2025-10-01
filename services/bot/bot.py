"""
Конфигурация Telegram бота
"""
import logging
from aiogram import Bot, Dispatcher
from app.config import settings
from app.logging_config import setup_root_logging

# Настройка логирования с ротацией по дням
logger = setup_root_logging('bot', log_level=logging.INFO)

# Создание экземпляров бота и диспетчера
bot = Bot(token=settings.TG_BOT_TOKEN)
dp = Dispatcher()