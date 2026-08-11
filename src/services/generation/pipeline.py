from __future__ import annotations
import time
import uuid
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.db.database import async_session_maker
from src.core.db.models import QueryLog
from src.core.logging_settings import logger
from src.services.generation.verifier import Verifier, VerificationResult
from src.services.llm.llm_client import LLMClient
from src.services.agent.graph import LangGraphAgent, AgentResult

# RAG-импорты (HybridSearchResult, RagService) удалены — RAG-over-cells больше нет.
# GenerationResult оставлен только для обратной совместимости; основной путь —
# run_agent() через LangGraph.


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
        retrieved_chunks: Optional[List[Any]],
        verification: VerificationResult,
        latency_ms: int,
        request_id: str,
        model_used: str,
    ) -> None:
        self.answer = answer
        self.retrieved_chunks = retrieved_chunks or []
        self.verification = verification
        self.latency_ms = latency_ms
        self.request_id = request_id
        self.model_used = model_used

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "retrieved_chunks": [
                getattr(r, "to_dict", lambda: str(r))() for r in self.retrieved_chunks
            ],
            "verification": self.verification.to_dict(),
            "latency_ms": self.latency_ms,
            "request_id": self.request_id,
            "model_used": self.model_used,
        }


class GenerationPipeline:
    def __init__(
        self,
        llm: Optional[LLMClient] = None,
        verifier: Optional[Verifier] = None,
        agent: Optional[LangGraphAgent] = None,
    ) -> None:
        self._llm = llm or LLMClient()
        self._verifier = verifier or Verifier()
        self._agent = agent or LangGraphAgent(llm=self._llm)

    async def run(
        self,
        question: str,
        top_k: int = 10,
        use_cheap_model: bool = False,
        session: Optional[AsyncSession] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> GenerationResult:
        """DEPRECATED: RAG-пайплайн удалён. Делегирует в run_agent (entity-resolution)."""
        result = await self.run_agent(
            question=question,
            top_k=top_k,
            session=session,
            conversation_history=conversation_history,
        )
        return GenerationResult(
            answer=result.answer,
            retrieved_chunks=[],
            verification=VerificationResult(passed=True, score=result.confidence),
            latency_ms=result.latency_ms,
            request_id=result.request_id,
            model_used="primary",
        )

    async def run_agent(
        self,
        question: str,
        top_k: int = 30,
        session: Optional[AsyncSession] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> AgentResult:
        """Запустить агента (Classifier → Planner → CodeGen → Executor → Verifier)
        с автоматическим Self-Correction при низком качестве ответа.

        Если после первого прохода confidence < 0.5 или статус failed/low_confidence,
        агент автоматически делает второй проход с контекстом предыдущей ошибки.

        Args:
            question: Вопрос пользователя.
            top_k: Количество чанков для RAG-поиска.
            session: Опциональная асинхронная сессия.
            conversation_history: История предыдущих попыток для self-correction.

        Returns:
            AgentResult с ответом и полным trace.
        """
        is_retry = bool(conversation_history)
        logger.info(
            "Pipeline [{}]: running agent for '{}' (retry={})",
            "agent",
            question[:80],
            is_retry,
        )

        # --- Первый проход ---
        result = await self._agent.run(
            question=question,
            top_k=top_k,
            conversation_history=conversation_history,
        )

        # --- Self-Correction: если ответ низкого качества, пробуем ещё раз ---
        needs_correction = (
            result.status in ("failed", "low_confidence")
            or result.confidence < 0.5
            or not result.answer
            or len(result.answer) < 20
        )

        if needs_correction and not is_retry:
            logger.info(
                "Pipeline [{}]: self-correction triggered (status={}, confidence={:.2f}). "
                "Retrying with previous attempt context...",
                result.request_id[:8],
                result.status,
                result.confidence,
            )

            # Формируем историю из предыдущей попытки
            correction_history = [
                {"role": "user", "content": question},
                {"role": "assistant", "content": result.answer or "Не удалось получить ответ"},
            ]

            # Добавляем информацию об ошибке, если есть
            if result.trace:
                error_details = []
                for step_name in ["rag", "classifier", "planner", "codegen", "executor", "verifier"]:
                    step_data = result.trace.get(step_name, {})
                    if isinstance(step_data, dict):
                        err = step_data.get("error") or step_data.get("sql_error")
                        if err:
                            error_details.append(f"{step_name}: {err}")
                if error_details:
                    correction_history.append({
                        "role": "assistant",
                        "content": f"Ошибки при выполнении: {'; '.join(error_details)}",
                    })

            # Второй проход с историей
            result = await self._agent.run(
                question=question,
                top_k=top_k,
                conversation_history=correction_history,
            )
            result.self_corrected = True

            logger.info(
                "Pipeline [{}]: self-correction completed (status={}, confidence={:.2f})",
                result.request_id[:8],
                result.status,
                result.confidence,
            )

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
        retrieved: List[Any],
        verification: VerificationResult,
        latency_ms: int,
        session: Optional[AsyncSession],
    ) -> None:
        """Persist query log to the database (RAG mode, legacy)."""
        trace = {
            "retrieved_count": len(retrieved),
            "retrieved_scores": [getattr(r, "score", 0.0) for r in retrieved],
            "verification": verification.to_dict(),
        }

        async with session or async_session_maker() as s:
            s.add(QueryLog(
                request_id=request_id,
                question=question,
                result={"answer": answer},
                trace=trace,
                latency_ms=latency_ms,
                status="success" if verification.passed else "low_confidence",
            ))
            await s.commit()

        logger.info("Pipeline [{}]: logged to DB (latency={}ms)", request_id[:8], latency_ms)

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
            s.add(QueryLog(
                request_id=result.request_id,
                question=result.question,
                result={"answer": result.answer},
                trace=trace,
                latency_ms=result.latency_ms,
                status=result.status,
            ))
            await s.commit()

        logger.info(
            "Pipeline [{}]: agent logged to DB (latency={}ms, status={})",
            result.request_id[:8],
            result.latency_ms,
            result.status,
        )


pipeline: GenerationPipeline = GenerationPipeline()
