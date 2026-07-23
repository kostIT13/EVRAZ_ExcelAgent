"""LangGraph граф агента EVRAZ.

Строит StateGraph со всеми узлами и conditional edges.
Предоставляет точку входа LangGraphAgent для использования из pipeline.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from langgraph.graph import END, StateGraph

from src.core.logging_settings import logger
from src.services.agent.graph_state import (
    GraphState,
    NODE_RAG,
    NODE_CLASSIFIER,
    NODE_PLANNER,
    NODE_CODEGEN,
    NODE_EXECUTOR,
    NODE_VERIFIER,
    NODE_ANSWER,
    NODE_FAILED,
)
from src.services.agent.nodes.rag_node import rag_node
from src.services.agent.nodes.classifier_node import classifier_node
from src.services.agent.nodes.planner_node import planner_node
from src.services.agent.nodes.codegen_node import codegen_node
from src.services.agent.nodes.executor_node import executor_node
from src.services.agent.nodes.verifier_node import verifier_node
from src.services.agent.nodes.answer_node import answer_node
from src.services.agent.nodes.routing import (
    route_after_rag,
    route_after_classifier,
    route_after_planner,
    route_after_codegen,
    route_after_executor,
    route_after_verifier,
)
from src.services.llm.llm_client import LLMClient


# ---------------------------------------------------------------------------
# Failed Node
# ---------------------------------------------------------------------------

async def failed_node(state: GraphState, **kwargs: Any) -> GraphState:
    """Узел-заглушка для ошибочных состояний.

    Просто логирует ошибку и завершает граф.
    """
    request_id = state.get("request_id", "?")[:8]
    logger.error("Failed Node [{}]: graph reached failed state", request_id)
    state["error"] = state.get("error") or "Граф достиг ошибочного состояния"
    return state


# ---------------------------------------------------------------------------
# Сборка графа
# ---------------------------------------------------------------------------

def build_agent_graph() -> StateGraph:
    """Собрать и скомпилировать граф агента.

    Returns:
        Скомпилированный граф (CompiledStateGraph).
    """
    # 1. Создаём граф с состоянием GraphState
    workflow = StateGraph(GraphState)

    # 2. Добавляем узлы
    workflow.add_node(NODE_RAG, rag_node)
    workflow.add_node(NODE_CLASSIFIER, classifier_node)
    workflow.add_node(NODE_PLANNER, planner_node)
    workflow.add_node(NODE_CODEGEN, codegen_node)
    workflow.add_node(NODE_EXECUTOR, executor_node)
    workflow.add_node(NODE_VERIFIER, verifier_node)
    workflow.add_node(NODE_ANSWER, answer_node)
    workflow.add_node(NODE_FAILED, failed_node)

    # 3. Добавляем рёбра
    # Старт → RAG
    workflow.set_entry_point(NODE_RAG)

    # RAG → Classifier (условно)
    workflow.add_conditional_edges(
        NODE_RAG,
        route_after_rag,
        {
            NODE_CLASSIFIER: NODE_CLASSIFIER,
            NODE_FAILED: NODE_FAILED,
        },
    )

    # Classifier → Planner (безусловно)
    workflow.add_conditional_edges(
        NODE_CLASSIFIER,
        route_after_classifier,
        {
            NODE_PLANNER: NODE_PLANNER,
            NODE_FAILED: NODE_FAILED,
        },
    )

    # Planner → CodeGen (безусловно)
    workflow.add_conditional_edges(
        NODE_PLANNER,
        route_after_planner,
        {
            NODE_CODEGEN: NODE_CODEGEN,
            NODE_FAILED: NODE_FAILED,
        },
    )

    # CodeGen → Executor | CodeGen (retry) | Failed
    workflow.add_conditional_edges(
        NODE_CODEGEN,
        route_after_codegen,
        {
            NODE_EXECUTOR: NODE_EXECUTOR,
            NODE_CODEGEN: NODE_CODEGEN,
            NODE_FAILED: NODE_FAILED,
        },
    )

    # Executor → Verifier | CodeGen (retry) | Failed
    workflow.add_conditional_edges(
        NODE_EXECUTOR,
        route_after_executor,
        {
            NODE_VERIFIER: NODE_VERIFIER,
            NODE_CODEGEN: NODE_CODEGEN,
            NODE_FAILED: NODE_FAILED,
        },
    )

    # Verifier → Answer | CodeGen (retry) | Failed
    workflow.add_conditional_edges(
        NODE_VERIFIER,
        route_after_verifier,
        {
            NODE_ANSWER: NODE_ANSWER,
            NODE_CODEGEN: NODE_CODEGEN,
            NODE_FAILED: NODE_FAILED,
        },
    )

    # Answer → END
    workflow.add_edge(NODE_ANSWER, END)

    # Failed → END
    workflow.add_edge(NODE_FAILED, END)

    # 4. Компилируем
    graph = workflow.compile()

    logger.info("LangGraph agent graph compiled successfully")
    return graph


# ---------------------------------------------------------------------------
# LangGraphAgent
# ---------------------------------------------------------------------------

@dataclass
class AgentResult:
    """Результат работы агента (совместим со старым AgentResult)."""
    answer: str
    confidence: float
    request_id: str
    question: str
    latency_ms: int
    trace: Dict[str, Any]
    query_type: str
    sql_query: str
    sql_result: List[Dict[str, Any]]
    retry_count: int
    status: str  # "success", "low_confidence", "failed"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "answer": self.answer,
            "confidence": self.confidence,
            "request_id": self.request_id,
            "question": self.question,
            "latency_ms": self.latency_ms,
            "trace": self.trace,
            "query_type": self.query_type,
            "sql_query": self.sql_query,
            "sql_result": self.sql_result[:5],
            "retry_count": self.retry_count,
            "status": self.status,
        }


class LangGraphAgent:
    """Агент на базе LangGraph.

    Использует StateGraph с узлами:
    RAG → Classifier → Planner → CodeGen → Executor → Verifier → Answer
    """

    def __init__(self, llm: Optional[LLMClient] = None) -> None:
        self._llm = llm or LLMClient()
        self._graph = build_agent_graph()

    async def run(self, question: str, top_k: int = 30) -> AgentResult:
        """Запустить агента для ответа на вопрос.

        Args:
            question: Вопрос пользователя.
            top_k: Количество чанков для RAG-поиска.

        Returns:
            AgentResult с ответом и полным trace.
        """
        request_id = str(uuid.uuid4())
        start_time = time.monotonic()

        logger.info(
            "LangGraphAgent [{}]: starting for '{}'",
            request_id[:8],
            question[:80],
        )

        # 1. Начальное состояние
        initial_state: GraphState = {
            "question": question,
            "request_id": request_id,
            "top_k": top_k,
            "rag_context": "",
            "rag_chunks": [],
            "rag_error": None,
            "query_type": None,  # type: ignore[typeddict-item]
            "entities": [],
            "relevant_sheets": [],
            "plan": "",
            "schema": [],
            "sql_query": "",
            "validation_errors": [],
            "sql_result": [],
            "sql_error": None,
            "answer": "",
            "confidence": 0.0,
            "retry_count": 0,
            "needs_retry": False,
            "retry_reason": "",
            "trace": {},
            "error": None,
        }

        # 2. Запускаем граф
        try:
            # Передаём llm через config
            config = {"configurable": {"llm": self._llm}}
            final_state = await self._graph.ainvoke(initial_state, config=config)
        except Exception as exc:
            logger.error(
                "LangGraphAgent [{}]: graph execution failed: {}",
                request_id[:8],
                exc,
            )
            final_state = initial_state
            final_state["error"] = str(exc)
            final_state["answer"] = (
                "Произошла внутренняя ошибка при обработке запроса. "
                "Пожалуйста, попробуйте позже."
            )

        # 3. Формируем результат
        latency_ms = int((time.monotonic() - start_time) * 1000)
        confidence = final_state.get("confidence", 0.0)
        has_error = final_state.get("error") is not None

        if has_error:
            status = "failed"
        elif confidence >= 0.7:
            status = "success"
        elif confidence >= 0.3:
            status = "low_confidence"
        else:
            status = "low_confidence"

        # Если ответ пустой — fallback
        answer = final_state.get("answer", "")
        if not answer:
            if final_state.get("sql_result"):
                answer = (
                    "Получены данные, но не удалось сформировать ответ. "
                    "Пожалуйста, уточните вопрос."
                )
            else:
                answer = (
                    "Не удалось найти ответ на ваш вопрос. "
                    "Попробуйте переформулировать запрос."
                )

        result = AgentResult(
            answer=answer,
            confidence=confidence,
            request_id=request_id,
            question=question,
            latency_ms=latency_ms,
            trace=final_state.get("trace", {}),
            query_type=(
                final_state.get("query_type").value
                if final_state.get("query_type")
                else "unknown"
            ),
            sql_query=final_state.get("sql_query", ""),
            sql_result=final_state.get("sql_result", []),
            retry_count=final_state.get("retry_count", 0),
            status=status,
        )

        logger.info(
            "LangGraphAgent [{}]: finished status={}, confidence={:.2f}, latency={}ms",
            request_id[:8],
            status,
            confidence,
            latency_ms,
        )

        return result


langgraph_agent: LangGraphAgent = LangGraphAgent()