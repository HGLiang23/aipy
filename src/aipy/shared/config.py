from datetime import timedelta
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, SecretStr
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


class JwtSettings(BaseModel):
    """JWT signing configuration.

    ``secret_key`` has no default: outside local/test it must be supplied via
    ``AIPY_JWT__SECRET_KEY`` or the application refuses to start. See
    :func:`aipy.shared.config.jwt_secret` for the resolution rules.
    """

    secret_key: SecretStr | None = None
    issuer: str = Field(default="aipy", min_length=1)
    audience: str = Field(default="aipy", min_length=1)
    access_token_ttl: timedelta = timedelta(minutes=15)
    refresh_token_ttl: timedelta = timedelta(days=14)


class SecuritySettings(BaseModel):
    """Login brute-force protection."""

    login_max_attempts: int = Field(default=10, ge=1, le=100)
    login_lockout: timedelta = timedelta(minutes=15)


class LlmSettings(BaseModel):
    """OpenAI-compatible model endpoint.

    Any provider that speaks the OpenAI chat completions contract works here -
    OpenAI itself, DeepSeek, 通义/智谱 (DashScope), or a local vLLM. Leave all
    three blank in local/test to fall back to :class:`StubModelGateway`; set them
    in staging/production to generate real content.
    """

    base_url: str | None = None
    api_key: SecretStr | None = None
    model: str | None = None
    timeout: float = Field(default=60.0, gt=0)


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
    jwt: JwtSettings = JwtSettings()
    security: SecuritySettings = SecuritySettings()
    llm: LlmSettings = LlmSettings()
    cors_origins: list[str] = ["http://localhost:3000"]

    @property
    def llm_configured(self) -> bool:
        """Whether a real model endpoint is configured (all three fields set)."""

        return (
            self.llm.base_url is not None
            and self.llm.api_key is not None
            and self.llm.model is not None
        )

    @property
    def cookie_secure(self) -> bool:
        """Send auth cookies with the ``Secure`` flag outside local/test."""

        return self.environment in ("staging", "production")

    @property
    def uses_shared_state(self) -> bool:
        """Whether revocation/lockout state must live in Redis.

        Local and test runs may keep that state in the process; any other
        environment runs multiple workers and needs a shared store.
        """

        return self.environment not in ("local", "test")


DEV_JWT_SECRET = "dev-only-insecure-secret-change-me-32+chars!!"


def jwt_secret(settings: AppSettings) -> SecretStr:
    """Resolve the signing key, refusing to fall back outside local/test.

    A missing key in staging/production is a deployment error, not something to
    paper over with a well-known default: doing so would let anyone forge tokens.
    """

    if settings.jwt.secret_key is not None:
        return settings.jwt.secret_key
    if not settings.uses_shared_state:
        return SecretStr(DEV_JWT_SECRET)
    raise RuntimeError(
        "AIPY_JWT__SECRET_KEY must be set when environment is "
        f"{settings.environment!r}; refusing to use the development key"
    )


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()
