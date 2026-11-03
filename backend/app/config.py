"""Конфигурация модуля: всё задаётся переменными окружения (12-factor)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "МП-3.5 «БДТС»"
    environment: str = "dev"
    database_url: str = "sqlite+aiosqlite:///./bdts.db"
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # Аутентификация: keycloak — проверка JWT по JWKS; dev — токены вида "dev:<логин>" (только для тестов)
    auth_mode: str = "dev"
    oidc_internal_url: str = "http://keycloak:8080/auth/realms/bdts"
    oidc_issuers: str = ""  # допустимые iss через запятую; пусто — не проверять
    oidc_audience: str = "bdts-api"

    # Инфраструктура (пустое значение — сервис отключён, используется встроенная замена)
    s3_endpoint: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "bdts"
    s3_secure: bool = False
    rabbitmq_url: str = ""
    redis_url: str = ""
    files_dir: str = "./data/files"  # локальное хранилище, если S3 не настроен

    # Адаптеры интеграций: mock — заглушки MVP
    adapter_plan: str = "mock"
    adapter_bdo: str = "mock"
    adapter_report_sink: str = "mock"
    adapter_diag_sink: str = "mock"
    adapter_ps0: str = "mock"
    adapter_notifier: str = "mock"
    suia_url_template: str = "https://suia.example/objects/{code}"

    seed_on_start: bool = True
    max_upload_mb: int = 50
    cors_origins: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
