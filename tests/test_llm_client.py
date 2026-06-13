from __future__ import annotations

import unittest.mock as mock

import anthropic
import httpx
import pytest
from pydantic import BaseModel

from app.core.circuit_breaker import CircuitBreaker
from app.core.exceptions import CircuitOpenError, LLMError
from app.services.llm_client import LLMClient, LLMResponse


class MockUsage(BaseModel):
    input_tokens: int = 15
    output_tokens: int = 25


class MockTextBlock(BaseModel):
    text: str


class MockMessage(BaseModel):
    content: list[MockTextBlock]
    usage: MockUsage


async def test_llm_client_success() -> None:
    mock_client_inst = mock.MagicMock()
    mock_messages = mock.AsyncMock()
    mock_client_inst.messages = mock_messages

    mock_response = MockMessage(
        content=[MockTextBlock(text="This is a response to [EMAIL_MASKED]")],
        usage=MockUsage(input_tokens=10, output_tokens=20),
    )
    mock_messages.create.return_value = mock_response

    with mock.patch("app.services.llm_client.AsyncAnthropic", return_value=mock_client_inst):
        client = LLMClient()

        # Call invoke with a prompt containing email PII
        resp = await client.invoke(
            model="categorizer",
            messages="Please query contact@example.com for me.",
        )

        # Verify result content
        assert isinstance(resp, LLMResponse)
        assert str(resp) == "This is a response to [EMAIL_MASKED]"
        assert resp.content == "This is a response to [EMAIL_MASKED]"

        # Verify sanitization occurred in the mock call's argument
        mock_messages.create.assert_called_once()
        kwargs = mock_messages.create.call_args[1]
        assert kwargs["model"] == "claude-3-haiku-20240307"
        assert kwargs["messages"] == [
            {"role": "user", "content": "Please query [EMAIL_MASKED] for me."}
        ]

        # Verify token counts were updated
        assert client.total_input_tokens == 10
        assert client.total_output_tokens == 20
        assert client.token_usage_by_model["claude-3-haiku-20240307"] == {"input": 10, "output": 20}


async def test_llm_client_caching() -> None:
    mock_client_inst = mock.MagicMock()
    mock_messages = mock.AsyncMock()
    mock_client_inst.messages = mock_messages

    mock_response = MockMessage(
        content=[MockTextBlock(text="api result")],
        usage=MockUsage(input_tokens=12, output_tokens=18),
    )
    mock_messages.create.return_value = mock_response

    class SimpleCache:
        def __init__(self) -> None:
            self.store: dict[str, str] = {}

        async def get(self, key: str) -> str | None:
            return self.store.get(key)

        async def set(self, key: str, val: str, expire_seconds: int | None = None) -> bool:
            self.store[key] = val
            return True

    cache_inst = SimpleCache()

    with mock.patch("app.services.llm_client.AsyncAnthropic", return_value=mock_client_inst):
        client = LLMClient(cache=cache_inst)  # type: ignore[arg-type]

        # 1st call: Cache miss, calls API
        resp1 = await client.invoke(model="categorizer", messages="hello")
        assert resp1.content == "api result"
        assert mock_messages.create.call_count == 1
        assert client.total_input_tokens == 12
        assert client.total_output_tokens == 18

        # 2nd call: Cache hit, does NOT call API, tokens stay the same
        resp2 = await client.invoke(model="categorizer", messages="hello")
        assert resp2.content == "api result"
        assert mock_messages.create.call_count == 1  # Unchanged
        assert client.total_input_tokens == 12  # Unchanged
        assert client.total_output_tokens == 18  # Unchanged

        # 3rd call with bypass_cache=True: calls API again
        resp3 = await client.invoke(model="categorizer", messages="hello", bypass_cache=True)
        assert resp3.content == "api result"
        assert mock_messages.create.call_count == 2
        assert client.total_input_tokens == 24
        assert client.total_output_tokens == 36


def test_llm_response_json_attribute_access() -> None:
    json_content = '{"category": "transport", "confidence": 0.95, "title": "Taxi"}'
    resp = LLMResponse(
        content=json_content, input_tokens=5, output_tokens=10, model="test-model"
    )

    assert resp.category == "transport"
    assert resp.confidence == 0.95
    assert resp.title == "Taxi"  # Prioritizes JSON key over str.title method
    assert resp.strip() == json_content  # Delegates missing attributes to str
    assert len(resp) == len(json_content)
    assert resp[0] == "{"
    assert resp.json == {"category": "transport", "confidence": 0.95, "title": "Taxi"}

    non_json = "plain text message"
    resp2 = LLMResponse(content=non_json)
    with pytest.raises(AttributeError):
        _ = resp2.some_missing_key
    assert resp2.upper() == "PLAIN TEXT MESSAGE"


