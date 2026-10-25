from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query
from src.api.schemas import TraceListResponse, TraceResponse, TraceStepInfo
from src.core.logging_settings import logger
from src.services.db_tables.query_log_service.service import TraceService


router = APIRouter(prefix="/trace", tags=["traceability"])

STEP_LABELS = {
    "question": {"icon": "❓", "label": "Вопрос пользователя"},
    "classifier": {"icon": "🔍", "label": "Классификация запроса"},
    "planner": {"icon": "📋", "label": "Планирование"},
    "codegen": {"icon": "💻", "label": "Генерация SQL"},
    "executor": {"icon": "⚡", "label": "Выполнение SQL"},
    "verifier": {"icon": "✅", "label": "Верификация"},
    "retrieval": {"icon": "📚", "label": "Поиск в RAG"},
    "answer": {"icon": "🤖", "label": "Формирование ответа"},
}

# Порядок поиска текста ошибки: узел, который упал первым, и есть причина.
ERROR_STEP_ORDER = ("codegen", "executor", "verifier", "classifier", "planner")


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _step_error(agent_trace: Dict[str, Any]) -> str:
    for step_name in ERROR_STEP_ORDER:
        error = _as_dict(agent_trace.get(step_name)).get("error")
        if error:
            return str(error)
    return ""


def _confidence(
    result_data: Dict[str, Any], agent_trace: Dict[str, Any]
) -> tuple[float, str]:
    """Уверенность ответа: сначала из result, иначе из шага верификатора.

    Поле confidence колонки result появилось позже строк query_logs, поэтому для
    исторических запросов единственным источником остаётся trace.agent_trace.verifier.
    """
    for source, container in (("result", result_data), ("verifier", agent_trace.get("verifier"))):
        value = _as_dict(container).get("confidence")
        if isinstance(value, (int, float)):
            return float(value), source
    return 0.0, "unknown"


def _summary_fields(log) -> Dict[str, Any]:
    """Поля трейса, общие для детального ответа и строки истории."""
    trace_data = _as_dict(log.trace)
    agent_trace = _as_dict(trace_data.get("agent_trace"))
    result_data = _as_dict(log.result)
    confidence, confidence_source = _confidence(result_data, agent_trace)

    return {
        "confidence": confidence,
        "confidence_source": confidence_source,
        "sql_query": log.sql_query or trace_data.get("sql_query") or "",
        "query_type": trace_data.get("query_type") or _as_dict(
            agent_trace.get("classifier")
        ).get("query_type") or "",
        "retry_count": int(trace_data.get("retry_count") or 0),
        "error_message": log.error_message
        or trace_data.get("error")
        or _step_error(agent_trace)
        or "",
        "from_cache": bool(trace_data.get("from_cache")),
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


@router.get("", response_model=TraceListResponse)
async def list_traces(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    q: Optional[str] = Query(None, min_length=1, max_length=200, description="Подстрока в тексте вопроса"),
    status: Optional[str] = Query(None, description="success / low_confidence / failed"),
    since: Optional[datetime] = Query(None, description="Начало периода, ISO-время"),
    until: Optional[datetime] = Query(None, description="Конец периода, ISO-время"),
) -> TraceListResponse:
    logger.info(
        "List traces: limit={}, offset={}, q='{}', status='{}'", limit, offset, q, status
    )

    service = TraceService()
    logs, total = await service.list_page(
        skip=offset, limit=limit, q=q, status=status, since=since, until=until
    )

    return TraceListResponse(
        items=[
            {
                "request_id": log.request_id,
                "question": log.question[:200] if log.question else "",
                "status": log.status,
                "latency_ms": log.latency_ms,
                **_summary_fields(log),
            }
            for log in logs
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{request_id}", response_model=TraceResponse)
async def get_trace(request_id: str) -> TraceResponse:
    logger.info("Trace request: request_id='{}'", request_id)

    service = TraceService()
    log = await service.get_by_request_id(request_id)

    trace_data = _as_dict(log.trace)
    result_data = _as_dict(log.result)

    steps: List[TraceStepInfo] = []

    def make_step(step_name: str, data: dict, duration_ms: int = 0) -> TraceStepInfo:
        meta = STEP_LABELS.get(step_name, {"icon": "●", "label": step_name})
        return TraceStepInfo(
            step=step_name,
            data={
                **data,
                "icon": meta["icon"],
                "label": meta["label"],
                "duration_ms": duration_ms,
            },
        )

    steps.append(make_step("question", {"question": log.question}))

    agent_trace = _as_dict(trace_data.get("agent_trace"))
    if agent_trace:
        for step_name in ["classifier", "planner", "codegen", "executor", "verifier"]:
            step_data = agent_trace.get(step_name)
            if step_data:
                duration = 0
                if isinstance(step_data, dict):
                    duration = step_data.get("duration_ms", 0) or 0
                steps.append(make_step(step_name, step_data or {}, duration))
    else:
        steps.append(make_step("retrieval", {
            "retrieved_count": trace_data.get("retrieved_count", 0),
            "retrieved_scores": trace_data.get("retrieved_scores", []),
        }))
        steps.append(make_step("verification", trace_data.get("verification", {})))

    steps.append(make_step("answer", {
        "answer": result_data.get("answer", ""),
        "status": log.status,
    }))

    return TraceResponse(
        request_id=log.request_id,
        question=log.question,
        answer=result_data.get("answer", ""),
        status=log.status,
        latency_ms=log.latency_ms,
        trace=trace_data,
        steps=steps,
        **_summary_fields(log),
    )
