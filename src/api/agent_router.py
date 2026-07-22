"""
API router for RAG question-answering endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from src.api.schemas import AskRequest, AskResponse, SourceInfo
from src.core.logging_settings import logger
from src.services.generation.pipeline import pipeline

router = APIRouter(prefix="/ask", tags=["rag"])


@router.post("", response_model=AskResponse)
async def ask_question(request: AskRequest) -> AskResponse:
    """Ask a question about the uploaded Excel data.

    The pipeline performs:
    1. Hybrid retrieval (BM25 + Dense vector search)
    2. LLM generation with context
    3. Response verification
    """
    logger.info(
        "Ask request: question='{}', top_k={}",
        request.question[:100],
        request.top_k,
    )

    try:
        result = await pipeline.run(
            question=request.question,
            top_k=request.top_k,
        )

        logger.info(
            "Ask response: request_id={}, confidence={:.2f}, latency={}ms",
            result.request_id,
            result.verification.confidence,
            result.latency_ms,
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
        )

    except Exception as exc:
        logger.error("Ask request failed: {}", exc)
        raise HTTPException(status_code=500, detail=str(exc))