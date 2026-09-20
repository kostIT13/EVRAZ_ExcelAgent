"""
Прогон golden-датасета через LangGraph-агента и отчёт по качеству.

Скрипт даёт живую метрику точности (pass rate) для презентации:
каждый вопрос из tests/golden_questions.json прогоняется через агента,
проверяется статус ответа, соответствие SQL-сигнатуре (expected_sql_hint)
и типу результата (expected_result_type).

Использование:
    python scripts/run_golden_report.py                 # полный прогон
    python scripts/run_golden_report.py --limit 5       # только первые N вопросов
    python scripts/run_golden_report.py --json out/golden_report.json
    python scripts/run_golden_report.py --top-k 30      # больше релевантных листов

Требования:
  - запущенная PostgreSQL со схемой (alembic upgrade head);
  - данные загружены (python scripts/load_demo_data.py);
  - LLM_* переменные окружения настроены в .env.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GOLDEN_PATH = ROOT / "tests" / "golden_questions.json"


def _run_async(coro):
    """asyncio.run() с совместимым event loop для Windows (psycopg)."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(coro)

# --- Проверки SQL-сигнатуры (зеркалируют tests/test_golden_dataset.py) -------


def _check_sql_signature(sql: str, hint: str) -> bool:
    """Проверяет, что сгенерированный SQL соответствует golden-хинту."""
    sql_lower = sql.lower()
    hint_lower = hint.lower().strip()

    if "from sheets" in hint_lower:
        if "from sheets" not in sql_lower and "from public.sheets" not in sql_lower:
            return False
        table_clause = " from sheets"
    elif "metric_type" in hint_lower or "dimension" in hint_lower:
        if "metrics" not in sql_lower:
            return False
        table_clause = ""
    else:
        if "price_facts" not in sql_lower:
            return False
        table_clause = ""

    clean = hint_lower.replace(table_clause, "")
    required_parts = [p.strip() for p in clean.split(" and ") if p.strip()]
    for part in required_parts:
        in_match = re.fullmatch(r"([a-z_]+)\s+in\s*\((.+)\)", part)
        if in_match:
            col = in_match.group(1)
            values = re.findall(r"'([^']*)'", in_match.group(2))
            if values and all(f"{col}='{v}'" in sql_lower for v in values):
                continue
        if part not in sql_lower:
            return False
    return True


def _check_result_type(result: List[Dict[str, Any]], expected: str) -> bool:
    if expected == "scalar":
        return len(result) == 1
    if expected == "multirow":
        return len(result) >= 1
    if expected in ("aggregate", "delta"):
        return len(result) >= 1
    return True


# --- Прогон -------------------------------------------------------------------


def load_golden() -> List[Dict[str, Any]]:
    with open(GOLDEN_PATH, encoding="utf-8") as fh:
        return json.load(fh)


async def run_one(agent: Any, item: Dict[str, Any], top_k: int) -> Dict[str, Any]:
    started = time.monotonic()
    try:
        result = await agent.run(question=item["question"], top_k=top_k)
    except Exception as exc:  # noqa: BLE001 — отчёт должен пережить сбой одного вопроса
        return {
            "id": item["id"],
            "question": item["question"],
            "query_type": item.get("query_type"),
            "domain": item.get("domain"),
            "status": "failed",
            "error": str(exc)[:500],
            "latency_ms": int((time.monotonic() - started) * 1000),
            "sql_hint_ok": False,
            "result_type_ok": False,
            "passed": False,
        }

    hint = item.get("expected_sql_hint", "")
    expected_type = item.get("expected_result_type", "")
    sql_hint_ok = _check_sql_signature(result.sql_query, hint) if hint else None
    result_type_ok = _check_result_type(result.sql_result, expected_type) if expected_type else None

    status_ok = result.status in ("success", "low_confidence")
    passed = status_ok and sql_hint_ok is not False and result_type_ok is not False

    return {
        "id": item["id"],
        "question": item["question"],
        "query_type": item.get("query_type"),
        "domain": item.get("domain"),
        "status": result.status,
        "confidence": round(result.confidence, 3),
        "retry_count": result.retry_count,
        "latency_ms": result.latency_ms,
        "sql": result.sql_query,
        "sql_hint_ok": sql_hint_ok,
        "result_type_ok": result_type_ok,
        "passed": passed,
    }


