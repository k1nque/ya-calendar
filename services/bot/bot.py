"""
Конфигурация Telegram бота
"""
import logging
from aiogram import Bot, Dispatcher
from app.config import settings

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Создание экземпляров бота и диспетчера
bot = Bot(token=settings.TG_BOT_TOKEN)
dp = Dispatcher()