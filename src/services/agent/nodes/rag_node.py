from __future__ import annotations
from typing import Any, Dict, List, Optional
from src.core.logging_settings import logger
from src.services.agent.graph_state import GraphState, NODE_RAG
from src.services.rag.hybrid import HybridSearchResult
from src.services.rag.rag_service import RagService, rag_service
from src.services.generation.rag_prompt import format_context

# Минимальный порог качества RAG: если средний score < этого значения,
# считаем что RAG не нашёл релевантных данных
MIN_AVG_SCORE_THRESHOLD = 0.3


async def rag_node(
    state: GraphState,
    rag: Optional[RagService] = None,
    **kwargs: Any,
) -> GraphState:
    rag = rag or rag_service
    request_id = state.get("request_id", "?")[:8]
    question = state.get("question", "")
    top_k = state.get("top_k", 30)

    logger.info(
        "RAG Node [{}]: hybrid search for '{}' (top_k={})",
        request_id,
        question[:80],
        top_k,
    )

    try:
        chunks: List[HybridSearchResult] = await rag.hybrid_search(
            query=question,
            top_k=top_k,
        )
        logger.info(
            "RAG Node [{}]: retrieved {} chunks",
            request_id,
            len(chunks),
        )
    except Exception as exc:
        logger.error("RAG Node [{}]: search failed: {}", request_id, exc)
        state["rag_context"] = ""
        state["rag_chunks"] = []
        state["rag_error"] = str(exc)
        state["trace"] = state.get("trace", {})
        state["trace"][NODE_RAG] = {"error": str(exc), "chunk_count": 0}
        return state

    # Диагностика качества RAG
    source_types = {}
    if chunks:
        scores = [c.score for c in chunks]
        avg_score = sum(scores) / len(scores)
        max_score = max(scores)
        min_score = min(scores)
        for c in chunks:
            st = c.source_type or "unknown"
            source_types[st] = source_types.get(st, 0) + 1

        logger.info(
            "RAG Node [{}]: quality check — avg_score={:.4f}, max_score={:.4f}, "
            "min_score={:.4f}, sources={}",
            request_id,
            avg_score,
            max_score,
            min_score,
            source_types,
        )

        # Если средний score слишком низкий — логируем предупреждение
        if avg_score < MIN_AVG_SCORE_THRESHOLD:
            logger.warning(
                "RAG Node [{}]: low quality results (avg_score={:.4f} < {}). "
                "RAG may not have found relevant data.",
                request_id,
                avg_score,
                MIN_AVG_SCORE_THRESHOLD,
            )
    else:
        logger.warning(
            "RAG Node [{}]: no chunks retrieved at all!",
            request_id,
        )

    try:
        # Увеличиваем лимит контекста с 48000 до 64000 символов
        context = format_context(chunks, max_chars=64000)
    except Exception as exc:
        logger.error("RAG Node [{}]: format_context failed: {}", request_id, exc)
        context = ""

    state["rag_context"] = context
    state["rag_chunks"] = [c.to_dict() for c in chunks]
    state["rag_error"] = None

    state["trace"] = state.get("trace", {})
    state["trace"][NODE_RAG] = {
        "chunk_count": len(chunks),
        "top_scores": [round(c.score, 4) for c in chunks[:5]],
        "avg_score": round(sum(c.score for c in chunks) / len(chunks), 4) if chunks else 0,
        "source_types": source_types,
    }

    logger.info(
        "RAG Node [{}]: context prepared ({} chars, {} chunks)",
        request_id,
        len(context),
        len(chunks),
    )

    return state