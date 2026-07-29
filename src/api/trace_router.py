from __future__ import annotations
from typing import List
from fastapi import APIRouter, Query
from src.api.schemas import TraceResponse, TraceStepInfo
from src.core.logging_settings import logger
from src.services.db_tables.query_log_service.service import TraceService


router = APIRouter(prefix="/trace", tags=["traceability"])


@router.get("", response_model=List[dict])
async def list_traces(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> List[dict]:
    logger.info("List traces: limit={}, offset={}", limit, offset)

    service = TraceService()
    logs = await service.list_all(skip=offset, limit=limit)

    return [
        {
            "request_id": log.request_id,
            "question": log.question[:200] if log.question else "",
            "status": log.status,
            "latency_ms": log.latency_ms,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]


@router.get("/{request_id}", response_model=TraceResponse)
async def get_trace(request_id: str) -> TraceResponse:
    logger.info("Trace request: request_id='{}'", request_id)

    service = TraceService()
    log = await service.get_by_request_id(request_id)

    trace_data = log.trace or {}
    result_data = log.result or {}

    steps = []

    steps.append(TraceStepInfo(
        step="question",
        data={"question": log.question},
    ))

    agent_trace = trace_data.get("agent_trace", {})
    if agent_trace:
        for step_name in ["classifier", "planner", "codegen", "executor", "verifier"]:
            step_data = agent_trace.get(step_name)
            if step_data:
                steps.append(TraceStepInfo(step=step_name, data=step_data))
    else:
        steps.append(TraceStepInfo(
            step="retrieval",
            data={
                "retrieved_count": trace_data.get("retrieved_count", 0),
                "retrieved_scores": trace_data.get("retrieved_scores", []),
            },
        ))
        steps.append(TraceStepInfo(
            step="verification",
            data=trace_data.get("verification", {}),
        ))

    steps.append(TraceStepInfo(
        step="answer",
        data={
            "answer": result_data.get("answer", ""),
            "status": log.status,
        },
    ))

    return TraceResponse(
        request_id=log.request_id,
        question=log.question,
        answer=result_data.get("answer", ""),
        status=log.status,
        latency_ms=log.latency_ms,
        trace=trace_data,
        steps=steps,
    )
