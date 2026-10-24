from __future__ import annotations
from typing import Dict, List
from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

ASK_INFLIGHT = Gauge(
    "evraz_ask_inflight",
    "Запросы /ask, находящиеся в обработке прямо сейчас",
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


def observe_ask_start() -> None:
    """Отметить начало обработки /ask (gauge in-flight)."""
    try:
        ASK_INFLIGHT.inc()
    except Exception:
        pass


def observe_ask_finish() -> None:
    """Отметить окончание обработки /ask (gauge in-flight)."""
    try:
        ASK_INFLIGHT.dec()
    except Exception:
        pass


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


def _histogram_quantile(metric, q: float = 0.95) -> float:
    """Расчёт квантиля по гистограмме (аналог histogram_quantile)."""
    buckets: list[tuple[float, float]] = []
    total = 0.0
    s = 0.0
    for m in metric.collect():
        for smp in m.samples:
            name = smp.name
            if name.endswith("_bucket"):
                le = smp.labels.get("le", "+Inf")
                buckets.append((float("inf") if le == "+Inf" else float(le), float(smp.value)))
            elif name.endswith("_sum"):
                s = float(smp.value)
            elif name.endswith("_count"):
                total = float(smp.value)
    if not buckets or total <= 0:
        return s / total if total else 0.0
    target = q * total
    prev_le, prev_cum = 0.0, 0.0
    for le, c in sorted(buckets):
        if c >= target and c - prev_cum > 0:
            frac = (target - prev_cum) / (c - prev_cum)
            return prev_le + (le - prev_le) * frac
        prev_le, prev_cum = le, c
    return prev_le


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
    success_requests = ask_by_status.get("success", 0.0)

    lat_sum, lat_count = _histogram_sum_count(ASK_LATENCY)
    avg_latency_ms = round((lat_sum / lat_count) * 1000, 1) if lat_count else 0.0
    p95_ms = round(_histogram_quantile(ASK_LATENCY, 0.95) * 1000, 1)
    p50_ms = round(_histogram_quantile(ASK_LATENCY, 0.50) * 1000, 1)

    return {
        "total_requests": int(total_requests),
        "requests_by_status": {k: int(v) for k, v in ask_by_status.items()},
        "success_rate": round(100.0 * success_requests / total_requests, 1)
        if total_requests
        else 0.0,
        "avg_latency_ms": avg_latency_ms,
        "latency_p95_ms": p95_ms,
        "latency_p50_ms": p50_ms,
        "inflight": int(ASK_INFLIGHT._value.get()),
        "total_tokens": int(total_tokens),
        "tokens_by_node": {
            k: {kk: int(vv) for kk, vv in v.items()} for k, v in tokens_by_node.items()
        },
        "total_cost_rub": round(total_cost, 4),
        "cost_by_node": {k: round(v, 4) for k, v in cost_by_node.items()},
    }


async def metrics_history(hours: int = 24) -> dict:
    """Почасовые ряды метрик из query_logs (для тайм-серий во frontend).

    Возвращает: labels (ISO-таргументы начала часа), requests, by_status,
    avg_latency_ms, latency_p50_ms, latency_p95_ms.
    """
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from src.core.db.database import async_session_maker
    from src.core.db.models import QueryLog

    hours = max(1, min(int(hours), 24 * 7))
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    since = now - timedelta(hours=hours - 1)

    async with async_session_maker() as session:
        rows = (
            await session.execute(
                select(QueryLog)
                .where(QueryLog.created_at >= since)
                .order_by(QueryLog.created_at.asc())
            )
        ).scalars().all()

    labels: List[str] = []
    requests: List[int] = []
    by_status: Dict[str, List[int]] = {}
    avg_latency_ms: List[float] = []
    latency_p50_ms: List[float] = []
    latency_p95_ms: List[float] = []

    # час строки -> индекс бакета
    bucket_of = {}
    for i in range(hours):
        ts = since + timedelta(hours=i)
        labels.append(ts.isoformat())
        bucket_of[ts] = i
        requests.append(0)
        avg_latency_ms.append(0.0)
        latency_p50_ms.append(0.0)
        latency_p95_ms.append(0.0)

    lat_by_bucket: Dict[int, List[int]] = {i: [] for i in range(hours)}
    for row in rows:
        raw_created = row.created_at
        created = (
            raw_created
            if raw_created.tzinfo is not None
            else raw_created.replace(tzinfo=timezone.utc)
        )
        hour_start = created.replace(minute=0, second=0, microsecond=0)
        idx = int((hour_start - since).total_seconds() // 3600)
        if idx < 0 or idx >= hours:
            continue
        status = row.status or "unknown"
        by_status.setdefault(status, [0] * hours)[idx] += 1
        requests[idx] += 1
        lat_by_bucket[idx].append(row.latency_ms or 0)

    # Процентили по часам + средние.
    for idx, lats in lat_by_bucket.items():
        if not lats:
            continue
        lats_sorted = sorted(lats)
        n = len(lats_sorted)
        avg_latency_ms[idx] = round(sum(lats_sorted) / n, 1)
        latency_p50_ms[idx] = float(lats_sorted[min(n - 1, int(0.50 * n))])
        latency_p95_ms[idx] = float(lats_sorted[min(n - 1, int(0.95 * n))])

    return {
        "period_hours": hours,
        "labels": labels,
        "requests": requests,
        "by_status": by_status,
        "avg_latency_ms": avg_latency_ms,
        "latency_p50_ms": latency_p50_ms,
        "latency_p95_ms": latency_p95_ms,
    }


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)