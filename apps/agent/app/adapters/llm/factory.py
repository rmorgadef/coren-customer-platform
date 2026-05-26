"""Factoría que monta la cadena Primary → Fallback → Fallback de degradación
según la configuración del entorno.

Patrón Coren: Gemma4 on-prem (Ollama) → modelo cloud económico (Gemini para
Coren, DeepSeek/Claude Haiku para RAI) → degradación heurística.

La selección de cada eslabón es independiente: si no hay Ollama, el primary
puede ser directamente Claude Sonnet. Si no hay DeepSeek, el fallback puede
ser Claude Haiku.
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


def _build_primary() -> LLMClient | None:
    if settings.llm_primary == "ollama":
        try:
            return OllamaLLM(
                base_url=settings.ollama_base_url,
                model=settings.ollama_model,
                label=f"ollama:{settings.ollama_model}",
            )
        except Exception as e:
            logger.warning("No se pudo construir Ollama primary: %s", e)
            return None
    if settings.llm_primary == "anthropic":
        if not settings.anthropic_api_key:
            return None
        return AnthropicLLM(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
            label=f"anthropic:{settings.anthropic_model}",
        )
    if settings.llm_primary == "deepseek":
        if not settings.deepseek_api_key:
            return None
        return OpenAICompatibleLLM(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            label=f"deepseek:{settings.deepseek_model}",
        )
    return None


def _build_fallback_chain() -> list[LLMClient]:
    chain: list[LLMClient] = []
    for kind in settings.llm_fallbacks_csv():
        client: LLMClient | None = None
        if kind == "anthropic" and settings.anthropic_api_key:
            client = AnthropicLLM(
                api_key=settings.anthropic_api_key,
                model=settings.anthropic_fallback_model,
                label=f"anthropic:{settings.anthropic_fallback_model}",
            )
        elif kind == "deepseek" and settings.deepseek_api_key:
            client = OpenAICompatibleLLM(
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
                model=settings.deepseek_model,
                label=f"deepseek:{settings.deepseek_model}",
            )
        elif kind == "ollama":
            client = OllamaLLM(
                base_url=settings.ollama_base_url,
                model=settings.ollama_model,
                label=f"ollama:{settings.ollama_model}",
            )
        if client:
            chain.append(client)
    # Última línea siempre la heurística determinista
    chain.append(HeuristicFallback())
    return chain


def build_circuit_breaker() -> CircuitBreaker:
    primary = _build_primary()
    fallbacks = _build_fallback_chain()

    if primary is None:
        # Si no hay primary configurable, el primer fallback asciende a primary.
        # Con esto la app sigue arrancando aunque solo haya configurada una API.
        if not fallbacks or isinstance(fallbacks[0], HeuristicFallback):
            raise RuntimeError(
                "No hay ningún LLM configurable (ni primary ni fallback). "
                "Configura ANTHROPIC_API_KEY, DEEPSEEK_API_KEY u Ollama."
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
