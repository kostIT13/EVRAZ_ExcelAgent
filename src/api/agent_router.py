from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from src.api.schemas import (
    AskRequest,
    AskResumeRequest,
    AskResponse,
    ChartRequest,
    ChartResponse,
    WaitForInputInfo,
)
from src.api.security import verify_api_key
from src.core.logging_settings import logger
from src.core.ratelimit import get_limiter, ask_limit
from src.services.generation.pipeline import pipeline
from src.services.agent.graph import AgentResult, STATUS_WAITING, langgraph_agent

router = APIRouter(prefix="/ask", tags=["agent"])
_limiter = get_limiter()


def _history_to_dicts(history):
    return [{"role": t.role, "content": t.content} for t in history]


def _build_agent_response(result: AgentResult, response_mode: str = "detailed") -> AskResponse:
    waiting = None
    if result.status == STATUS_WAITING and result.waiting_question is not None:
        waiting = WaitForInputInfo(
            question=result.waiting_question.get("question", ""),
            options=result.waiting_question.get("options", []),
        )
    return AskResponse(
        answer=result.answer,
        confidence=result.confidence,
        sources=[],
        request_id=result.request_id,
        latency_ms=result.latency_ms,
        mode_used="agent",
        response_mode=response_mode,
        query_type=result.query_type,
        sql_query=result.sql_query,
        sql_result_preview=result.sql_result[:10],
        retry_count=result.retry_count,
        status=result.status,
        self_corrected=result.self_corrected,
        thread_id=result.thread_id,
        waiting_question=waiting,
        chart_available=result.chart_available,
        chart_data=result.chart_data,
    )


@router.post("", response_model=AskResponse)
@_limiter.limit(ask_limit)
async def ask_question(
    request: Request,
    body: AskRequest,
    _key: str = Depends(verify_api_key),
) -> AskResponse:
    history_dicts = _history_to_dicts(body.conversation_history)
    is_retry = len(history_dicts) > 0

    logger.info(
        "Ask request: question='{}', top_k={}, mode={}, retry={}",
        body.question[:100],
        body.top_k,
        body.mode,
        is_retry,
    )
    if body.mode == "rag":
        rag_result = await pipeline.run_agent(
            question=body.question,
            top_k=body.top_k,
            conversation_history=history_dicts,
            conversation_id=body.conversation_id,
            response_mode=body.response_mode,
        )
        return _build_agent_response(rag_result, body.response_mode)

    agent_result = await pipeline.run_agent(
        question=body.question,
        top_k=body.top_k,
        conversation_history=history_dicts,
        conversation_id=body.conversation_id,
        response_mode=body.response_mode,
    )

    if body.mode == "auto" and agent_result.status == "failed":
        logger.info(
            "Auto mode: agent failed, falling back to entity-resolution agent for '{}'",
            body.question[:80],
        )
        fallback_result = await pipeline.run_agent(
            question=body.question,
            top_k=body.top_k,
            conversation_history=history_dicts,
            conversation_id=body.conversation_id,
            response_mode=body.response_mode,
        )
        return _build_agent_response(fallback_result, body.response_mode)

    return _build_agent_response(agent_result, body.response_mode)


@router.post("/resume", response_model=AskResponse)
@_limiter.limit(ask_limit)
async def ask_resume(
    request: Request,
    body: AskResumeRequest,
    _key: str = Depends(verify_api_key),
) -> AskResponse:
    """Продолжает прерванный на уточняющем вопросе агентный запуск."""
    logger.info(
        "Ask resume request: thread='{}', answer='{}'",
        body.thread_id[:8],
        body.user_answer[:80],
    )
    result = await pipeline.resume_agent(
        thread_id=body.thread_id,
        user_answer=body.user_answer,
        response_mode=body.response_mode,
    )
    return _build_agent_response(result, body.response_mode)


@router.post("/chart", response_model=ChartResponse)
@_limiter.limit(ask_limit)
async def ask_chart(
    request: Request,
    body: ChartRequest,
    _key: str = Depends(verify_api_key),
) -> ChartResponse:
    """Лёгкий timeseries по уже резолвнутому контексту из checkpoint.

    Не проходит через Router/Entity Resolver и не дёргает LLM — переиспользует
    last_category_id/last_semantic_keys/last_supplier_filter из памяти диалога.
    """
    logger.info("Ask chart request: thread='{}'", body.thread_id[:8])
    data, error = await langgraph_agent.build_chart(thread_id=body.thread_id)
    if error:
        return ChartResponse(
            thread_id=body.thread_id,
            chart_available=False,
            chart_data=[],
            message=error,
        )
    return ChartResponse(
        thread_id=body.thread_id,
        chart_available=True,
        chart_data=data,
    )
