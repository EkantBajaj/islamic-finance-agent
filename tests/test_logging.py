import json

import structlog

from app.config import Environment, LogFormat, Settings
from app.core.logging import configure_logging


def test_json_logging_emits_structured_context(capsys) -> None:
    settings = Settings(
        environment=Environment.TEST,
        log_format=LogFormat.JSON,
        log_level="INFO",
    )
    configure_logging(settings)

    structlog.get_logger().bind(agent_name="categorizer").info(
        "agent_completed",
        transaction_id="txn-1",
        latency_ms=12,
    )

    event = json.loads(capsys.readouterr().err)
    assert event["event"] == "agent_completed"
    assert event["agent_name"] == "categorizer"
    assert event["transaction_id"] == "txn-1"
    assert event["latency_ms"] == 12
    assert event["level"] == "info"
    assert event["timestamp"].endswith("Z")


def test_log_level_filters_debug_events(capsys) -> None:
    configure_logging(Settings(log_format=LogFormat.JSON, log_level="INFO"))

    structlog.get_logger().debug("hidden_event")

    assert capsys.readouterr().err == ""

