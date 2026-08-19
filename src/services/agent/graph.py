from __future__ import annotations
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from langgraph.graph import END, StateGraph
from langgraph.types import Command

from src.core.logging_settings import logger
from src.services.agent.checkpointer import CheckpointerManager
from src.services.agent.graph_state import (
    GraphState,
    NODE_CLASSIFIER,
    NODE_DISAMBIGUATION,
    NODE_PLANNER,
    NODE_CODEGEN,
    NODE_EXECUTOR,
    NODE_VERIFIER,
    NODE_ANSWER,
    NODE_FAILED,
)
from src.services.agent.nodes.entity_resolution_node import entity_resolution_node
from src.services.agent.nodes.classifier_node import classifier_node
from src.services.agent.nodes.disambiguation_node import disambiguation_node
from src.services.agent.nodes.planner_node import planner_node
from src.services.agent.nodes.codegen_node import codegen_node
from src.services.agent.nodes.executor_node import executor_node
from src.services.agent.nodes.verifier_node import verifier_node
from src.services.agent.nodes.answer_node import answer_node
from src.services.agent.nodes.routing import (
    route_after_classifier,
    route_after_disambiguation,
    route_after_planner,
    route_after_codegen,
    route_after_executor,
    route_after_verifier,
)
from src.services.llm.llm_client import LLMClient
from src.services.entity_resolution.query_cache import query_cache_service

# Ключ, в котором LangGraph возвращает активные interrupt-точки после ainvoke.
INTERRUPT_KEY = "__interrupt__"
STATUS_WAITING = "waiting_for_input"


async def failed_node(state: GraphState, **kwargs: Any) -> GraphState:
    request_id = state.get("request_id", "?")[:8]
    logger.error("Failed Node [{}]: graph reached failed state", request_id)
    state["error"] = state.get("error") or "Граф достиг ошибочного состояния"
    return state


def build_agent_graph() -> StateGraph:
    """Собирает workflow (без компиляции).

    Компиляция с Postgres-checkpointer'ом выполняется лениво в ``LangGraphAgent._get_graph``,
    т.к. инициализация пула соединений — асинхронная.
    """
    workflow = StateGraph(GraphState)

    workflow.add_node(NODE_CLASSIFIER, classifier_node)
    workflow.add_node(NODE_DISAMBIGUATION, disambiguation_node)
    workflow.add_node(NODE_PLANNER, planner_node)
    workflow.add_node(NODE_CODEGEN, codegen_node)
    workflow.add_node(NODE_EXECUTOR, executor_node)
    workflow.add_node(NODE_VERIFIER, verifier_node)
    workflow.add_node(NODE_ANSWER, answer_node)
    workflow.add_node(NODE_FAILED, failed_node)

    workflow.set_entry_point(NODE_CLASSIFIER)

    workflow.add_conditional_edges(
        NODE_CLASSIFIER,
        route_after_classifier,
        {
            NODE_DISAMBIGUATION: NODE_DISAMBIGUATION,
            NODE_PLANNER: NODE_PLANNER,
            NODE_FAILED: NODE_FAILED,
        },
    )

    workflow.add_conditional_edges(
        NODE_DISAMBIGUATION,
        route_after_disambiguation,
        {
            NODE_PLANNER: NODE_PLANNER,
            NODE_FAILED: NODE_FAILED,
        },
    )

    workflow.add_conditional_edges(
        NODE_PLANNER,
        route_after_planner,
        {
            NODE_CODEGEN: NODE_CODEGEN,
            NODE_FAILED: NODE_FAILED,
        },
    )

    workflow.add_conditional_edges(
        NODE_CODEGEN,
        route_after_codegen,
        {
            NODE_EXECUTOR: NODE_EXECUTOR,
            NODE_CODEGEN: NODE_CODEGEN,
            NODE_FAILED: NODE_FAILED,
        },
    )

    workflow.add_conditional_edges(
        NODE_EXECUTOR,
        route_after_executor,
        {
            NODE_VERIFIER: NODE_VERIFIER,
            NODE_CODEGEN: NODE_CODEGEN,
            NODE_FAILED: NODE_FAILED,
        },
    )

    workflow.add_conditional_edges(
        NODE_VERIFIER,
        route_after_verifier,
        {
            NODE_ANSWER: NODE_ANSWER,
            NODE_CODEGEN: NODE_CODEGEN,
            NODE_FAILED: NODE_FAILED,
        },
    )

    workflow.add_edge(NODE_ANSWER, END)
    workflow.add_edge(NODE_FAILED, END)

    return workflow


