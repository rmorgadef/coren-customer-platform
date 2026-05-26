"""Cliente LLM contra Ollama local. Pensado para Gemma4 (o cualquier modelo
con tool calling en Ollama). Esta es la "primary on-prem" del patrón Coren.

Ollama expone API OpenAI-compatible en /v1/chat/completions, y desde v0.4
soporta `tools` para modelos compatibles (Gemma 3+, Llama 3.1+, Qwen 2.5+).

Si Ollama no está corriendo o el modelo no responde dentro del timeout,
levanta excepción y el CircuitBreaker pasa al fallback.
"""

import json
from typing import Any

import httpx

from app.adapters.llm.base import LLMClient, LLMResponse


class OllamaLLM(LLMClient):
    def __init__(
        self,
        *,
        base_url: str = "http://localhost:11434",
        model: str = "gemma3:latest",
        label: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.name = label or f"ollama:{model}"
        self._timeout = timeout

    def complete(
        self,
        *,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        # Ollama acepta el formato OpenAI: {role, content}. Aplanamos los
        # content blocks de Anthropic (tool_use / tool_result) a texto/JSON.
        flat_messages: list[dict] = [{"role": "system", "content": system}]
        for m in messages:
            content = m["content"]
            if isinstance(content, str):
                flat_messages.append({"role": m["role"], "content": content})
            else:
                flat_messages.append(
                    {"role": m["role"], "content": json.dumps(content, ensure_ascii=False, default=str)}
                )

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": flat_messages,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t["description"],
                        "parameters": t["input_schema"],
                    },
                }
                for t in tools
            ]

        with httpx.Client(timeout=self._timeout) as client:
            r = client.post(f"{self.base_url}/api/chat", json=payload)
            r.raise_for_status()
            data = r.json()

        msg = data.get("message", {}) or {}
        text = (msg.get("content") or "").strip()
        tool_calls = msg.get("tool_calls") or []
        tool_uses: list[dict[str, Any]] = []
        for i, tc in enumerate(tool_calls):
            fn = tc.get("function", {}) or {}
            args = fn.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            tool_uses.append({"id": f"ollama_{i}", "name": fn.get("name", ""), "input": args or {}})

        return LLMResponse(
            text=text,
            tool_uses=tool_uses,
            stop_reason="tool_use" if tool_uses else "end_turn",
            raw_blocks=[],  # Ollama no devuelve formato Anthropic; raw_blocks no aplica
            model=self.model,
            confidence=0.9 if text or tool_uses else 0.0,
        )
