"""Circuit breaker para llamadas LLM con fallback en cadena.

Inspirado en el patrón de Coren: Gemma4 on-prem → Gemini fallback cuando
hay latencia alta o baja confianza. En RAI: Claude Sonnet 4.6 (primary)
→ Claude Haiku 4.5 (fallback) → HeuristicFallback (degradación total).

Estados:
- CLOSED: trafico normal al primary
- OPEN: primary apartado tras N fallos consecutivos; todo va a fallback
- HALF_OPEN: tras `reset_timeout` se prueba una petición al primary

Reglas:
- timeout por llamada
- fallback automático ante excepción o respuesta con confidence < min_confidence
- reapertura del primary tras cooldown
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from app.adapters.llm.base import LLMClient, LLMResponse


logger = logging.getLogger("rai.circuit_breaker")


class State(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitConfig:
    failure_threshold: int = 3
    reset_timeout_seconds: float = 30.0
    per_call_timeout_seconds: float = 20.0
    min_confidence: float = 0.5


class CircuitBreaker:
    def __init__(
        self,
        primary: LLMClient,
        fallbacks: list[LLMClient],
        config: Optional[CircuitConfig] = None,
    ) -> None:
        self.primary = primary
        self.fallbacks = fallbacks
        self.config = config or CircuitConfig()
        self._state = State.CLOSED
        self._consecutive_failures = 0
        self._opened_at: float | None = None
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cb")

    @property
    def state(self) -> State:
        if self._state == State.OPEN and self._opened_at is not None:
            if time.monotonic() - self._opened_at >= self.config.reset_timeout_seconds:
                self._state = State.HALF_OPEN
                logger.info("Circuit breaker → HALF_OPEN (probando primary)")
        return self._state

    def _record_success(self) -> None:
        if self._state != State.CLOSED:
            logger.info("Circuit breaker → CLOSED (primary recuperado)")
        self._state = State.CLOSED
        self._consecutive_failures = 0
        self._opened_at = None

    def _record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.config.failure_threshold and self._state != State.OPEN:
            self._state = State.OPEN
            self._opened_at = time.monotonic()
            logger.warning(
                "Circuit breaker → OPEN tras %d fallos consecutivos del primary (%s)",
                self._consecutive_failures,
                self.primary.name,
            )

    def _call_with_timeout(self, client: LLMClient, **kwargs) -> LLMResponse:
        future = self._executor.submit(client.complete, **kwargs)
        try:
            return future.result(timeout=self.config.per_call_timeout_seconds)
        except FuturesTimeout:
            future.cancel()
            raise TimeoutError(
                f"{client.name} excedió {self.config.per_call_timeout_seconds}s"
            )

    def complete(
        self,
        *,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        kwargs = {
            "system": system,
            "messages": messages,
            "tools": tools,
            "max_tokens": max_tokens,
        }

        # 1) Primary, salvo que el circuito esté OPEN
        if self.state != State.OPEN:
            try:
                response = self._call_with_timeout(self.primary, **kwargs)
                if response.confidence < self.config.min_confidence:
                    logger.info(
                        "Primary %s devolvió confidence=%.2f < %.2f, intentando fallback",
                        self.primary.name,
                        response.confidence,
                        self.config.min_confidence,
                    )
                else:
                    self._record_success()
                    return response
            except Exception as e:
                logger.warning("Primary %s falló: %s", self.primary.name, e)
                self._record_failure()

        # 2) Cadena de fallbacks
        for fb in self.fallbacks:
            try:
                logger.info("Intentando fallback %s", fb.name)
                return self._call_with_timeout(fb, **kwargs)
            except Exception as e:
                logger.warning("Fallback %s falló: %s", fb.name, e)

        # 3) No debería pasar (la heurística no lanza excepciones), pero por
        # seguridad devolvemos respuesta vacía si todos fallaron.
        return LLMResponse(text="", confidence=0.0)
