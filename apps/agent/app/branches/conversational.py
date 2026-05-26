"""Rama conversacional / RAG. Recupera docs relevantes de la base de
conocimiento para enriquecer el prompt del LLM con contexto factual.

Equivalente conceptual a la rama de Conversación/RAG de Coren.

No genera respuestas. Solo provee el contexto al Coordinator, que lo
inyecta en el system prompt de la rama transaccional.
"""

from dataclasses import dataclass

from app.rag.store import Doc, retrieve


@dataclass
class RetrievalResult:
    docs: list[Doc]

    def as_context(self) -> str:
        if not self.docs:
            return ""
        parts = ["# Contexto recuperado de la base de conocimiento\n"]
        parts.append(
            "Usa este contexto si responde a la pregunta del cliente, pero NO "
            "lo cites textualmente y NO inventes datos que no estén aquí.\n"
        )
        for d in self.docs:
            parts.append(f"\n## {d.title}\n{d.body.strip()}")
        return "\n".join(parts)


class ConversationalBranch:
    name = "conversational"

    def retrieve(self, query: str, k: int = 3) -> RetrievalResult:
        return RetrievalResult(docs=retrieve(query, k=k))
