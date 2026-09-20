from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

# Windows: psycopg несовместим с ProactorEventLoop (asyncio.run по умолчанию).
# На Linux/macOS дефолтная политика подходит и без этого блока.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

GOLDEN_PATH = Path(__file__).parent / "golden_questions.json"


def _load_golden() -> List[Dict[str, Any]]:
    with open(GOLDEN_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _check_sql_signature(sql: str, hint: str) -> bool:
    """Проверяет, что сгенерированный SQL соответствует golden-хинту.

    Хинт — набор частей, разделённых AND; каждая часть должна присутствовать
    в нормализованном SQL. Целевая таблица определяется автоматически:
      - ``FROM sheets``              → таблица ``sheets``;
      - ``metric_type``/``dimension`` → витрина ``mart.metrics``;
      - иначе                         → витрина ``mart.price_facts``.

    Конструкции вида ``col IN ('a','b')`` дополнительно считаются выполненными,
    если SQL содержит обе формы ``col='a'`` и ``col='b'`` (агент может
    сгенерировать эквивалентный OR-вариант вместо IN).
    """
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
    # hint уже приведён к нижнему регистру, поэтому разделитель — ' and '.
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


@pytest.mark.golden
@pytest.mark.parametrize("item", _load_golden(), ids=lambda it: it["id"])
def test_golden_question(item: Dict[str, Any]):
    from src.services.agent.graph import langgraph_agent

    async def _run():
        return await langgraph_agent.run(question=item["question"], top_k=10)

    agent_result = asyncio.run(_run())

    sql = agent_result.sql_query
    hint = item.get("expected_sql_hint", "")
    assert agent_result.status in ("success", "low_confidence"), (
        f"Golden {item['id']} failed with status {agent_result.status}: {agent_result.trace}"
    )
    if hint:
        assert _check_sql_signature(sql, hint), (
            f"Golden {item['id']}: SQL '{sql}' не соответствует hint '{hint}'"
        )
    if item.get("expected_result_type"):
        assert _check_result_type(agent_result.sql_result, item["expected_result_type"]), (
            f"Golden {item['id']}: result type mismatch"
        )


def test_golden_json_valid():
    items = _load_golden()
    assert 30 <= len(items) <= 50, (
        f"Golden dataset должен содержать 30-50 вопросов, сейчас {len(items)}"
    )
    seen_ids: set[str] = set()
    for it in items:
        assert it.get("id") and it.get("question") and it.get("query_type")
        assert it["id"] not in seen_ids, f"Дублирующийся id golden-вопроса: {it['id']}"
        seen_ids.add(it["id"])
        assert it.get("expected_sql_hint"), f"Golden {it['id']}: отсутствует expected_sql_hint"
        assert it.get("expected_result_type"), f"Golden {it['id']}: отсутствует expected_result_type"


def test_sql_signature_helper():
    # price_facts
    assert _check_sql_signature(
        "SELECT value FROM mart.price_facts WHERE price_type='среднерыночная' "
        "AND item_name ILIKE '%медь%' AND sheet_period='2025-01'",
        "price_type='среднерыночная' AND item_name ILIKE '%медь%' AND sheet_period='2025-01'",
    )
    assert not _check_sql_signature(
        "SELECT * FROM raw.cells", "item_name ILIKE '%медь%'"
    )
    # sheets
    assert _check_sql_signature(
        "SELECT COUNT(*) AS cnt FROM sheets",
        "COUNT(*) FROM sheets",
    )
    assert _check_sql_signature(
        "SELECT COUNT(*) AS cnt FROM public.sheets",
        "COUNT(*) FROM sheets",
    )
    # metrics
    assert _check_sql_signature(
        "SELECT value FROM mart.metrics WHERE metric_type='план' AND dimension ILIKE '%медь%'",
        "metric_type='план' AND dimension ILIKE '%медь%'",
    )
    # IN-форма в SQL
    assert _check_sql_signature(
        "SELECT value FROM mart.price_facts "
        "WHERE sheet_period IN ('2025-03','2025-04') AND item_name ILIKE '%бронз%'",
        "sheet_period IN ('2025-03','2025-04') AND item_name ILIKE '%бронз%'",
    )
    # OR-форма в SQL тоже валидна для IN-хинта
    assert _check_sql_signature(
        "SELECT value FROM mart.price_facts "
        "WHERE (sheet_period='2025-03' OR sheet_period='2025-04') AND item_name ILIKE '%бронз%'",
        "sheet_period IN ('2025-03','2025-04') AND item_name ILIKE '%бронз%'",
    )