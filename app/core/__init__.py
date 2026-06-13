"""Cross-cutting application concerns."""

from app.core.circuit_breaker import CircuitBreaker

__all__ = ["CircuitBreaker"]