async def test_llm_client_retries_on_transient_error() -> None:
    mock_client_inst = mock.MagicMock()
    mock_messages = mock.AsyncMock()
    mock_client_inst.messages = mock_messages

    # First two calls raise transient errors, third succeeds
    mock_req = mock.MagicMock(spec=httpx.Request)
    mock_messages.create.side_effect = [
        anthropic.APITimeoutError(request=mock_req),
        anthropic.APIConnectionError(message="connection failed", request=mock_req),
        MockMessage(
            content=[MockTextBlock(text="recovered")],
            usage=MockUsage(input_tokens=5, output_tokens=5),
        ),
    ]

    with (
        mock.patch("app.services.llm_client.AsyncAnthropic", return_value=mock_client_inst),
        mock.patch("asyncio.sleep", return_value=None) as mock_sleep,
    ):
        client = LLMClient()
        resp = await client.invoke(model="categorizer", messages="test")

        assert resp.content == "recovered"
        assert mock_messages.create.call_count == 3
        mock_sleep.assert_has_calls([mock.call(1.0), mock.call(2.0)])


async def test_llm_client_retries_exhausted() -> None:
    mock_client_inst = mock.MagicMock()
    mock_messages = mock.AsyncMock()
    mock_client_inst.messages = mock_messages
    mock_req = mock.MagicMock(spec=httpx.Request)
    mock_messages.create.side_effect = anthropic.APITimeoutError(request=mock_req)

    with (
        mock.patch("app.services.llm_client.AsyncAnthropic", return_value=mock_client_inst),
        mock.patch("asyncio.sleep", return_value=None),
    ):
        client = LLMClient()
        with pytest.raises(LLMError) as exc_info:
            await client.invoke(model="categorizer", messages="test")

        assert "failed after" in str(exc_info.value)
        # 1 initial call + 3 retries = 4 total calls
        assert mock_messages.create.call_count == 4


async def test_llm_client_non_retryable_error() -> None:
    mock_client_inst = mock.MagicMock()
    mock_messages = mock.AsyncMock()
    mock_client_inst.messages = mock_messages

    # BadRequestError is a non-retryable error
    mock_response = mock.MagicMock()
    mock_response.status_code = 400
    mock_response.headers = {}
    mock_messages.create.side_effect = anthropic.BadRequestError(
        message="Bad Request", response=mock_response, body=None
    )

    with mock.patch("app.services.llm_client.AsyncAnthropic", return_value=mock_client_inst):
        client = LLMClient()
        with pytest.raises(LLMError) as exc_info:
            await client.invoke(model="categorizer", messages="test")

        assert "LLM API error" in str(exc_info.value)
        # Should call only once (no retries)
        assert mock_messages.create.call_count == 1


async def test_llm_client_circuit_breaker() -> None:
    mock_client_inst = mock.MagicMock()
    mock_messages = mock.AsyncMock()
    mock_client_inst.messages = mock_messages

    breaker = CircuitBreaker("llm-test", failure_threshold=2, cooldown_seconds=60.0)
    mock_req = mock.MagicMock(spec=httpx.Request)
    mock_messages.create.side_effect = anthropic.APITimeoutError(request=mock_req)

    with (
        mock.patch("app.services.llm_client.AsyncAnthropic", return_value=mock_client_inst),
        mock.patch("asyncio.sleep", return_value=None),
    ):
        client = LLMClient(breaker=breaker)

        # First invoke fails and trips breaker
        # Inside invoke:
        # 1st call fails (breaker failure count -> 1)
        # 2nd call fails (breaker failure count -> 2, state -> open)
        # 3rd call raises CircuitOpenError
        with pytest.raises(CircuitOpenError):
            await client.invoke(model="categorizer", messages="test")

        assert breaker.state == "open"

        # Subsequent call immediately raises CircuitOpenError without calling messages.create
        mock_messages.create.reset_mock()
        with pytest.raises(CircuitOpenError):
            await client.invoke(model="categorizer", messages="test2")

        mock_messages.create.assert_not_called()
