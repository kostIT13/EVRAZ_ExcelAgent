from __future__ import annotations

from fastapi import APIRouter, HTTPException
from src.api.schemas import AskRequest, AskResponse, SourceInfo
from src.core.logging_settings import logger
from src.services.generation.pipeline import pipeline

router = APIRouter(prefix="/ask", tags=["rag"])


def _history_to_dicts(history):
    return [{"role": t.role, "content": t.content} for t in history]


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

    try:
        if request.mode == "rag":
            result = await pipeline.run(
                question=request.question,
                top_k=request.top_k,
                conversation_history=history_dicts,
            )

            return AskResponse(
                answer=result.answer,
                confidence=result.verification.confidence,
                sources=[
                    SourceInfo(
                        chunk=s.chunk[:200],
                        score=s.score,
                        source_type=s.source_type,
                        source_id=s.source_id,
                        rank=s.rank,
                    )
                    for s in result.retrieved_chunks
                ],
                request_id=result.request_id,
                latency_ms=result.latency_ms,
                mode_used="rag",
            )

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

            return AskResponse(
                answer=rag_result.answer,
                confidence=rag_result.verification.confidence,
                sources=[
                    SourceInfo(
                        chunk=s.chunk[:200],
                        score=s.score,
                        source_type=s.source_type,
                        source_id=s.source_id,
                        rank=s.rank,
                    )
                    for s in rag_result.retrieved_chunks
                ],
                request_id=rag_result.request_id,
                latency_ms=rag_result.latency_ms,
                mode_used="rag_fallback",
            )

        return AskResponse(
            answer=agent_result.answer,
            confidence=agent_result.confidence,
            sources=[],  
            request_id=agent_result.request_id,
            latency_ms=agent_result.latency_ms,
            mode_used="agent",
            query_type=agent_result.query_type,
            sql_query=agent_result.sql_query,
            sql_result_preview=agent_result.sql_result[:10],
            retry_count=agent_result.retry_count,
            status=agent_result.status,
            self_corrected=agent_result.self_corrected,
        )

    except Exception as exc:
        logger.error("Ask request failed: {}", exc)
        raise HTTPException(status_code=500, detail=str(exc))
