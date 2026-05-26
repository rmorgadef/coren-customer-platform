"""Cliente LLM contra Claude (API). Se usa para primary (Sonnet 4.6) y para
fallback (Haiku 4.5). El modelo concreto se pasa en el constructor."""

from typing import Optional

from anthropic import Anthropic

from app.adapters.llm.base import LLMClient, LLMResponse


class AnthropicLLM(LLMClient):
    def __init__(self, *, api_key: str, model: str, label: str | None = None) -> None:
        if not api_key:
            raise ValueError("AnthropicLLM requiere ANTHROPIC_API_KEY")
        self._client = Anthropic(api_key=api_key)
        self.model = model
        self.name = label or f"anthropic:{model}"

    def complete(
        self,
        *,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        response = self._client.messages.create(**kwargs)

        text_parts = [b.text for b in response.content if b.type == "text"]
        tool_uses = [
            {"id": b.id, "name": b.name, "input": b.input}
            for b in response.content
            if b.type == "tool_use"
        ]
        raw_blocks = [b.model_dump() for b in response.content]

        return LLMResponse(
            text="\n".join(text_parts).strip(),
            tool_uses=tool_uses,
            stop_reason=response.stop_reason or "end_turn",
            raw_blocks=raw_blocks,
            model=self.model,
            confidence=1.0,
        )
