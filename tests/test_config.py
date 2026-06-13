import pytest
from pydantic import ValidationError

from app.config import Environment, LogFormat, Settings


def test_settings_normalize_log_level() -> None:
    settings = Settings(log_level=" debug ")

    assert settings.log_level == "DEBUG"


def test_settings_reject_invalid_log_level() -> None:
    with pytest.raises(ValidationError, match="log_level must be one of"):
        Settings(log_level="verbose")


def test_production_defaults_to_json_logging() -> None:
    settings = Settings(environment=Environment.PRODUCTION)

    assert settings.effective_log_format is LogFormat.JSON
    assert settings.is_production is True


def test_explicit_log_format_overrides_environment_default() -> None:
    settings = Settings(environment=Environment.PRODUCTION, log_format=LogFormat.CONSOLE)

    assert settings.effective_log_format is LogFormat.CONSOLE


def test_api_key_is_masked_in_settings_representation() -> None:
    settings = Settings(anthropic_api_key="secret-value")

    assert "secret-value" not in repr(settings)

