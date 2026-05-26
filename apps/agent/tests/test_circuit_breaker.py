"""Tests del circuit breaker (primary → fallbacks → heurística)."""

import time

import pytest

from app.adapters.llm.base import LLMClient, LLMResponse
from app.adapters.llm.heuristic import HeuristicFallback
from app.circuit_breaker import CircuitBreaker, CircuitConfig, State


class FlakyLLM(LLMClient):
    """LLM stub configurable: lanza N excepciones consecutivas, luego responde OK."""

    def __init__(self, name: str, fail_count: int = 0, raise_exc: Exception | None = None,
                 confidence: float = 1.0, sleep_seconds: float = 0.0):
        self.name = name
        self._fail_count = fail_count
        self._raise = raise_exc or RuntimeError("flaky failure")
        self._confidence = confidence
        self._sleep = sleep_seconds
        self.calls = 0

    def complete(self, *, system, messages, tools=None, max_tokens=1024):
        self.calls += 1
        if self._sleep:
            time.sleep(self._sleep)
        if self._fail_count > 0:
            self._fail_count -= 1
            raise self._raise
        return LLMResponse(
            text=f"OK from {self.name}", confidence=self._confidence, model=self.name
        )


def _kwargs():
    return {"system": "s", "messages": [{"role": "user", "content": "hola"}]}


def test_primary_ok_no_fallback_used():
    primary = FlakyLLM("primary", fail_count=0)
    fb = FlakyLLM("fb", fail_count=0)
    cb = CircuitBreaker(primary=primary, fallbacks=[fb, HeuristicFallback()])
    r = cb.complete(**_kwargs())
    assert "primary" in r.text
    assert fb.calls == 0
    assert cb.state == State.CLOSED


def test_falls_back_on_primary_failure():
    primary = FlakyLLM("primary", fail_count=10)
    fb = FlakyLLM("fb", fail_count=0)
    cb = CircuitBreaker(primary=primary, fallbacks=[fb, HeuristicFallback()])
    r = cb.complete(**_kwargs())
    assert "fb" in r.text
    assert fb.calls == 1


def test_opens_circuit_after_threshold():
    primary = FlakyLLM("primary", fail_count=10)
    fb = FlakyLLM("fb", fail_count=0)
    cb = CircuitBreaker(
        primary=primary,
        fallbacks=[fb, HeuristicFallback()],
        config=CircuitConfig(failure_threshold=2, reset_timeout_seconds=30),
    )
    cb.complete(**_kwargs())
    cb.complete(**_kwargs())
    assert cb.state == State.OPEN
    # Próxima petición ya no toca primary
    primary_calls_before = primary.calls
    cb.complete(**_kwargs())
    assert primary.calls == primary_calls_before  # primary skipped


def test_half_open_after_reset_timeout():
    primary = FlakyLLM("primary", fail_count=10)
    fb = FlakyLLM("fb", fail_count=0)
    cb = CircuitBreaker(
        primary=primary,
        fallbacks=[fb, HeuristicFallback()],
        config=CircuitConfig(failure_threshold=1, reset_timeout_seconds=0.05),
    )
    cb.complete(**_kwargs())
    assert cb.state == State.OPEN
    time.sleep(0.06)
    assert cb.state == State.HALF_OPEN


def test_low_confidence_triggers_fallback():
    primary = FlakyLLM("primary", fail_count=0, confidence=0.1)
    fb = FlakyLLM("fb", fail_count=0, confidence=1.0)
    cb = CircuitBreaker(
        primary=primary,
        fallbacks=[fb, HeuristicFallback()],
        config=CircuitConfig(min_confidence=0.5),
    )
    r = cb.complete(**_kwargs())
    assert "fb" in r.text


def test_timeout_falls_to_next():
    primary = FlakyLLM("primary", fail_count=0, sleep_seconds=0.3)
    fb = FlakyLLM("fb", fail_count=0)
    cb = CircuitBreaker(
        primary=primary,
        fallbacks=[fb, HeuristicFallback()],
        config=CircuitConfig(per_call_timeout_seconds=0.05),
    )
    r = cb.complete(**_kwargs())
    assert "fb" in r.text


def test_heuristic_is_last_resort():
    primary = FlakyLLM("primary", fail_count=10)
    fb1 = FlakyLLM("fb1", fail_count=10)
    cb = CircuitBreaker(primary=primary, fallbacks=[fb1, HeuristicFallback()])
    r = cb.complete(**_kwargs())
    assert "Raidasl" in r.text or "compañero" in r.text  # mensaje degradado
    assert r.confidence == 0.0
