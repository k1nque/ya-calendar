# Система логирования

## 📋 Обзор

Все сервисы приложения используют централизованную систему логирования с автоматической ротацией файлов по дням.

## 📂 Структура логов

Все логи хранятся в директории `/app/logs` (монтируется из `./logs` на хосте):

```
logs/
├── bot.log              # Текущие логи Telegram бота
├── worker.log           # Текущие логи Calendar sync worker
├── celery_worker.log    # Текущие логи Celery task worker
├── bot.log.2025-10-01   # Архивные логи за 1 октября
├── worker.log.2025-10-01
└── ...
```

## ⚙️ Конфигурация

### Параметры ротации
- **Частота**: ежедневно в полночь (midnight)
- **Хранение**: последние 30 дней
- **Формат имени**: `<service>.log.YYYY-MM-DD`
- **Кодировка**: UTF-8

### Формат логов
```
YYYY-MM-DD HH:MM:SS - <logger_name> - <LEVEL> - <message>
```

Пример:
```
2025-10-01 15:30:45 - worker - INFO - Successfully processed 5 events
2025-10-01 15:31:12 - celery_worker - WARNING - No paid lessons to deduct for student Иван Иванов
```

## 🎯 Уровни логирования

### По умолчанию: INFO
- **DEBUG**: Детальная отладочная информация
- **INFO**: Основные события работы сервиса
- **WARNING**: Предупреждения о потенциальных проблемах
- **ERROR**: Ошибки выполнения
- **CRITICAL**: Критические ошибки

## 📊 Что логируется

### Worker (`worker.log`)
- Подключение к CalDAV
- Количество найденных событий
- Планирование уроков и уведомлений
- Создание/обновление задач в Celery
- Отмена старых задач
- Ошибки синхронизации

### Bot (`bot.log`)
- Запуск и остановка polling
- Обработка команд пользователей
- Отправка уведомлений
- Ошибки доставки сообщений
- HTTP API запросы

### Celery Worker (`celery_worker.log`)
- Инициализация worker
- Выполнение задач (уведомления, списания)
- Отметка уроков как оплаченных
- Уведомления админу
- Повторные попытки при ошибках

## 🔍 Просмотр логов

### Просмотр текущих логов
```bash
# Все логи бота
tail -f logs/bot.log

# Последние 100 строк worker
tail -n 100 logs/worker.log

# Логи celery в реальном времени
tail -f logs/celery_worker.log
```

### Поиск ошибок
```bash
# Все ошибки за сегодня
grep ERROR logs/*.log

# Предупреждения в worker
grep WARNING logs/worker.log

# Логи конкретного урока
grep "lesson_id=123" logs/*.log
```

### Анализ архивных логов
```bash
# Логи за конкретную дату
cat logs/bot.log.2025-10-01

# Все ошибки за период
grep ERROR logs/*.log.2025-10-*
```

## 🐳 Docker интеграция

Логи автоматически монтируются в контейнеры через `docker-compose.yml`:

```yaml
volumes:
  - ./logs:/app/logs
```

Просмотр логов через Docker:
```bash
# Логи сервиса в реальном времени
docker-compose logs -f bot
docker-compose logs -f worker
docker-compose logs -f celery

# Последние 100 строк
docker-compose logs --tail=100 bot
```

## 📝 Git

Файлы логов игнорируются в Git (`.gitignore`):
```
logs/*.log
logs/*.log.*
!logs/README.md
```

## 🛠️ Настройка

### Изменение уровня логирования

Для изменения уровня логирования отредактируйте файл `app/logging_config.py`:

```python
# Для DEBUG-уровня во всех сервисах
logger = setup_root_logging('service_name', log_level=logging.DEBUG)
```

### Изменение периода хранения

В `app/logging_config.py` измените параметр `backupCount`:

```python
file_handler = TimedRotatingFileHandler(
    filename=str(log_file),
    when='midnight',
    interval=1,
    backupCount=60,  # Хранить 60 дней вместо 30
    encoding='utf-8',
    utc=False
)
```

## 🚨 Мониторинг

Рекомендуемые действия для мониторинга:

1. **Ежедневная проверка** ошибок:
   ```bash
   grep ERROR logs/*.log | tail -20
   ```

2. **Отслеживание размера** логов:
   ```bash
   du -sh logs/
   ```

3. **Проверка работы** сервисов:
   ```bash
   # Последняя активность каждого сервиса
   tail -n 1 logs/bot.log
   tail -n 1 logs/worker.log
   tail -n 1 logs/celery_worker.log
   ```

## 💡 Лучшие практики

1. Регулярно проверяйте логи на наличие WARNING и ERROR
2. Используйте `grep` для фильтрации нужной информации
3. Архивируйте старые логи при необходимости
4. Мониторьте размер директории `logs/`
5. В production используйте централизованные системы сбора логов (ELK, Loki, etc.)
