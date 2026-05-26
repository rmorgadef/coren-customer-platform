"""Cliente LLM contra cualquier API OpenAI-compatible.

Uso típico: DeepSeek (https://api.deepseek.com), Together, Groq, etc. Apunta
al endpoint correcto con `base_url` y pon el `api_key` del proveedor.

DeepSeek v3.x acepta `tools` con la misma forma que OpenAI. Para DeepSeek
"Flash" o variantes específicas, pasa el slug del modelo (ej.
"deepseek-chat", "deepseek-v3-flash") en el parámetro `model`.

Si el modelo concreto no soporta tool calling, las tools se pasarán igual
pero el modelo simplemente no las invocará → la rama transaccional acabará
sin tool_uses y RAI dará respuesta conversacional pura.
"""

import json
from typing import Any

import httpx

from app.adapters.llm.base import LLMClient, LLMResponse


class OpenAICompatibleLLM(LLMClient):
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        label: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        if not api_key:
            raise ValueError(f"{base_url} requiere api_key")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.name = label or f"openai-compat:{model}"
        self._timeout = timeout

    def complete(
        self,
        *,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 1024,
    ) -> LLMResponse:
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
            "max_tokens": max_tokens,
            "stream": False,
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

        headers = {"Authorization": f"Bearer {self.api_key}"}

        with httpx.Client(timeout=self._timeout) as client:
            r = client.post(
                f"{self.base_url}/chat/completions", json=payload, headers=headers
            )
            r.raise_for_status()
            data = r.json()

        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message", {}) or {}
        text = (msg.get("content") or "").strip()
        tool_calls = msg.get("tool_calls") or []
        tool_uses: list[dict[str, Any]] = []
        for tc in tool_calls:
            fn = tc.get("function", {}) or {}
            args = fn.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            tool_uses.append({"id": tc.get("id", ""), "name": fn.get("name", ""), "input": args or {}})

        finish = choice.get("finish_reason", "stop")
        stop_reason = "tool_use" if tool_uses else ("end_turn" if finish == "stop" else finish)

        return LLMResponse(
            text=text,
            tool_uses=tool_uses,
            stop_reason=stop_reason,
            raw_blocks=[],
            model=self.model,
            confidence=0.9 if text or tool_uses else 0.0,
        )