@dataclass
class AgentResult:
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
    status: str
    self_corrected: bool = False
    from_cache: bool = False
    thread_id: Optional[str] = None
    waiting_question: Optional[Dict[str, Any]] = None
    waiting_options: Optional[List[str]] = field(default_factory=list)

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
            "from_cache": self.from_cache,
            "thread_id": self.thread_id,
            "waiting_question": self.waiting_question,
            "waiting_options": self.waiting_options,
        }


class LangGraphAgent:
    def __init__(self, llm: Optional[LLMClient] = None) -> None:
        self._llm = llm or LLMClient()
        self._workflow = build_agent_graph()
        self._graph = None

    async def _get_graph(self):
        """Компилирует граф с Postgres-checkpointer'ом один раз (лениво)."""
        if self._graph is None:
            checkpointer = await CheckpointerManager.get()
            self._graph = self._workflow.compile(checkpointer=checkpointer)
            logger.info("LangGraph agent graph compiled with Postgres checkpointer")
        return self._graph

    @staticmethod
    def _extract_interrupt(final_state: Dict[str, Any]):
        interrupts = final_state.get(INTERRUPT_KEY)
        if interrupts:
            intr = interrupts[0]
            value = getattr(intr, "value", None)
            # interrupt() payload может быть dict с "question"/"options"
            if isinstance(value, dict):
                question = value.get("question") or value.get("payload", "")
                options = value.get("options") or []
                return question, options
            return value, []
        return None, []

    def _finalize(
        self,
        final_state: Dict[str, Any],
        question: str,
        request_id: str,
        thread_id: Optional[str],
        start_time: float,
        response_mode: str,
        from_cache: bool = False,
    ) -> AgentResult:
        latency_ms = int((time.monotonic() - start_time) * 1000)
        confidence = final_state.get("confidence", 0.0)
        has_error = final_state.get("error") is not None

        if has_error:
            status = "failed"
        elif confidence >= 0.7:
            status = "success"
        else:
            status = "low_confidence"

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

        sql_query = final_state.get("sql_query", "")
        sql_result = final_state.get("sql_result", [])
        query_type = (
            final_state.get("query_type").value
            if final_state.get("query_type")
            else "unknown"
        )

        waiting_question, waiting_options = self._extract_interrupt(final_state)
        if waiting_question is not None:
            status = STATUS_WAITING
            answer = ""

        return AgentResult(
            answer=answer,
            confidence=confidence,
            request_id=request_id,
            question=question,
            latency_ms=latency_ms,
            trace=final_state.get("trace", {}),
            query_type=query_type,
            sql_query=sql_query,
            sql_result=sql_result,
            retry_count=final_state.get("retry_count", 0),
            status=status,
            from_cache=from_cache,
            thread_id=thread_id,
            waiting_question={
                "question": waiting_question,
                "options": waiting_options,
            }
            if waiting_question is not None
            else None,
            waiting_options=waiting_options,
        )

    async def run(
        self,
        question: str,
        top_k: int = 30,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        conversation_id: Optional[str] = None,
        response_mode: str = "detailed",
    ) -> AgentResult:
        request_id = str(uuid.uuid4())
        start_time = time.monotonic()
        # thread_id = стабильный идентификатор диалога для checkpointer/интерраптов.
        thread_id = conversation_id or request_id
        is_retry = bool(conversation_history)

        logger.info(
            "LangGraphAgent [{}]: starting for '{}' (retry={}, thread={})",
            request_id[:8],
            question[:80],
            is_retry,
            thread_id[:8],
        )

        try:
            cached = await query_cache_service.lookup(question, response_mode=response_mode)
        except Exception as exc:
            logger.warning("LangGraphAgent [{}]: cache lookup failed: {}", request_id[:8], exc)
            cached = None

        if cached is not None:
            latency_ms = int((time.monotonic() - start_time) * 1000)
            logger.info(
                "LangGraphAgent [{}]: cache HIT, returning cached result",
                request_id[:8],
            )
            return AgentResult(
                answer=cached.get("result", {}).get("formatted_answer", "Данные из кэша."),
                confidence=1.0,
                request_id=request_id,
                question=question,
                latency_ms=latency_ms,
                trace={"from_cache": True, "cached_sql": cached["sql_query"]},
                query_type=cached.get("query_type", "unknown"),
                sql_query=cached["sql_query"],
                sql_result=cached.get("result", {}).get("data", []),
                retry_count=0,
                status="success",
                from_cache=True,
                thread_id=thread_id,
            )

        initial_state: GraphState = {
            "question": question,
            "request_id": request_id,
            "top_k": top_k,
            "response_mode": response_mode,
            "conversation_id": thread_id,
            "conversation_history": conversation_history or [],
            "entity_candidates": [],
            "entities_for_prompt": None,
            "query_type": None,
            "entities": [],
            "relevant_sheets": [],
            "disambiguation_needed": False,
            "disambiguation_info": {},
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

        if conversation_history:
            initial_state["trace"]["conversation_history"] = conversation_history

        graph = await self._get_graph()

        try:
            config = {
                "configurable": {
                    "llm": self._llm,
                    "thread_id": thread_id,
                }
            }
            final_state = await graph.ainvoke(initial_state, config=config)
        except Exception as exc:
            logger.error(
                "LangGraphAgent [{}]: graph execution failed: {}",
                request_id[:8],
                exc,
            )
            final_state = dict(initial_state)
            final_state["error"] = str(exc)
            final_state["answer"] = (
                "Произошла внутренняя ошибка при обработке запроса. "
                "Пожалуйста, попробуйте позже."
            )

        result = self._finalize(
            final_state, question, request_id, thread_id, start_time, response_mode
        )

        # Кэшируем только успешные завершённые ответы.
        if (
            result.sql_query
            and result.status == "success"
            and not result.from_cache
        ):
            await query_cache_service.store(
                question=question,
                sql_query=result.sql_query,
                result={"data": result.sql_result[:100], "formatted_answer": result.answer},
                query_type=result.query_type,
                entities=final_state.get("entities", []),
                response_mode=response_mode,
            )

        try:
            from src.core.metrics import observe_ask
            observe_ask(result.status, result.latency_ms / 1000.0)
        except Exception:
            pass

        logger.info(
            "LangGraphAgent [{}]: finished status={}, confidence={:.2f}, latency={}ms",
            request_id[:8],
            result.status,
            result.confidence,
            result.latency_ms,
        )

        return result

    async def resume(
        self,
        thread_id: str,
        user_answer: Any,
        response_mode: str = "detailed",
    ) -> AgentResult:
        """Продолжает прерванный (interrupt) запуск с ответом пользователя."""
        request_id = str(uuid.uuid4())
        start_time = time.monotonic()

        logger.info(
            "LangGraphAgent [{}]: resuming thread {} with user answer",
            request_id[:8],
            thread_id[:8],
        )

        graph = await self._get_graph()

        try:
            config = {
                "configurable": {
                    "llm": self._llm,
                    "thread_id": thread_id,
                }
            }
            # Command(resume=...) продолжает граф с точки interrupt().
            final_state = await graph.ainvoke(
                Command(resume=user_answer),
                config=config,
            )
        except Exception as exc:
            logger.error(
                "LangGraphAgent [{}]: resume failed: {}",
                request_id[:8],
                exc,
            )
            final_state = {
                "answer": (
                    "Не удалось продолжить обработку запроса. "
                    "Попробуйте задать вопрос заново."
                ),
                "error": str(exc),
                "confidence": 0.0,
                "trace": {},
                "sql_query": "",
                "sql_result": [],
                "retry_count": 0,
                "query_type": None,
            }

        question = final_state.get("question", "")
        result = self._finalize(
            final_state, question, request_id, thread_id, start_time, response_mode
        )

        if result.sql_query and result.status == "success" and question:
            try:
                await query_cache_service.store(
                    question=question,
                    sql_query=result.sql_query,
                    result={
                        "data": result.sql_result[:100],
                        "formatted_answer": result.answer,
                    },
                    query_type=result.query_type,
                    entities=final_state.get("entities", []),
                    response_mode=response_mode,
                )
            except Exception as exc:
                logger.warning("Resume [{}]: cache store failed: {}", request_id[:8], exc)

        return result


langgraph_agent: LangGraphAgent = LangGraphAgent()