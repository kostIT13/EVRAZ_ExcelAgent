from __future__ import annotations
import json
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from src.core.db.database import async_session_maker
from src.core.db.models import Sheet
from src.core.logging_settings import logger
from src.services.agent.graph_state import (
    GraphState,
    QueryType,
    NODE_CLASSIFIER,
    NODE_PLANNER,
)
from src.services.llm.llm_client import LLMClient
from src.services.entity_resolution.entity_resolver import entity_resolver

CLASSIFIER_SYSTEM_PROMPT = """Ты — классификатор запросов к базе данных Excel-файла Evraz с ценами на металлы.

У тебя есть:
1. Вопрос пользователя
2. Контекст из RAG (релевантные фрагменты данных)
3. Список листов (таблиц) в формате JSON

Твоя задача — проанализировать вопрос и вернуть JSON с полями:
1. query_type — тип запроса (lookup, aggregate, cross_sheet, delta, unknown)
2. entities — список сущностей (например, ["медь", "январь 2025"])
3. relevant_sheet_ids — список ID листов, релевантных вопросу

Правила определения query_type:
- lookup: вопрос про конкретное значение ("какая цена меди в январе?", "сколько стоит никель?")
- aggregate: вопрос про сумму, среднее, минимум, максимум
- cross_sheet: сравнение между разными листами/месяцами
- delta: разница между значениями во времени
- unknown: если не подходит ни под один из вышеперечисленных

Используй RAG-контекст для уточнения: если в контексте есть данные,
которые явно отвечают на вопрос — отметь это.

Верни ТОЛЬКО JSON без дополнительного текста.
"""


async def get_all_sheets() -> List[Dict[str, Any]]:
    async with async_session_maker() as session:
        result = await session.execute(
            select(Sheet.id, Sheet.normalized_name, Sheet.description)
        )
        sheets = []
        for row in result.all():
            sheets.append({
                "id": row.id,
                "name": row.normalized_name,
                "description": row.description or "",
            })
        return sheets


async def classifier_node(
    state: GraphState,
    llm: Optional[LLMClient] = None,
    **kwargs: Any,
) -> GraphState:
    llm = llm or LLMClient()
    request_id = state.get("request_id", "?")[:8]
    question = state.get("question", "")

    logger.info(
        "Classifier Node [{}]: classifying '{}'",
        request_id,
        question[:80],
    )

    sheets = await get_all_sheets()
    logger.info(
        "Classifier Node [{}]: found {} sheets",
        request_id,
        len(sheets),
    )

    # Entity-resolution: top-N кандидатов item/supplier/period по вопросу.
    # Заменяет тяжёлый RAG-over-cells; кандидаты передаются в Planner/CodeGen.
    try:
        candidates = await entity_resolver.resolve_candidates(question, top_n=10)
        state["entity_candidates"] = [c.to_dict() for c in candidates]
    except Exception as exc:
        logger.warning(
            "Classifier Node [{}]: entity resolution failed: {}",
            request_id,
            exc,
        )
        state["entity_candidates"] = []

    sheets_json = json.dumps(sheets, ensure_ascii=False, indent=2)
    candidates_text = json.dumps(
        state.get("entity_candidates", [])[:5],
        ensure_ascii=False,
        indent=2,
    )
    entity_section = (
        f"\nСущности-кандидаты (pg_trgm):\n{candidates_text}"
        if state.get("entity_candidates")
        else ""
    )
    user_message = f"""Вопрос пользователя: {question}{entity_section}

Список листов в базе данных:
{sheets_json}

Определи тип запроса, сущности и ID релевантных листов. Используй
сущности-кандидаты, чтобы уточнить названия лома/поставщиков."""

    messages = [
        {"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    try:
        raw_response = await llm.chat(
            messages=messages,
            model=None,
            temperature=0.1,
            max_tokens=1024,
        )

        cleaned = raw_response.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        result = json.loads(cleaned)

        query_type_str = result.get("query_type", "unknown")
        if query_type_str not in ("lookup", "aggregate", "cross_sheet", "delta", "unknown"):
            query_type_str = "unknown"

        state["query_type"] = QueryType(query_type_str)
        state["entities"] = result.get("entities", [])

        sheet_map = {s["id"]: s for s in sheets}
        relevant_ids = result.get("relevant_sheet_ids", [])
        state["relevant_sheets"] = [
            sheet_map[sid] for sid in relevant_ids if sid in sheet_map
        ]

        logger.info(
            "Classifier Node [{}]: type={}, entities={}, sheets={}",
            request_id,
            state["query_type"].value,
            state["entities"],
            [s["name"] for s in state["relevant_sheets"]],
        )

    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.error(
            "Classifier Node [{}]: failed to parse LLM response: {}",
            request_id,
            exc,
        )
        state["query_type"] = QueryType.UNKNOWN
        state["entities"] = []
        state["relevant_sheets"] = []

    state["trace"] = state.get("trace", {})
    state["trace"][NODE_CLASSIFIER] = {
        "query_type": state["query_type"].value,
        "entities": state["entities"],
        "relevant_sheets": state["relevant_sheets"],
    }

    return state