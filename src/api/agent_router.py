from __future__ import annotations

from typing import List

from fastapi import APIRouter
from src.api.schemas import AskRequest, AskResponse, SourceInfo
from src.core.logging_settings import logger
from src.services.generation.pipeline import pipeline, GenerationResult
from src.services.agent.graph import AgentResult
from src.services.rag.hybrid import HybridSearchResult


router = APIRouter(prefix="/ask", tags=["rag"])


def _history_to_dicts(history):
    return [{"role": t.role, "content": t.content} for t in history]


def _sources_from_chunks(chunks: List[HybridSearchResult]) -> List[SourceInfo]:
    return [
        SourceInfo(
            chunk=s.chunk[:200],
            score=s.score,
            source_type=s.source_type,
            source_id=s.source_id,
            rank=s.rank,
        )
        for s in chunks
    ]


def _build_rag_response(result: GenerationResult, mode_used: str) -> AskResponse:
    return AskResponse(
        answer=result.answer,
        confidence=result.verification.confidence,
        sources=_sources_from_chunks(result.retrieved_chunks),
        request_id=result.request_id,
        latency_ms=result.latency_ms,
        mode_used=mode_used,
    )


def _build_agent_response(result: AgentResult) -> AskResponse:
    return AskResponse(
        answer=result.answer,
        confidence=result.confidence,
        sources=[],
        request_id=result.request_id,
        latency_ms=result.latency_ms,
        mode_used="agent",
        query_type=result.query_type,
        sql_query=result.sql_query,
        sql_result_preview=result.sql_result[:10],
        retry_count=result.retry_count,
        status=result.status,
        self_corrected=result.self_corrected,
    )


@router.post("", response_model=AskResponse)
async def ask_question(request: AskRequest) -> AskResponse:
    history_dicts = _history_to_dicts(request.conversation_history)
    is_retry = len(history_dicts) > 0

    logger.info(
        "Ask request: question='{}', top_k={}, mode={}, retry={}",
        request.question[:100],
        request.top_k,
        request.mode,
        is_retry,
    )

    if request.mode == "rag":
        result = await pipeline.run(
            question=request.question,
            top_k=request.top_k,
            conversation_history=history_dicts,
        )
        return _build_rag_response(result, mode_used="rag")

    agent_result = await pipeline.run_agent(
        question=request.question,
        top_k=request.top_k,
        conversation_history=history_dicts,
    )

    if request.mode == "auto" and agent_result.status == "failed":
        logger.info(
            "Auto mode: agent failed, falling back to RAG for '{}'",
            request.question[:80],
        )
        rag_result = await pipeline.run(
            question=request.question,
            top_k=request.top_k,
            conversation_history=history_dicts,
        )
        return _build_rag_response(rag_result, mode_used="rag_fallback")

    return _build_agent_response(agent_result)
