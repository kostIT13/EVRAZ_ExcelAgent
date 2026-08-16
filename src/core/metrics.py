from __future__ import annotations
from typing import Dict, List
from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from fastapi import Response

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

FAILED_TOTAL = Counter("evraz_failed_total", "Число запросов со статусом failed")
LOW_CONFIDENCE_TOTAL = Counter(
    "evraz_low_confidence_total", "Число запросов со статусом low_confidence"
)

LLM_TOKENS = Counter(
    "evraz_llm_tokens_total", "Потреблённые токены LLM", ["node", "kind"]
)

LLM_COST_RUB = Counter(
    "evraz_llm_cost_rub_total", "Оценочная стоимость LLM-вызовов (руб.)", ["node"]
)

RUB_PER_1K_PROMPT = 0.15
RUB_PER_1K_COMPLETION = 0.60


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
    if kind == "prompt":
        LLM_COST_RUB.labels(node=node).inc((count / 1000.0) * RUB_PER_1K_PROMPT)
    elif kind == "completion":
        LLM_COST_RUB.labels(node=node).inc((count / 1000.0) * RUB_PER_1K_COMPLETION)


def _counter_values(metric) -> List[tuple]:
    out: List[tuple] = []
    for m in metric.collect():
        for s in m.samples:
            if s.name.endswith("_created"):
                continue
            out.append((dict(s.labels), float(s.value)))
    return out


def _histogram_sum_count(metric) -> tuple[float, float]:
    s = 0.0
    c = 0.0
    for m in metric.collect():
        for smp in m.samples:
            if smp.name.endswith("_sum"):
                s = float(smp.value)
            elif smp.name.endswith("_count"):
                c = float(smp.value)
    return s, c


def metrics_summary() -> dict:
    ask_by_status: Dict[str, float] = {}
    for labels, value in _counter_values(ASK_REQUESTS):
        ask_by_status[labels.get("status", "unknown")] = value

    tokens_by_node: Dict[str, Dict[str, float]] = {}
    for labels, value in _counter_values(LLM_TOKENS):
        node = labels.get("node", "llm")
        kind = labels.get("kind", "prompt")
        tokens_by_node.setdefault(node, {})
        tokens_by_node[node][kind] = value

    cost_by_node: Dict[str, float] = {}
    for labels, value in _counter_values(LLM_COST_RUB):
        cost_by_node[labels.get("node", "llm")] = value

    total_tokens = sum(sum(v.values()) for v in tokens_by_node.values())
    total_cost = sum(cost_by_node.values())
    total_requests = sum(ask_by_status.values())

    lat_sum, lat_count = _histogram_sum_count(ASK_LATENCY)
    avg_latency_ms = round((lat_sum / lat_count) * 1000, 1) if lat_count else 0.0

    return {
        "total_requests": int(total_requests),
        "requests_by_status": {k: int(v) for k, v in ask_by_status.items()},
        "avg_latency_ms": avg_latency_ms,
        "total_tokens": int(total_tokens),
        "tokens_by_node": {
            k: {kk: int(vv) for kk, vv in v.items()} for k, v in tokens_by_node.items()
        },
        "total_cost_rub": round(total_cost, 4),
        "cost_by_node": {k: round(v, 4) for k, v in cost_by_node.items()},
    }


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)