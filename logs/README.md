# Logs directory structure
# This directory will contain daily logs from all services:
# - bot.log (Telegram bot service)
# - worker.log (Calendar sync worker)
# - celery_worker.log (Celery task worker)
#
# Log files are rotated daily at midnight (1 file = 1 day)
# Old logs are kept for 30 days with format: <service>.log.YYYY-MM-DD
