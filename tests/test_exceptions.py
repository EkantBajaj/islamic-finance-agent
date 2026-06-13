from app.core.exceptions import CircuitOpenError, PipelineStageError, ResourceNotFoundError


def test_circuit_open_error_is_retryable_and_safe_to_serialize() -> None:
    error = CircuitOpenError("anthropic", retry_after_seconds=12.5)

    assert error.status_code == 503
    assert error.to_dict() == {
        "code": "circuit_open",
        "message": "The dependency circuit breaker is open.",
        "retryable": True,
        "details": {
            "dependency": "anthropic",
            "retry_after_seconds": 12.5,
        },
    }


def test_pipeline_stage_error_records_fallback_state() -> None:
    error = PipelineStageError("categorize", "Categorization failed", fallback_used=True)

    assert error.stage == "categorize"
    assert error.details == {"stage": "categorize", "fallback_used": True}


def test_not_found_error_uses_http_404() -> None:
    assert ResourceNotFoundError().status_code == 404

