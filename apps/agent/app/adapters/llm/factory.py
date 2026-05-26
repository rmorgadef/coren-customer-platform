"""Factoría que monta la cadena Primary → Fallback → Fallback de degradación
según la configuración del entorno.

Patrón Coren: Gemma4 on-prem (Ollama) → modelo cloud económico (Gemini para
Coren, Mistral en Scaleway o DeepSeek/Claude Haiku para RAI) → heurística.

Cuando un mismo proveedor (ej. `scaleway` o `anthropic`) aparece como primary
Y como fallback, se usa automáticamente el modelo grande como primary y el
económico como fallback en la posición primary, o al revés en fallback. Esto
permite construir cadenas tipo "Mistral Small → Mistral Medium" o
"Sonnet → Haiku" con dos eslabones del mismo proveedor.
"""

import logging

from app.adapters.llm.anthropic_client import AnthropicLLM
from app.adapters.llm.base import LLMClient
from app.adapters.llm.heuristic import HeuristicFallback
from app.adapters.llm.ollama_client import OllamaLLM
from app.adapters.llm.openai_compatible import OpenAICompatibleLLM
from app.circuit_breaker import CircuitBreaker, CircuitConfig
from app.config import settings


logger = logging.getLogger("rai.llm.factory")


def _build_client(kind: str, *, position: str) -> LLMClient | None:
    """Construye un LLMClient para el proveedor `kind`.

    `position` es "primary" o "fallback" y determina qué modelo de la familia
    se usa cuando el proveedor distingue (ej. Mistral Small vs Medium en
    Scaleway, Sonnet vs Haiku en Anthropic).
    """
    if kind == "scaleway":
        if not settings.scaleway_api_key:
            return None
        model = settings.scaleway_model if position == "primary" else settings.scaleway_fallback_model
        return OpenAICompatibleLLM(
            api_key=settings.scaleway_api_key,
            base_url=settings.scaleway_base_url,
            model=model,
            label=f"scaleway:{model}",
        )

    if kind == "anthropic":
        if not settings.anthropic_api_key:
            return None
        model = settings.anthropic_model if position == "primary" else settings.anthropic_fallback_model
        return AnthropicLLM(
            api_key=settings.anthropic_api_key,
            model=model,
            label=f"anthropic:{model}",
        )

    if kind == "deepseek":
        if not settings.deepseek_api_key:
            return None
        return OpenAICompatibleLLM(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            label=f"deepseek:{settings.deepseek_model}",
        )

    if kind == "ollama":
        try:
            return OllamaLLM(
                base_url=settings.ollama_base_url,
                model=settings.ollama_model,
                label=f"ollama:{settings.ollama_model}",
            )
        except Exception as e:
            logger.warning("No se pudo construir Ollama: %s", e)
            return None

    return None


def _build_fallback_chain() -> list[LLMClient]:
    chain: list[LLMClient] = []
    for kind in settings.llm_fallbacks_csv():
        if client := _build_client(kind, position="fallback"):
            chain.append(client)
    chain.append(HeuristicFallback())
    return chain


def build_circuit_breaker() -> CircuitBreaker:
    primary = _build_client(settings.llm_primary, position="primary")
    fallbacks = _build_fallback_chain()

    if primary is None:
        if not fallbacks or isinstance(fallbacks[0], HeuristicFallback):
            raise RuntimeError(
                "No hay ningún LLM configurable. Define al menos uno: "
                "SCALEWAY_API_KEY, ANTHROPIC_API_KEY, DEEPSEEK_API_KEY u Ollama."
            )
        primary = fallbacks.pop(0)
        logger.info("Primary asciendido desde fallback: %s", primary.name)

    config = CircuitConfig(
        failure_threshold=settings.circuit_failure_threshold,
        reset_timeout_seconds=settings.circuit_reset_seconds,
        per_call_timeout_seconds=settings.circuit_per_call_timeout_seconds,
        min_confidence=settings.circuit_min_confidence,
    )

    logger.info(
        "Circuit breaker construido: primary=%s, fallbacks=%s",
        primary.name,
        [c.name for c in fallbacks],
    )
    return CircuitBreaker(primary=primary, fallbacks=fallbacks, config=config)
