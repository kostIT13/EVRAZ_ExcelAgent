"""Prometheus-метрики для наблюдаемости агента.

Ведём счётчики и гистограммы для:
- RPS и латентности /ask запросов (по статусу: success/low_confidence/failed);
- per-node latency графа (classifier/planner/codegen/executor/verifier/answer);
- LLM token usage / стоимости (заполняется в nodes через LLMClient usage).

Используем prometheus-client без внешних серверов — /metrics отдаёт
FastAPI-эндпоинт в формате Prometheus.
"""
from __future__ import annotations

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from fastapi import Response


# RPS и статусы ответов агента.
ASK_REQUESTS = Counter(
    "evraz_ask_requests_total",
    "Всего запросов /ask по статусу",
    ["status"],
)
ASK_LATENCY = Histogram(
    "evraz_ask_latency_seconds",
    "Латентность /ask (гистограмма)",
    buckets=(0.5, 1, 2, 5, 10, 30, 60, 120),
)

# Per-node latency графа.
NODE_LATENCY = Histogram(
    "evraz_node_latency_seconds",
    "Латентность по узлам графа",
    ["node"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60),
)

# Доля failed / low_confidence.
FAILED_TOTAL = Counter("evraz_failed_total", "Число запросов со статусом failed")
LOW_CONFIDENCE_TOTAL = Counter(
    "evraz_low_confidence_total", "Число запросов со статусом low_confidence"
)

# LLM token usage / стоимость.
LLM_TOKENS = Counter(
    "evraz_llm_tokens_total", "Потреблённые токены LLM", ["node", "kind"]
)


def observe_ask(status: str, latency_s: float) -> None:
    ASK_REQUESTS.labels(status=status).inc()
    ASK_LATENCY.observe(latency_s)
    if status == "failed":
        FAILED_TOTAL.inc()
    elif status == "low_confidence":
        LOW_CONFIDENCE_TOTAL.inc()


def observe_node(node: str, latency_s: float) -> None:
    NODE_LATENCY.labels(node=node).observe(latency_s)


def observe_llm_tokens(node: str, kind: str, count: float) -> None:
    LLM_TOKENS.labels(node=node, kind=kind).inc(count)


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)