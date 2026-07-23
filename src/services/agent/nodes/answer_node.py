"""Answer Node — финальный узел графа LangGraph.

Формирует финальный ответ, если верификация не потребовала retry.
Если ответ пустой — формирует fallback-сообщение.
"""

from __future__ import annotations

from src.core.logging_settings import logger
from src.services.agent.graph_state import GraphState, NODE_ANSWER


async def answer_node(state: GraphState) -> GraphState:
    """Узел Answer: финализирует ответ пользователю.

    Args:
        state: Состояние с заполненными answer, confidence, sql_result.

    Returns:
        Финальное состояние с гарантированно непустым answer.
    """
    request_id = state.get("request_id", "?")[:8]
    answer = state.get("answer", "")
    sql_result = state.get("sql_result", [])

    logger.info(
        "Answer Node [{}]: finalizing answer ({} chars)",
        request_id,
        len(answer),
    )

    # Если ответ пустой — формируем fallback
    if not answer:
        if sql_result:
            answer = (
                "Получены данные, но не удалось сформировать ответ. "
                "Пожалуйста, уточните вопрос."
            )
        else:
            answer = (
                "Не удалось найти ответ на ваш вопрос. "
                "Попробуйте переформулировать запрос."
            )
        state["answer"] = answer
        state["confidence"] = state.get("confidence", 0.0)

    # Trace
    state["trace"] = state.get("trace", {})
    state["trace"][NODE_ANSWER] = {
        "answer_length": len(answer),
        "confidence": state.get("confidence", 0.0),
    }

    logger.info(
        "Answer Node [{}]: done, confidence={:.2f}",
        request_id,
        state.get("confidence", 0.0),
    )

    return state