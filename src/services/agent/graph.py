from __future__ import annotations
import re
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


def _extract_chart_data(sql_result: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
    """Case A: если sql_result уже является временным рядом (несколько периодов),
    формирует структурированный chart_data [{period, value}, ...]."""
    if not sql_result or len(sql_result) < 2:
        return None
    row = sql_result[0]
    if not isinstance(row, dict):
        return None
    period_key = next(
        (k for k in row if k.lower() in ("sheet_period", "period", "месяц")),
        None,
    )
    value_key = next(
        (k for k, v in row.items()
         if k != period_key and isinstance(v, (int, float))),
        None,
    )
    if not period_key or not value_key:
        return None
    points = []
    for r in sql_result:
        p = r.get(period_key)
        v = r.get(value_key)
        if p is None or v is None:
            continue
        try:
            points.append({"period": str(p), "value": float(v)})
        except (TypeError, ValueError):
            continue
    if len(points) < 2:
        return None
    return points


def _extract_chart_filters(sql_query: str) -> Dict[str, Any]:
    """Извлекает фильтры (category/supplier/price_type) из выполненного SQL.

    Надёжнее, чем entity-candidates: сам SQL уже содержит условия
    ``item_name ILIKE '%...%'`` / ``supplier ILIKE '%...%'`` / ``price_type = '...'``,
    которые агент сгенерировал и выполнил.
    """
    out: Dict[str, Any] = {}

    def _first(pattern: str) -> Optional[str]:
        m = re.search(pattern, sql_query or "", re.IGNORECASE)
        return m.group(1).strip() if m else None

    # item_name ILIKE '%x%'
    cat = _first(r"item_name\s+ILIKE\s+'%([^']+)%'")
    if not cat:
        # item_name IN ('a','b') — берём первый элемент.
        m = re.search(r"item_name\s+IN\s*\(\s*'([^']+)'", sql_query or "", re.IGNORECASE)
        cat = m.group(1).strip() if m else None
    if not cat:
        cat = _first(r"item_name\s*=\s*'([^']+)'")
    if cat:
        out["category"] = cat

    sup = _first(r"supplier\s+ILIKE\s+'%([^']+)%'")
    if not sup:
        m = re.search(r"supplier\s+IN\s*\(\s*'([^']+)'", sql_query or "", re.IGNORECASE)
        sup = m.group(1).strip() if m else None
    if not sup:
        sup = _first(r"supplier\s*=\s*'([^']+)'")
    if sup:
        out["supplier"] = sup

    ptype = _first(r"price_type\s*=\s*'([^']+)'")
    if not ptype:
        ptype = _first(r"price_type\s+ILIKE\s+'%([^']+)%'")
    if ptype:
        out["price_type"] = ptype

    return out


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
    chart_available: bool = False
    chart_data: Optional[List[Dict[str, Any]]] = None

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
            "chart_available": self.chart_available,
            "chart_data": self.chart_data,
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

        # Case A: если результат уже является временным рядом — отдаём chart_data сразу.
        chart_data = _extract_chart_data(sql_result)
        # Кнопка доступна, если есть что резолвить (item/supplier) или уже есть chart_data.
        chart_available = (
            chart_data is not None
            or bool(final_state.get("last_category_id"))
            or bool(final_state.get("last_semantic_keys"))
            or bool(final_state.get("last_supplier_filter"))
        )

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
            chart_available=chart_available,
            chart_data=chart_data,
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

    async def build_chart(
        self,
        thread_id: str,
    ) -> tuple[List[Dict[str, Any]], Optional[str]]:
        """Case B: лёгкий timeseries по уже резолвнутому контексту из checkpoint.

        Не проходит через Router/Entity Resolver и не дёргает LLM — берём последний
        checkpoint по ``thread_id`` и извлекаем фильтры (item/supplier/price_type)
        из уже выполненного ``sql_query`` (надёжнее, чем entity-candidates), строя
        временной ряд по всем месяцам.
        """
        graph = await self._get_graph()
        config = {"configurable": {"thread_id": thread_id}}

        try:
            snapshot = await graph.aget_state(config)
            values = dict(snapshot.values or {})
        except Exception as exc:
            logger.warning("build_chart [{}]: get_state failed: {}", thread_id[:8], exc)
            return [], "Не удалось получить контекст диалога"

        domain = values.get("domain")
        table = "mart.metrics" if getattr(domain, "value", None) == "metrics" else "mart.price_facts"

        # Приоритет: фильтры из выполненного SQL, фолбэк на резолвнутый контекст.
        filters = _extract_chart_filters(values.get("sql_query", ""))
        semantic_keys = values.get("last_semantic_keys") or []
        if not filters.get("category"):
            filters["category"] = values.get("last_category_id") or (semantic_keys[0] if semantic_keys else None)
        if not filters.get("supplier"):
            filters["supplier"] = values.get("last_supplier_filter")

        category = filters.get("category")
        supplier = filters.get("supplier")
        price_type = filters.get("price_type")

        if not category and not supplier:
            return [], "Нет контекста для построения графика"

        # Исходные значения фильтров для условий.
        category_value = category
        supplier_value = supplier

        if table == "mart.metrics":
            where = []
            params: Dict[str, Any] = {}
            if category_value:
                where.append("dimension ILIKE :cat")
                params["cat"] = f"%{category_value}%"
            if supplier_value:
                where.append("supplier ILIKE :sup")
                params["sup"] = f"%{supplier_value}%"
            where_sql = f"WHERE {' AND '.join(where)}" if where else ""
            sql = f"""
SELECT period, AVG(value) AS value
FROM mart.metrics
{where_sql}
GROUP BY period
ORDER BY period"""
        else:
            where = []
            params = {}
            if category_value:
                where.append("fp.item_name ILIKE :cat")
                params["cat"] = f"%{category_value}%"
            if supplier_value:
                where.append("fp.supplier ILIKE :sup")
                params["sup"] = f"%{supplier_value}%"
            if price_type:
                where.append("fp.price_type = :ptype")
                params["ptype"] = price_type
            where_sql = f"WHERE {' AND '.join(where)}" if where else ""
            sql = f"""
SELECT fp.sheet_period AS period, AVG(fp.value) AS value
FROM mart.price_facts fp
{where_sql}
GROUP BY fp.sheet_period
ORDER BY fp.sheet_period"""

        from src.core.db.database import async_session_maker
        from sqlalchemy import text
        try:
            async with async_session_maker() as s:
                res = await s.execute(text(sql), params)
                rows = res.fetchall()
        except Exception as exc:
            logger.error("build_chart [{}]: SQL failed: {}", thread_id[:8], exc)
            return [], "Не удалось выполнить запрос для графика"

        points = [
            {"period": str(r[0]), "value": float(r[1])}
            for r in rows
            if r[0] is not None and r[1] is not None
        ]
        if len(points) < 2:
            return [], "Мало данных для построения временного ряда"
        return points, None


langgraph_agent: LangGraphAgent = LangGraphAgent()