from __future__ import annotations
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.db.database import async_session_maker
from src.core.db.models import QueryLog
from src.core.logging_settings import logger
from src.services.llm.llm_client import LLMClient
from src.services.agent.graph import (
    LangGraphAgent,
    AgentResult,
    STATUS_WAITING,
)


class GenerationPipeline:
    def __init__(
        self,
        llm: Optional[LLMClient] = None,
        agent: Optional[LangGraphAgent] = None,
    ) -> None:
        self._llm = llm or LLMClient()
        self._agent = agent or LangGraphAgent(llm=self._llm)

    async def run_agent(
        self,
        question: str,
        top_k: int = 30,
        session: Optional[AsyncSession] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        conversation_id: Optional[str] = None,
        response_mode: str = "detailed",
    ) -> AgentResult:
        is_retry = bool(conversation_history)
        logger.info(
            "Pipeline [{}]: running agent for '{}' (retry={})",
            "agent",
            question[:80],
            is_retry,
        )

        result = await self._agent.run(
            question=question,
            top_k=top_k,
            conversation_history=conversation_history,
            conversation_id=conversation_id,
            response_mode=response_mode,
        )

        # waiting_for_input — граф приостановлен на уточняющем вопросе,
        # self-correction не запускаем.
        needs_correction = (
            result.status not in (STATUS_WAITING,)
            and (
                result.status in ("failed", "low_confidence")
                or result.confidence < 0.5
                or not result.answer
                or (len(result.answer) < 20 and response_mode != "concise")
            )
        )

        if needs_correction and not is_retry:
            logger.info(
                "Pipeline [{}]: self-correction triggered (status={}, confidence={:.2f}). "
                "Retrying with previous attempt context...",
                result.request_id[:8],
                result.status,
                result.confidence,
            )

            correction_history = [
                {"role": "user", "content": question},
                {"role": "assistant", "content": result.answer or "Не удалось получить ответ"},
            ]

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

            result = await self._agent.run(
                question=question,
                top_k=top_k,
                conversation_history=correction_history,
                conversation_id=conversation_id,
                response_mode=response_mode,
            )
            result.self_corrected = True

            logger.info(
                "Pipeline [{}]: self-correction completed (status={}, confidence={:.2f})",
                result.request_id[:8],
                result.status,
                result.confidence,
            )

        await self._log_agent_to_db(
            result=result,
            session=session,
        )

        return result

    async def resume_agent(
        self,
        thread_id: str,
        user_answer: str,
        session: Optional[AsyncSession] = None,
        response_mode: str = "detailed",
    ) -> AgentResult:
        """Продолжает прерванный на уточняющем вопросе запуск агента."""
        logger.info(
            "Pipeline: resuming agent thread={} with answer",
            thread_id[:8],
        )
        result = await self._agent.resume(
            thread_id=thread_id,
            user_answer=user_answer,
            response_mode=response_mode,
        )

        await self._log_agent_to_db(
            result=result,
            session=session,
        )
        return result

    async def _log_agent_to_db(
        self,
        result: AgentResult,
        session: Optional[AsyncSession],
    ) -> None:
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
