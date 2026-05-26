"""Coordinator central. Orquesta las 3 ramas en paralelo según el patrón
de Coren (Inditex 3-branch model):

  ┌──────────────┐    ┌──────────────────┐    ┌────────────────────┐
  │  Seguridad   │    │ Conversación/RAG │    │   Transaccional    │
  │  (rápida,    │ ║  │  (BM25 sobre KB) │ ║  │ (LLM + tools sobre │
  │  sin LLM)    │ ║  │                  │ ║  │  CRM/pricing)      │
  └──────┬───────┘ ║  └────────┬─────────┘ ║  └─────────┬──────────┘
         │         ║           │           ║            │
         └─────────╨───────────┴───────────╨────────────┘
                            Coordinator

Security y RAG arrancan EN PARALELO (concurrent.futures). Cuando los dos
terminan, el Coordinator decide:
  - Si Security devuelve BLOCK_AND_ESCALATE → corta y escala sin LLM.
  - Si Security devuelve FLAG_FOR_HUMAN → ejecuta Transactional pidiéndole
    que escale con la razón correspondiente.
  - Si Security devuelve PASS → ejecuta Transactional con el contexto RAG
    inyectado en el system prompt.

La rama Transaccional es la única que paga LLM. Las otras dos son baratas
y se ejecutan siempre, manteniendo la latencia total ≈ latencia del LLM
(las branches preparatorias se solapan con la red al LLM).
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from app import db
from app.branches.conversational import ConversationalBranch, RetrievalResult
from app.branches.security import SecurityAction, SecurityBranch, SecurityVerdict
from app.branches.transactional import TransactionalBranch, TransactionalResult
from app.config import settings
from app.handoff import notify_installer
from app.prompts import SYSTEM_PROMPT


logger = logging.getLogger("rai.coordinator")


@dataclass
class CoordinationOutcome:
    reply_text: str
    security: SecurityVerdict
    retrieval: RetrievalResult
    transactional: TransactionalResult | None
    model_used: str


class Coordinator:
    def __init__(
        self,
        security: SecurityBranch,
        conversational: ConversationalBranch,
        transactional: TransactionalBranch,
    ) -> None:
        self.security = security
        self.conversational = conversational
        self.transactional = transactional
        self._executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="branch")

    def _build_system_prompt(
        self, retrieval: RetrievalResult, returning_context: str | None, security_flag: str | None
    ) -> str:
        prompt = SYSTEM_PROMPT.replace("{privacy_policy_url}", settings.privacy_policy_url)
        if returning_context:
            prompt += f"\n\n# Contexto de cliente recurrente\n{returning_context}\n"
        if security_flag:
            prompt += (
                f"\n\n# Aviso de seguridad\n"
                f"La rama de seguridad ha marcado este mensaje como '{security_flag}'. "
                "Cuando termines la respuesta cordial, escala con `escalate_to_human` "
                "indicando el motivo correspondiente.\n"
            )
        rag_context = retrieval.as_context()
        if rag_context:
            prompt += f"\n\n{rag_context}\n"
        return prompt

    def handle(
        self,
        *,
        lead_id: int,
        phone: str,
        user_text: str,
        history: list[dict],
        returning_context: str | None = None,
    ) -> CoordinationOutcome:
        # 1) Seguridad + RAG en paralelo
        sec_future = self._executor.submit(self.security.check, user_text)
        rag_future = self._executor.submit(self.conversational.retrieve, user_text, 3)
        security: SecurityVerdict = sec_future.result(timeout=2.0)
        retrieval: RetrievalResult = rag_future.result(timeout=2.0)

        logger.info(
            "Coordinator branches done: security=%s flags=%s rag_docs=%d",
            security.action,
            security.detected_flags,
            len(retrieval.docs),
        )

        # 2) Si la seguridad bloquea, corta sin pagar LLM
        if security.action == SecurityAction.BLOCK_AND_ESCALATE:
            reason = security.reason or "bloqueo_seguridad"
            db.escalate_lead(lead_id, f"seguridad: {reason}")
            answers = db.get_lead_answers(lead_id)
            leads = [l for l in db.list_leads() if l["id"] == lead_id]
            lead = leads[0] if leads else {}
            transcript = "\n".join(
                f"{m['role']}: {m['content']}" for m in db.get_messages(lead_id)[-10:]
            )
            notify_installer(
                lead_id=lead_id,
                phone=phone,
                name=lead.get("name"),
                email=lead.get("email"),
                reason=f"bloqueo_seguridad: {reason}",
                answers=answers,
                quote=None,
                transcript_excerpt=transcript,
            )
            return CoordinationOutcome(
                reply_text=(
                    "Te paso ya con un compañero del equipo de Raidasl para que pueda "
                    "ayudarte mejor. Gracias por tu paciencia."
                ),
                security=security,
                retrieval=retrieval,
                transactional=None,
                model_used="security_branch",
            )

        # 3) Construye system prompt con RAG y, si procede, aviso de seguridad
        security_flag = security.reason if security.action == SecurityAction.FLAG_FOR_HUMAN else None
        system_prompt = self._build_system_prompt(retrieval, returning_context, security_flag)

        # 4) Rama transaccional (con LLM + tools, vía circuit breaker)
        result = self.transactional.run(
            system_prompt=system_prompt,
            history=history,
            lead_id=lead_id,
            phone=phone,
        )

        return CoordinationOutcome(
            reply_text=result.text or "Disculpa, no te he entendido bien. ¿Me lo puedes repetir?",
            security=security,
            retrieval=retrieval,
            transactional=result,
            model_used=result.last_model,
        )
