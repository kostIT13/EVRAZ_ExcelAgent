from __future__ import annotations
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from langgraph.graph import END, StateGraph

from src.core.logging_settings import logger
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


async def failed_node(state: GraphState, **kwargs: Any) -> GraphState:
    request_id = state.get("request_id", "?")[:8]
    logger.error("Failed Node [{}]: graph reached failed state", request_id)
    state["error"] = state.get("error") or "Граф достиг ошибочного состояния"
    return state


def build_agent_graph() -> StateGraph:
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

    graph = workflow.compile()

    logger.info("LangGraph agent graph compiled successfully")
    return graph


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
        }


class LangGraphAgent:
    def __init__(self, llm: Optional[LLMClient] = None) -> None:
        self._llm = llm or LLMClient()
        self._graph = build_agent_graph()

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
        is_retry = bool(conversation_history)

        logger.info(
            "LangGraphAgent [{}]: starting for '{}' (retry={})",
            request_id[:8],
            question[:80],
            is_retry,
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
            )

        initial_state: GraphState = {
            "question": question,
            "request_id": request_id,
            "top_k": top_k,
            "response_mode": response_mode,
            "conversation_id": conversation_id,
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

        try:
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

        try:
            from src.core.metrics import observe_ask
            observe_ask(status, latency_ms / 1000.0)
        except Exception:
            pass

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
        entities = final_state.get("entities", [])

        if sql_query and status == "success":
            await query_cache_service.store(
                question=question,
                sql_query=sql_query,
                result={"data": sql_result[:100], "formatted_answer": answer},
                query_type=query_type,
                entities=entities,
                response_mode=response_mode,
            )

        result = AgentResult(
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
            from_cache=False,
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