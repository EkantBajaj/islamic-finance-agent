from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

from app.core.exceptions import CircuitOpenError
from app.core.logging import get_logger

logger = get_logger()

T = TypeVar("T")


class CircuitBreaker:
    """An asynchronous circuit breaker for wrapping external dependency calls."""

    def __init__(
        self,
        dependency: str,
        failure_threshold: int = 5,
        cooldown_seconds: float = 60.0,
    ) -> None:
        self.dependency = dependency
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds

        self.state = "closed"  # "closed", "open", "half_open"
        self.failures = 0
        self.last_failure_time: float | None = None
        self._probe_in_progress = False
        self._lock = asyncio.Lock()

    async def call(
        self,
        func: Callable[..., Coroutine[Any, Any, T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Execute the async callable wrapped by the circuit breaker logic."""
        async with self._lock:
            now = time.monotonic()

            if self.state == "open":
                if self.last_failure_time is not None and (
                    now - self.last_failure_time >= self.cooldown_seconds
                ):
                    old_state = self.state
                    self.state = "half_open"
                    self._probe_in_progress = True
                    logger.info(
                        "circuit_breaker_state_transition",
                        dependency=self.dependency,
                        old_state=old_state,
                        new_state=self.state,
                        reason="cooldown_expired",
                        consecutive_failures=self.failures,
                    )
                else:
                    retry_after = (
                        (self.last_failure_time + self.cooldown_seconds) - now
                        if self.last_failure_time
                        else self.cooldown_seconds
                    )
                    raise CircuitOpenError(
                        self.dependency,
                        retry_after_seconds=max(0.0, retry_after),
                    )

            elif self.state == "half_open":
                if self._probe_in_progress:
                    raise CircuitOpenError(self.dependency)
                else:
                    self._probe_in_progress = True

        try:
            result = await func(*args, **kwargs)
        except asyncio.CancelledError:
            async with self._lock:
                # If a probe is cancelled, reset probe in progress so another check can occur
                if self.state == "half_open" and self._probe_in_progress:
                    self._probe_in_progress = False
            raise
        except Exception as e:
            async with self._lock:
                self.failures += 1
                self.last_failure_time = time.monotonic()

                if self.state == "half_open":
                    old_state = self.state
                    self.state = "open"
                    self._probe_in_progress = False
                    logger.warning(
                        "circuit_breaker_state_transition",
                        dependency=self.dependency,
                        old_state=old_state,
                        new_state=self.state,
                        reason="probe_failed",
                        consecutive_failures=self.failures,
                    )
                elif self.state == "closed":
                    if self.failures >= self.failure_threshold:
                        old_state = self.state
                        self.state = "open"
                        logger.warning(
                            "circuit_breaker_state_transition",
                            dependency=self.dependency,
                            old_state=old_state,
                            new_state=self.state,
                            reason="failure_threshold_reached",
                            consecutive_failures=self.failures,
                        )
            raise e
        else:
            async with self._lock:
                if self.state == "half_open":
                    old_state = self.state
                    self.state = "closed"
                    self.failures = 0
                    self._probe_in_progress = False
                    logger.info(
                        "circuit_breaker_state_transition",
                        dependency=self.dependency,
                        old_state=old_state,
                        new_state=self.state,
                        reason="probe_succeeded",
                        consecutive_failures=self.failures,
                    )
                elif self.state == "closed":
                    self.failures = 0
            return result
