from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.core.circuit_breaker import CircuitBreaker
from app.core.exceptions import CircuitOpenError


async def test_cb_starts_closed() -> None:
    cb = CircuitBreaker("test-service", failure_threshold=2, cooldown_seconds=0.1)
    assert cb.state == "closed"
    assert cb.failures == 0
    assert cb.last_failure_time is None


async def test_cb_successful_call_returns_value_and_remains_closed() -> None:
    cb = CircuitBreaker("test-service", failure_threshold=2, cooldown_seconds=0.1)

    async def sample_func() -> str:
        return "success"

    result = await cb.call(sample_func)
    assert result == "success"
    assert cb.state == "closed"
    assert cb.failures == 0


async def test_cb_failures_increment_failures_and_threshold_opens_circuit() -> None:
    cb = CircuitBreaker("test-service", failure_threshold=2, cooldown_seconds=0.1)

    async def fail_func() -> None:
        raise ValueError("failing")

    # First failure
    with pytest.raises(ValueError, match="failing"):
        await cb.call(fail_func)
    assert cb.failures == 1
    assert cb.state == "closed"

    # Second failure - threshold reached
    with pytest.raises(ValueError, match="failing"):
        await cb.call(fail_func)
    assert cb.failures == 2
    assert cb.state == "open"
    assert cb.last_failure_time is not None

    # Call while open raises CircuitOpenError without calling inner function
    called = False

    async def another_func() -> str:
        nonlocal called
        called = True
        return "yes"

    with pytest.raises(CircuitOpenError) as exc_info:
        await cb.call(another_func)

    assert not called
    assert exc_info.value.details["dependency"] == "test-service"
    assert exc_info.value.details["retry_after_seconds"] > 0.0


async def test_cb_cooldown_expiry_transitions_to_half_open_and_probe_success_closes() -> None:
    cb = CircuitBreaker("test-service", failure_threshold=2, cooldown_seconds=0.05)

    async def fail_func() -> None:
        raise ValueError("failing")

    # Open the circuit
    with pytest.raises(ValueError):
        await cb.call(fail_func)
    with pytest.raises(ValueError):
        await cb.call(fail_func)
    assert cb.state == "open"

    # Wait for cooldown to expire
    await asyncio.sleep(0.06)

    # First call after cooldown should probe (half_open)
    probe_called = False

    async def success_func() -> str:
        nonlocal probe_called
        probe_called = True
        return "recovered"

    result = await cb.call(success_func)
    assert result == "recovered"
    assert probe_called
    assert cb.state == "closed"
    assert cb.failures == 0


async def test_cb_failed_probe_reopens_circuit_and_restarts_cooldown() -> None:
    cb = CircuitBreaker("test-service", failure_threshold=2, cooldown_seconds=0.05)

    async def fail_func() -> None:
        raise ValueError("failing")

    # Open the circuit
    with pytest.raises(ValueError):
        await cb.call(fail_func)
    with pytest.raises(ValueError):
        await cb.call(fail_func)
    assert cb.state == "open"

    # Wait for cooldown to expire
    await asyncio.sleep(0.06)

    # Failed probe should immediately reopen
    with pytest.raises(ValueError, match="failing"):
        await cb.call(fail_func)

    assert cb.state == "open"
    assert cb.failures == 3  # increments failures


async def test_cb_success_before_threshold_resets_failures() -> None:
    cb = CircuitBreaker("test-service", failure_threshold=2, cooldown_seconds=0.1)

    async def fail_func() -> None:
        raise ValueError("failing")

    async def success_func() -> str:
        return "ok"

    # Fail once
    with pytest.raises(ValueError):
        await cb.call(fail_func)
    assert cb.failures == 1

    # Succeed once
    result = await cb.call(success_func)
    assert result == "ok"
    assert cb.failures == 0
    assert cb.state == "closed"


async def test_cb_cancellation_does_not_increment_failures() -> None:
    cb = CircuitBreaker("test-service", failure_threshold=2, cooldown_seconds=0.1)

    async def cancel_func() -> None:
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await cb.call(cancel_func)

    assert cb.failures == 0
    assert cb.state == "closed"


async def test_cb_concurrent_calls_do_not_allow_multiple_half_open_probes() -> None:
    cb = CircuitBreaker("test-service", failure_threshold=2, cooldown_seconds=0.05)

    async def fail_func() -> None:
        raise ValueError("failing")

    # Open the circuit
    with pytest.raises(ValueError):
        await cb.call(fail_func)
    with pytest.raises(ValueError):
        await cb.call(fail_func)
    assert cb.state == "open"

    # Wait for cooldown to expire
    await asyncio.sleep(0.06)

    # Launch two concurrent calls:
    # 1. The first one should act as a probe (enters half_open, sleeps, then succeeds/fails).
    # 2. The second one should immediately see that a probe is in progress and raise
    #    CircuitOpenError.
    probe_started = asyncio.Event()
    probe_complete = asyncio.Event()

    async def slow_probe_func() -> str:
        probe_started.set()
        await probe_complete.wait()
        return "done"

    async def call_probe() -> Any:
        return await cb.call(slow_probe_func)

    async def call_second() -> Any:
        # Wait until the probe is inside call()
        await probe_started.wait()
        return await cb.call(slow_probe_func)

    # Run them concurrently
    probe_task = asyncio.create_task(call_probe())
    second_task = asyncio.create_task(call_second())

    # Wait for second call to raise error or finish
    with pytest.raises(CircuitOpenError):
        await second_task

    # Complete the probe call
    probe_complete.set()
    res = await probe_task
    assert res == "done"
    assert cb.state == "closed"
    assert cb.failures == 0
