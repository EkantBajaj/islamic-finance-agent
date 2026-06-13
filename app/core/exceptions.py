from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class BarakahError(Exception):
    """Base exception carrying a stable code and safe public details."""

    default_code = "application_error"
    default_message = "An application error occurred."
    default_status_code = 500
    retryable = False

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.code = code or self.default_code
        self.status_code = self.default_status_code
        self.details = dict(details or {})
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.details:
            payload["details"] = self.details
        return payload


class ConfigurationError(BarakahError):
    default_code = "configuration_error"
    default_message = "The application is not configured correctly."


class PipelineError(BarakahError):
    default_code = "pipeline_error"
    default_message = "The transaction pipeline failed."


class PipelineStageError(PipelineError):
    default_code = "pipeline_stage_error"

    def __init__(self, stage: str, message: str, *, fallback_used: bool = False) -> None:
        self.stage = stage
        self.fallback_used = fallback_used
        super().__init__(
            message,
            details={"stage": stage, "fallback_used": fallback_used},
        )


class DependencyError(BarakahError):
    default_code = "dependency_error"
    default_message = "An external dependency is unavailable."
    default_status_code = 503
    retryable = True


class DatabaseError(DependencyError):
    default_code = "database_error"
    default_message = "The database is unavailable."


class CacheError(DependencyError):
    default_code = "cache_error"
    default_message = "The cache is unavailable."


class LLMError(DependencyError):
    default_code = "llm_error"
    default_message = "The language model provider is unavailable."


class LLMResponseError(LLMError):
    default_code = "llm_response_error"
    default_message = "The language model returned an invalid response."
    retryable = False


class CircuitOpenError(DependencyError):
    default_code = "circuit_open"
    default_message = "The dependency circuit breaker is open."

    def __init__(self, dependency: str, *, retry_after_seconds: float | None = None) -> None:
        details: dict[str, Any] = {"dependency": dependency}
        if retry_after_seconds is not None:
            details["retry_after_seconds"] = retry_after_seconds
        super().__init__(details=details)


class ResourceNotFoundError(BarakahError):
    default_code = "resource_not_found"
    default_message = "The requested resource was not found."
    default_status_code = 404


class ValidationError(BarakahError):
    default_code = "validation_error"
    default_message = "The request is invalid."
    default_status_code = 422

