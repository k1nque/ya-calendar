from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str
    TG_BOT_TOKEN: str
    ADMIN_TELEGRAM_ID: int
    CALDAV_EMAIL: str
    CALDAV_PASSWORD: str
    CALDAV_WEBSITE: str = "https://caldav.yandex.ru/"
    WORKER_POLL_SECONDS: int = 600

    class Config:
        env_file = ".env"

settings = Settings()