def _print_report(rows: List[Dict[str, Any]]) -> None:
    total = len(rows)
    passed = sum(1 for r in rows if r["passed"])
    failed = total - passed
    rate = passed / total * 100 if total else 0.0

    print("=" * 72)
    print("GOLDEN DATASET REPORT")
    print("=" * 72)
    print(f"Всего: {total} | Прошло: {passed} | Провалено: {failed} | Pass rate: {rate:.1f}%")
    print()

    by_type: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "passed": 0})
    by_domain: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "passed": 0})
    by_status: Counter = Counter()
    for r in rows:
        by_type[r["query_type"]]["total"] += 1
        by_type[r["query_type"]]["passed"] += int(r["passed"])
        by_domain[r["domain"]]["total"] += 1
        by_domain[r["domain"]]["passed"] += int(r["passed"])
        by_status[r["status"]] += 1

    print("По типам запросов:")
    for t, s in sorted(by_type.items()):
        r = s["passed"] / s["total"] * 100 if s["total"] else 0
        print(f"  {t:<18} {s['passed']:>3}/{s['total']:<3} ({r:5.1f}%)")
    print()
    print("По доменам:")
    for d, s in sorted(by_domain.items()):
        r = s["passed"] / s["total"] * 100 if s["total"] else 0
        print(f"  {d:<10} {s['passed']:>3}/{s['total']:<3} ({r:5.1f}%)")
    print()
    print("Статусы агента:", dict(by_status))
    print()

    bad = [r for r in rows if not r["passed"]]
    if bad:
        print("Проваленные вопросы:")
        for r in bad:
            reasons = []
            if r.get("error"):
                reasons.append(f"error={r['error'][:120]}")
            if r["status"] not in ("success", "low_confidence"):
                reasons.append(f"status={r['status']}")
            if r.get("sql_hint_ok") is False:
                reasons.append("SQL не соответствует hint")
            if r.get("result_type_ok") is False:
                reasons.append("тип результата не совпал")
            print(f"  {r['id']} [{r['query_type']}/{r['domain']}] "
                  f"{'; '.join(reasons)} ({r['latency_ms']} ms)")
        print()
    print(f"Итог: {rate:.1f}% ({passed}/{total})")
    print("=" * 72)


async def main(args: argparse.Namespace) -> int:
    items = load_golden()
    if args.limit:
        items = items[: args.limit]

    from src.services.agent.graph import langgraph_agent

    print(f"Прогон {len(items)} golden-вопросов через LangGraph-агента...")
    rows: List[Dict[str, Any]] = []
    for i, item in enumerate(items, 1):
        row = await run_one(langgraph_agent, item, top_k=args.top_k)
        rows.append(row)
        marker = "OK " if row["passed"] else "FAIL"
        print(f"[{i:>2}/{len(items)}] {marker} {row['id']} "
              f"({row['query_type']}/{row['domain']}) "
              f"status={row['status']} {row['latency_ms']} ms")

    print()
    _print_report(rows)

    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        summary = {
            "total": len(rows),
            "passed": sum(1 for r in rows if r["passed"]),
            "failed": sum(1 for r in rows if not r["passed"]),
            "pass_rate": round(sum(1 for r in rows if r["passed"]) / len(rows) * 100, 1)
            if rows else 0.0,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "rows": rows,
        }
        out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Отчёт сохранён: {out}")

    return 0 if all(r["passed"] for r in rows) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Прогон golden-датасета и отчёт по точности")
    parser.add_argument("--limit", type=int, default=0, help="Прогнать только первые N вопросов")
    parser.add_argument("--top-k", type=int, default=10, help="Количество релевантных листов (top_k)")
    parser.add_argument("--json", type=str, default="", help="Путь для JSON-отчёта")
    return parser


if __name__ == "__main__":
    sys.exit(_run_async(main(build_parser().parse_args())))