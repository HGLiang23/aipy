from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)


class DatabaseSettings(BaseModel):
    url: str = "postgresql+psycopg://aipy:aipy@localhost:5432/aipy"


class RedisSettings(BaseModel):
    url: str = "redis://localhost:6379/0"


class CelerySettings(BaseModel):
    broker_url: str = "redis://localhost:6379/1"


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="AIPY_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    app_name: str = "AIPY API"
    environment: Literal["local", "test", "staging", "production"] = "local"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    api: ApiSettings = ApiSettings()
    database: DatabaseSettings = DatabaseSettings()
    redis: RedisSettings = RedisSettings()
    celery: CelerySettings = CelerySettings()


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()
