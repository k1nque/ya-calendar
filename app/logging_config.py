"""Общая конфигурация логирования для всех сервисов с ротацией по дням."""
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


def setup_logging(service_name: str, log_level: int = logging.INFO) -> logging.Logger:
    """
    Настроить логирование для сервиса с ротацией файлов по дням.
    
    Args:
        service_name: Имя сервиса (bot, worker, celery_worker)
        log_level: Уровень логирования (по умолчанию INFO)
    
    Returns:
        Настроенный logger
    """
    # Создаем директорию для логов, если её нет
    log_dir = Path("/app/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Создаем logger
    logger = logging.getLogger(service_name)
    logger.setLevel(log_level)
    
    # Очищаем существующие handlers, чтобы избежать дубликатов
    logger.handlers.clear()
    
    # Формат логов
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Handler для файла с ротацией по дням (1 файл = 1 день)
    log_file = log_dir / f"{service_name}.log"
    file_handler = TimedRotatingFileHandler(
        filename=str(log_file),
        when='midnight',  # Ротация в полночь
        interval=1,       # Каждый день
        backupCount=30,   # Хранить логи за последние 30 дней
        encoding='utf-8',
        utc=False
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(log_level)
    
    # Handler для вывода в консоль
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)
    
    # Добавляем handlers к logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


def setup_root_logging(service_name: str, log_level: int = logging.INFO):
    """
    Настроить корневой logger для перехвата всех логов в приложении.
    
    Args:
        service_name: Имя сервиса для имени файла
        log_level: Уровень логирования
    """
    # Создаем директорию для логов
    log_dir = Path("/app/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Очищаем существующие handlers у root logger
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(log_level)
    
    # Формат логов
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Handler для файла
    log_file = log_dir / f"{service_name}.log"
    file_handler = TimedRotatingFileHandler(
        filename=str(log_file),
        when='midnight',
        interval=1,
        backupCount=30,
        encoding='utf-8',
        utc=False
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(log_level)
    
    # Handler для консоли
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)
    
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    return root_logger
