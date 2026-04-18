from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    app_name: str = "Grocery PWA"
    debug: bool = False
    secret_key: str = "change-me-in-production"
    base_url: str = "http://localhost:80"

    # Database
    database_url: str = "sqlite+aiosqlite:////data/grocery.db"

    # JWT
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    # SMTP
    smtp_host: str = "email-smtp.eu-west-1.amazonaws.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_sender: str = "no-reply@stackxperts.com"
    smtp_use_tls: bool = True

    # ML
    ml_model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
