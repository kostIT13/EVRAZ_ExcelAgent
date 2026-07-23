from __future__ import annotations
import time
import uuid
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.db.database import async_session_maker
from src.core.db.models import QueryLog
from src.core.logging_settings import logger
from src.services.generation.rag_prompt import build_rag_prompt, format_context
from src.services.generation.verifier import Verifier, VerificationResult
from src.services.llm.llm_client import LLMClient
from src.services.rag.hybrid import HybridSearchResult
from src.services.rag.rag_service import RagService, rag_service
from src.services.agent.orchestrator import AgentOrchestrator, AgentResult


class GenerationResult:
    __slots__ = (
        "answer",
        "retrieved_chunks",
        "verification",
        "latency_ms",
        "request_id",
        "model_used",
    )

    def __init__(
        self,
        answer: str,
        retrieved_chunks: List[HybridSearchResult],
        verification: VerificationResult,
        latency_ms: int,
        request_id: str,
        model_used: str,
    ) -> None:
        self.answer = answer
        self.retrieved_chunks = retrieved_chunks
        self.verification = verification
        self.latency_ms = latency_ms
        self.request_id = request_id
        self.model_used = model_used

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "retrieved_chunks": [r.to_dict() for r in self.retrieved_chunks],
            "verification": self.verification.to_dict(),
            "latency_ms": self.latency_ms,
            "request_id": self.request_id,
            "model_used": self.model_used,
        }


class GenerationPipeline:
    def __init__(
        self,
        rag: Optional[RagService] = None,
        llm: Optional[LLMClient] = None,
        verifier: Optional[Verifier] = None,
        agent: Optional[AgentOrchestrator] = None,
    ) -> None:
        self._rag = rag or rag_service
        self._llm = llm or LLMClient()
        self._verifier = verifier or Verifier()
        self._agent = agent or AgentOrchestrator(llm=self._llm)

    async def run(
        self,
        question: str,
        top_k: int = 10,
        use_cheap_model: bool = False,
        session: Optional[AsyncSession] = None,
    ) -> GenerationResult:
        """Запустить RAG-пайплайн (без агента, как было раньше)."""
        request_id = str(uuid.uuid4())
        start_time = time.monotonic()

        logger.info(
            "Pipeline [{}]: retrieving top_k={} for query '{}'",
            request_id[:8],
            top_k,
            question[:80],
        )
        retrieved: List[HybridSearchResult] = await self._rag.hybrid_search(
            query=question, top_k=top_k
        )
        logger.info(
            "Pipeline [{}]: retrieved {} chunks",
            request_id[:8],
            len(retrieved),
        )

        context = format_context(retrieved)
        messages = build_rag_prompt(question, context)

        logger.info(
            "Pipeline [{}]: calling LLM (cheap={})",
            request_id[:8],
            use_cheap_model,
        )
        try:
            answer = await self._llm.chat(
                messages=messages,
                model=None, 
                temperature=0.1,
                max_tokens=2048,
            )
        except Exception as exc:
            logger.error(
                "Pipeline [{}]: LLM call failed: {}", request_id[:8], exc
            )
            answer = f"Ошибка при генерации ответа: {exc}"

        verification = self._verifier.verify(answer, retrieved)
        logger.info(
            "Pipeline [{}]: verification passed={}, score={:.3f}",
            request_id[:8],
            verification.passed,
            verification.score,
        )

        latency_ms = int((time.monotonic() - start_time) * 1000)
        await self._log_to_db(
            request_id=request_id,
            question=question,
            answer=answer,
            retrieved=retrieved,
            verification=verification,
            latency_ms=latency_ms,
            session=session,
        )

        return GenerationResult(
            answer=answer,
            retrieved_chunks=retrieved,
            verification=verification,
            latency_ms=latency_ms,
            request_id=request_id,
            model_used="primary/cheap", 
        )

    async def run_agent(
        self,
        question: str,
        session: Optional[AsyncSession] = None,
    ) -> AgentResult:
        """Запустить агента (Classifier → Planner → CodeGen → Executor → Verifier).

        Args:
            question: Вопрос пользователя.
            session: Опциональная асинхронная сессия.

        Returns:
            AgentResult с ответом и полным trace.
        """
        logger.info(
            "Pipeline [{}]: running agent for '{}'",
            "agent",
            question[:80],
        )

        result = await self._agent.run(question=question)

        # Логируем в БД
        await self._log_agent_to_db(
            result=result,
            session=session,
        )

        return result

    async def _log_to_db(
        self,
        request_id: str,
        question: str,
        answer: str,
        retrieved: List[HybridSearchResult],
        verification: VerificationResult,
        latency_ms: int,
        session: Optional[AsyncSession],
    ) -> None:
        """Persist query log to the database (RAG mode)."""
        trace = {
            "retrieved_count": len(retrieved),
            "retrieved_scores": [r.score for r in retrieved],
            "verification": verification.to_dict(),
        }

        async with session or async_session_maker() as s:
            log = QueryLog(
                request_id=request_id,
                question=question,
                result={"answer": answer},
                trace=trace,
                latency_ms=latency_ms,
                status="success" if verification.passed else "low_confidence",
            )
            s.add(log)
            await s.commit()

        logger.info(
            "Pipeline [{}]: logged to DB (latency={}ms)",
            request_id[:8],
            latency_ms,
        )

    async def _log_agent_to_db(
        self,
        result: AgentResult,
        session: Optional[AsyncSession],
    ) -> None:
        """Persist agent query log to the database."""
        trace = {
            "agent_trace": result.trace,
            "query_type": result.query_type,
            "sql_query": result.sql_query,
            "sql_result_preview": result.sql_result[:5],
            "retry_count": result.retry_count,
        }

        async with session or async_session_maker() as s:
            log = QueryLog(
                request_id=result.request_id,
                question="",  # вопрос не передаётся в AgentResult, но можно достать из trace
                result={"answer": result.answer},
                trace=trace,
                latency_ms=result.latency_ms,
                status=result.status,
            )
            s.add(log)
            await s.commit()

        logger.info(
            "Pipeline [{}]: agent logged to DB (latency={}ms, status={})",
            result.request_id[:8],
            result.latency_ms,
            result.status,
        )


pipeline: GenerationPipeline = GenerationPipeline()
