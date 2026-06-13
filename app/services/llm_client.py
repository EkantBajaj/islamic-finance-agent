from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
from typing import Any

import anthropic
import structlog
from anthropic import AsyncAnthropic

from app.config import get_settings
from app.core.circuit_breaker import CircuitBreaker
from app.core.exceptions import CircuitOpenError, LLMError
from app.services.cache import RedisCache
from app.services.sanitizer import LLMSanitizer

logger = structlog.get_logger()

MODEL_REGISTRY = {
    "categorizer": {
        "model": "claude-3-haiku-20240307",
        "version": "v1.0",
        "prompt_version": "cat-v3",
        "fallback_model": "rules-engine-v2",
    },
    "shariah_screener": {
        "model": "claude-3-haiku-20240307",
        "version": "v1.0",
        "prompt_version": "shariah-v2",
        "fallback_model": "blocklist-v1",
    },
    "insight_generator": {
        "model": "claude-3-5-sonnet-20241022",
        "version": "v1.0",
        "prompt_version": "insight-v1",
        "fallback_model": "template-engine-v1",
    },
}

MODEL_ALIASES = {
    "claude-haiku": "claude-3-haiku-20240307",
    "claude-sonnet": "claude-3-5-sonnet-20241022",
}


class LLMResponse:
    """Wrapped response returned by the LLM client.

    Provides transparent string-like behavior, property-style access for JSON fields,
    and token usage details.
    """

    def __init__(
        self,
        content: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        model: str = "",
    ) -> None:
        self.content = content
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.total_tokens = input_tokens + output_tokens
        self.model = model
        self._json_data: dict[str, Any] | None = None
        with contextlib.suppress(Exception):
            self._json_data = json.loads(content)

    @property
    def json(self) -> dict[str, Any] | None:
        """Return parsed JSON dict if the content is valid JSON."""
        return self._json_data

    def __str__(self) -> str:
        return self.content

    def __repr__(self) -> str:
        return (
            f"LLMResponse(content={self.content!r}, "
            f"input_tokens={self.input_tokens}, "
            f"output_tokens={self.output_tokens}, "
            f"model={self.model!r})"
        )

    def __len__(self) -> int:
        return len(self.content)

    def __getitem__(self, index: Any) -> Any:
        return self.content[index]

    def __getattr__(self, name: str) -> Any:
        # Prioritize parsed JSON attributes
        if self._json_data and isinstance(self._json_data, dict) and name in self._json_data:
            return self._json_data[name]
        # Fallback to string attribute delegation
        if hasattr(self.content, name):
            return getattr(self.content, name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")


class LLMClient:
    """Resilient Anthropic Claude client wrapper with caching, sanitization,
    and circuit breaking.
    """

    def __init__(
        self,
        cache: RedisCache | None = None,
        sanitizer: LLMSanitizer | None = None,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        settings = get_settings()
        self.cache = cache
        self.sanitizer = sanitizer or LLMSanitizer()
        self.breaker = breaker or CircuitBreaker(
            dependency="llm",
            failure_threshold=5,
            cooldown_seconds=60.0,
        )

        api_key = (
            settings.anthropic_api_key.get_secret_value()
            if settings.anthropic_api_key
            else "mock-key"
        )
        self.anthropic_client = AsyncAnthropic(
            api_key=api_key,
            timeout=settings.llm_timeout_seconds,
        )

        # Token usage tracking metrics
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.token_usage_by_model: dict[str, dict[str, int]] = {}

    def _track_tokens(self, model: str, input_tokens: int, output_tokens: int) -> None:
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens

        if model not in self.token_usage_by_model:
            self.token_usage_by_model[model] = {"input": 0, "output": 0}
        self.token_usage_by_model[model]["input"] += input_tokens
        self.token_usage_by_model[model]["output"] += output_tokens

    def _get_cache_key(
        self,
        model: str,
        system: str | None,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> str:
        payload = {
            "model": model,
            "system": system,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        serialized = json.dumps(payload, sort_keys=True)
        hash_val = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        return f"llm_cache:{hash_val}"

    def _sanitize_inputs(
        self,
        system: str | None,
        messages: list[dict[str, str]],
    ) -> tuple[str | None, list[dict[str, str]]]:
        sanitized_system = self.sanitizer.sanitize(system) if system else None
        sanitized_messages = []
        for msg in messages:
            sanitized_msg = dict(msg)
            if "content" in sanitized_msg and isinstance(sanitized_msg["content"], str):
                sanitized_msg["content"] = self.sanitizer.sanitize(sanitized_msg["content"])
            sanitized_messages.append(sanitized_msg)
        return sanitized_system, sanitized_messages

    async def invoke(
        self,
        model: str,
        messages: list[dict[str, str]] | str,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
        bypass_cache: bool = False,
    ) -> LLMResponse:
        """Call the LLM with structured input, incorporating sanitization,
        cache check, and circuit breaker.
        """
        settings = get_settings()

        # Resolve model name
        model_info = MODEL_REGISTRY.get(model)
        model_name = model_info["model"] if model_info else MODEL_ALIASES.get(model, model)

        # Standardize messages format
        normalized_messages = (
            [{"role": "user", "content": messages}] if isinstance(messages, str) else messages
        )

        # 1. PII Sanitization
        sanitized_system, sanitized_messages = self._sanitize_inputs(
            system, normalized_messages
        )

        # 2. Cache check
        cache_key = self._get_cache_key(
            model_name,
            sanitized_system,
            sanitized_messages,
            temperature,
            max_tokens,
        )

        if not bypass_cache and self.cache:
            try:
                cached = await self.cache.get(cache_key)
                if cached:
                    try:
                        cached_data = json.loads(cached)
                        content = cached_data.get("content", cached)
                    except Exception:
                        content = cached
                    logger.debug("llm_cache_hit", model=model_name, key=cache_key)
                    return LLMResponse(
                        content=content,
                        input_tokens=0,
                        output_tokens=0,
                        model=model_name,
                    )
            except Exception as e:
                logger.warning("llm_cache_lookup_failed", error=str(e))

        # 3. Call LLM with retries and circuit breaker wrapping
        max_retries = settings.llm_max_retries
        delay = 1.0
        backoff_factor = 2.0

        for attempt in range(max_retries + 1):
            try:
                # API Call wrapped in the circuit breaker
                response = await self.breaker.call(
                    self.anthropic_client.messages.create,
                    model=model_name,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=sanitized_system,
                    messages=sanitized_messages,
                )

                # Extract content text from Anthropic response block(s)
                response_text = ""
                if response.content:
                    # In anthropic-py, response.content is a list of block elements (e.g. TextBlock)
                    response_text = "".join(
                        block.text for block in response.content if hasattr(block, "text")
                    )

                # Track token usage metrics
                input_tokens = getattr(response.usage, "input_tokens", 0)
                output_tokens = getattr(response.usage, "output_tokens", 0)
                self._track_tokens(model_name, input_tokens, output_tokens)

                # 4. Cache storing
                if self.cache:
                    try:
                        cache_payload = json.dumps({"content": response_text})
                        await self.cache.set(cache_key, cache_payload, expire_seconds=86400)
                    except Exception as e:
                        logger.warning("llm_cache_save_failed", error=str(e))

                return LLMResponse(
                    content=response_text,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    model=model_name,
                )

            except CircuitOpenError:
                # Do not retry if circuit is open
                raise
            except (
                anthropic.APITimeoutError,
                anthropic.APIConnectionError,
                anthropic.RateLimitError,
                anthropic.InternalServerError,
                anthropic.OverloadedError,
            ) as e:
                if attempt == max_retries:
                    logger.error(
                        "llm_client_api_failed_all_retries",
                        error=str(e),
                        attempts=attempt + 1,
                    )
                    raise LLMError(f"LLM request failed after {max_retries} retries: {e}") from e

                logger.warning(
                    "llm_client_transient_error_retrying",
                    error=str(e),
                    attempt=attempt + 1,
                    next_delay=delay,
                )
                await asyncio.sleep(delay)
                delay *= backoff_factor
            except anthropic.APIError as e:
                logger.error("llm_client_api_error", error=str(e))
                raise LLMError(f"LLM API error: {e}") from e
            except Exception as e:
                logger.error("llm_client_unexpected_error", error=str(e))
                raise e
