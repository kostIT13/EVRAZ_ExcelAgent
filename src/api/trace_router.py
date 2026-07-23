"""
API router for traceability endpoint.
Позволяет посмотреть полный "след" запроса: вопрос → план → SQL → результат.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from src.api.schemas import TraceResponse, TraceStepInfo
from src.core.db.database import async_session_maker
from src.core.db.models import QueryLog
from src.core.logging_settings import logger

router = APIRouter(prefix="/trace", tags=["traceability"])


@router.get("/{request_id}", response_model=TraceResponse)
async def get_trace(request_id: str) -> TraceResponse:
    """Получить полный trace запроса по request_id."""
    logger.info("Trace request: request_id='{}'", request_id)

    async with async_session_maker() as session:
        result = await session.execute(
            select(QueryLog).where(QueryLog.request_id == request_id)
        )
        log = result.scalar_one_or_none()

        if not log:
            raise HTTPException(
                status_code=404,
                detail=f"Trace not found for request_id: {request_id}",
            )

        trace_data = log.trace or {}
        result_data = log.result or {}

        steps = []

        # Шаг 1: вопрос
        steps.append(TraceStepInfo(
            step="question",
            data={"question": log.question},
        ))

        # Шаги агента (если это был agent-запрос)
        agent_trace = trace_data.get("agent_trace", {})
        if agent_trace:
            for step_name in ["classifier", "planner", "codegen", "executor", "verifier"]:
                step_data = agent_trace.get(step_name)
                if step_data:
                    steps.append(TraceStepInfo(step=step_name, data=step_data))
        else:
            # Если это был RAG-запрос
            steps.append(TraceStepInfo(
                step="retrieval",
                data={
                    "retrieved_count": trace_data.get("retrieved_count", 0),
                    "retrieved_scores": trace_data.get("retrieved_scores", []),
                },
            ))
            steps.append(TraceStepInfo(
                step="verification",
                data=trace_data.get("verification", {}),
            ))

        # Финальный ответ
        steps.append(TraceStepInfo(
            step="answer",
            data={
                "answer": result_data.get("answer", ""),
                "status": log.status,
            },
        ))

        return TraceResponse(
            request_id=log.request_id,
            question=log.question,
            answer=result_data.get("answer", ""),
            status=log.status,
            latency_ms=log.latency_ms,
            trace=trace_data,
            steps=steps,
        )
