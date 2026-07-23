"""RAG Node — первый узел графа LangGraph.

Выполняет гибридный поиск (BM25 + Dense) по вопросу пользователя,
чтобы получить релевантный контекст из Excel-данных.
Этот контекст используется всеми последующими узлами.
"""

from __future__ import annotations

from typing import Any, Dict, List

from src.core.logging_settings import logger
from src.services.agent.graph_state import GraphState, NODE_RAG, NODE_CLASSIFIER
from src.services.rag.hybrid import HybridSearchResult
from src.services.rag.rag_service import RagService, rag_service
from src.services.generation.rag_prompt import format_context


async def rag_node(
    state: GraphState,
    rag: RagService | None = None,
    top_k: int = 20,
) -> GraphState:
    """Узел RAG: гибридный поиск + форматирование контекста.

    Args:
        state: Текущее состояние графа.
        rag: RAG-сервис (по умолчанию синглтон).
        top_k: Количество чанков для поиска.

    Returns:
        Обновлённое состояние с rag_context и rag_chunks.
    """
    rag = rag or rag_service
    request_id = state.get("request_id", "?")[:8]
    question = state.get("question", "")

    logger.info(
        "RAG Node [{}]: hybrid search for '{}' (top_k={})",
        request_id,
        question[:80],
        top_k,
    )

    # 1. Гибридный поиск
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
        state[NODE_CLASSIFIER] = NODE_CLASSIFIER  # продолжаем даже без RAG
        return state

    # 2. Форматируем контекст
    try:
        context = format_context(chunks)
    except Exception as exc:
        logger.error("RAG Node [{}]: format_context failed: {}", request_id, exc)
        context = ""

    # 3. Сохраняем в state
    state["rag_context"] = context
    state["rag_chunks"] = [c.to_dict() for c in chunks]
    state["rag_error"] = None

    # 4. Trace
    state["trace"] = state.get("trace", {})
    state["trace"][NODE_RAG] = {
        "chunk_count": len(chunks),
        "top_scores": [round(c.score, 4) for c in chunks[:5]],
    }

    logger.info(
        "RAG Node [{}]: context prepared ({} chars, {} chunks)",
        request_id,
        len(context),
        len(chunks),
    )

    return state