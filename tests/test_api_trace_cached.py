from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import trace_router


def _log(agent_trace):
    """Запись журнала: ответ отдан из кэша (latency_ms — попадание в кэш)."""
    return SimpleNamespace(
        request_id="req-cache",
        question="Какая цена на медь?",
        status="success",
        latency_ms=18,
        sql_query="SELECT 1",
        error_message=None,
        created_at=None,
        result={"answer": "ответ", "confidence": 1.0},
        trace={
            "agent_trace": agent_trace,
            "query_type": "lookup",
            "sql_query": "SELECT 1",
            "retry_count": 0,
        },
    )


def _client(monkeypatch, log):
    class _StubTraceService:
        def __init__(self, session=None):
            pass

        async def get_by_request_id(self, request_id):
            return log

    monkeypatch.setattr(trace_router, "TraceService", _StubTraceService)
    app = FastAPI()
    app.include_router(trace_router.router)
    return TestClient(app)


CACHED_NODES = {
    "from_cache": True,
    "cached_sql": "SELECT 1",
    "source_request_id": "req-src",
    "source_latency_ms": 31000,
    "classifier": {"query_type": "lookup", "duration_ms": 800},
    "planner": {"steps": ["…"], "duration_ms": 400},
    "codegen": {"sql": "SELECT 1", "duration_ms": 21000},
    "executor": {"row_count": 1, "duration_ms": 90},
    "verifier": {"confidence": 0.98, "duration_ms": 120},
}


def test_cached_trace_lists_all_agent_nodes(monkeypatch):
    body = _client(monkeypatch, _log(CACHED_NODES)).get("/trace/req-cache").json()
    steps = body["steps"]

    assert [s["step"] for s in steps] == [
        "question",
        "cache",
        "classifier",
        "planner",
        "codegen",
        "executor",
        "verifier",
        "answer",
    ]
    assert steps[2]["data"]["duration_ms"] == 800


def test_cached_trace_marks_cache_and_source_run(monkeypatch):
    body = _client(monkeypatch, _log(CACHED_NODES)).get("/trace/req-cache").json()
    cache_step = next(s for s in body["steps"] if s["step"] == "cache")

    assert body["from_cache"] is True
    assert body["source_latency_ms"] == 31000
    assert body["latency_ms"] == 18
    assert cache_step["data"]["source_request_id"] == "req-src"
    assert cache_step["data"]["node_trace_stored"] is True


def test_old_cached_row_without_snapshot_still_marks_cache(monkeypatch):
    """Строки кэша, записанные до снимка узлов: шагов агента нет, флаг — есть."""
    body = (
        _client(monkeypatch, _log({"from_cache": True, "cached_sql": "SELECT 1"}))
        .get("/trace/req-cache")
        .json()
    )
    steps = body["steps"]

    assert [s["step"] for s in steps] == ["question", "cache", "answer"]
    assert body["from_cache"] is True
    assert body["source_latency_ms"] == 0
    assert next(s for s in steps if s["step"] == "cache")["data"][
        "node_trace_stored"
    ] is False


def test_plain_trace_has_no_cache_step(monkeypatch):
    body = (
        _client(monkeypatch, _log({"classifier": {"query_type": "lookup"}}))
        .get("/trace/req-cache")
        .json()
    )

    assert [s["step"] for s in body["steps"]] == [
        "question",
        "classifier",
        "answer",
    ]
    assert body["from_cache"] is False
