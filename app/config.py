from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from functools import lru_cache

from pydantic import AnyUrl, Field, RedisDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class LogFormat(StrEnum):
    JSON = "json"
    CONSOLE = "console"


class Settings(BaseSettings):
    """Application settings loaded from environment variables and `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Barakah Transaction Intelligence Agent"
    app_version: str = "0.1.0"
    environment: Environment = Environment.DEVELOPMENT
    log_level: str = "INFO"
    log_format: LogFormat | None = None

    database_url: AnyUrl = Field(
        default="postgresql+asyncpg://barakah:barakah_dev@localhost:5432/barakah_agent"
    )
    redis_url: RedisDsn = Field(default="redis://localhost:6379/0")
    anthropic_api_key: SecretStr | None = None

    llm_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    llm_max_retries: int = Field(default=3, ge=0, le=10)
    gold_price_url: AnyUrl = Field(
        default="https://api.gold-api.com/price/XAU"
    )
    gold_fallback_price: Decimal = Field(default=Decimal("320.45"), gt=0)

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized = value.strip().upper()
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        if normalized not in allowed:
            raise ValueError(f"log_level must be one of: {', '.join(sorted(allowed))}")
        return normalized

    @property
    def effective_log_format(self) -> LogFormat:
        if self.log_format is not None:
            return self.log_format
        if self.environment is Environment.DEVELOPMENT:
            return LogFormat.CONSOLE
        return LogFormat.JSON

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()

