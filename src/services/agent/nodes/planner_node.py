from __future__ import annotations
import json
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from src.core.db.database import async_session_maker
from src.core.db.models import ColumnMetadata, Sheet, PriceFact
from src.core.logging_settings import logger
from src.services.agent.graph_state import (
    GraphState,
    NODE_PLANNER,
)
from src.services.agent.structured_schemas import PlannerResult
from src.services.llm.llm_client import LLMClient
from src.services.llm.structured import get_structured_llm

PLANNER_SYSTEM_PROMPT = """Ты — планировщик запросов к нормализованной факт-таблице цен на металлы.

У тебя есть:
1. Вопрос пользователя
2. Список сущностей-кандидатов (item_name/supplier/sheet_period), найденных по вопросу
3. Тип запроса (lookup/aggregate/cross_sheet/delta)
4. Сущности, извлечённые из вопроса
5. Схема таблицы mart.price_facts

Твоя задача — составить текстовый план действий для генерации SQL-запроса
по таблице mart.price_facts. План должен содержать:
1. Какие условия фильтрации (WHERE) по item_name/supplier/sheet_period/price_type
2. Нужна ли агрегация (SUM/AVG/MIN/MAX) или группировка
3. Нужна ли сортировка

Правила:
- Не выдумывай значения item_name/supplier — используй только сущности-кандидаты
- Схема: mart.price_facts — единственная таблица для вопросов о ценах
- План должен быть на русском языке, кратким (3-5 предложений)

Верни ТОЛЬКО JSON-объект вида {"plan": "текст плана"} без лишних пояснений.
"""


async def get_sheet_schema(sheet_ids: List[int]) -> List[Dict[str, Any]]:
    if not sheet_ids:
        return []

    async with async_session_maker() as session:
        sheets_result = await session.execute(
            select(Sheet).where(Sheet.id.in_(sheet_ids))
        )
        sheets = sheets_result.scalars().all()
        sheet_map = {s.id: s for s in sheets}

        columns_result = await session.execute(
            select(ColumnMetadata).where(ColumnMetadata.sheet_id.in_(sheet_ids))
        )
        columns = columns_result.scalars().all()

        schema = []
        for sid in sheet_ids:
            sheet = sheet_map.get(sid)
            if not sheet:
                continue

            sheet_columns = [
                {
                    "name": col.normalized_name,
                    "original_name": col.original_name,
                    "data_type": col.data_type,
                    "sample_values": col.sample_values or [],
                }
                for col in columns
                if col.sheet_id == sid
            ]

            fact_result = await session.execute(
                select(PriceFact)
                .where(PriceFact.sheet_id == sid)
                .limit(20)
            )
            fact_rows = fact_result.scalars().all()

            fact_samples = []
            seen_items = set()
            for fp in fact_rows:
                if fp.item_name not in seen_items:
                    seen_items.add(fp.item_name)
                    fact_samples.append({
                        "item_name": fp.item_name,
                        "sheet_period": fp.sheet_period,
                        "supplier": fp.supplier,
                        "price_type": fp.price_type,
                        "value": fp.value,
                    })
                if len(fact_samples) >= 10:
                    break

            schema.append({
                "id": sheet.id,
                "name": sheet.normalized_name,
                "original_name": sheet.original_name,
                "description": sheet.description or "",
                "period": sheet.period,
                "columns": sheet_columns,
                "samples": fact_samples,
                "schema": {
                    "table": "mart.price_facts",
                    "columns": [
                        {"name": "sheet_period", "type": "TEXT", "description": "период (например, '2025-11')"},
                        {"name": "item_name", "type": "TEXT", "description": "нормализованное название лома"},
                        {"name": "supplier", "type": "TEXT", "description": "поставщик или NULL"},
                        {"name": "price_type", "type": "TEXT", "description": "среднерыночная / аукцион_старт / аукцион_победитель / поставщик"},
                        {"name": "value", "type": "FLOAT", "description": "значение цены в руб/тн"},
                    ],
                },
            })
        return schema


def _default_columns(table: str) -> List[Dict[str, str]]:
    if table == "mart.metrics":
        return [
            {"name": "period", "type": "TEXT", "description": "период (например, '2025-05')"},
            {"name": "dimension", "type": "TEXT", "description": "измерение (материал/шихта)"},
            {"name": "dimension_type", "type": "TEXT", "description": "тип измерения"},
            {"name": "metric_type", "type": "TEXT", "description": "план / факт / отклонение / percent"},
            {"name": "metric", "type": "TEXT", "description": "наименование метрики"},
            {"name": "value", "type": "FLOAT", "description": "значение метрики"},
            {"name": "is_blank", "type": "BOOL", "description": "пустая ячейка (не считать в средних)"},
        ]
    return [
        {"name": "sheet_period", "type": "TEXT", "description": "период (например, '2025-11')"},
        {"name": "item_name", "type": "TEXT", "description": "нормализованное название лома"},
        {"name": "supplier", "type": "TEXT", "description": "поставщик или None"},
        {"name": "price_type", "type": "TEXT", "description": "среднерыночная / аукцион_старт / аукцион_победитель / поставщик"},
        {"name": "value", "type": "FLOAT", "description": "значение цены в руб/тн"},
        {"name": "is_blank", "type": "BOOL", "description": "пустая ячейка (не считать в средних)"},
    ]


def _build_light_schema(schema: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Лёгкая схема для промпта планировщика (без samples и sample_values).

    Полная схема (с samples) хранится в state['schema'] для executor/codegen,
    а в LLM-промпт отправляем компактную версию — это значительно ускоряет ответ.
    """
    light = []
    for sheet in schema:
        light.append({
            "name": sheet.get("name"),
            "period": sheet.get("period"),
            "table": (sheet.get("schema") or {}).get("table"),
            "columns": [
                {"name": c.get("name"), "data_type": c.get("data_type")}
                for c in sheet.get("columns", [])
            ],
        })
    return light


async def planner_node(
    state: GraphState,
    llm: Optional[LLMClient] = None,
    **kwargs: Any,
) -> GraphState:
    llm = llm or LLMClient()
    request_id = state.get("request_id", "?")[:8]
    question = state.get("question", "")
    query_type = state.get("query_type")
    entities = state.get("entities", [])
    relevant_sheets = state.get("relevant_sheets", [])
    entity_candidates = state.get("entity_candidates", [])

    logger.info(
        "Planner Node [{}]: planning for type={}, candidates={}",
        request_id,
        query_type.value if query_type else "?",
        len(entity_candidates),
    )

    sheet_ids = [s["id"] for s in relevant_sheets]
    schema = await get_sheet_schema(sheet_ids)

    if not schema:
        # Планируем по mart-таблице даже без листов (fallback на факт-таблицу).
        domain = state.get("domain")
        table = "mart.metrics" if domain and getattr(domain, "value", None) == "metrics" else "mart.price_facts"
        logger.warning(
            "Planner Node [{}]: no schema for sheets {}, falling back to {}",
            request_id,
            sheet_ids,
            table,
        )
        schema = [
            {
                "id": None,
                "name": table,
                "schema": {
                    "table": table,
                    "columns": _default_columns(table),
                },
            }
        ]

    state["schema"] = schema

    # Лёгкая схема (без samples) для промпта — ускоряет ответ LLM.
    schema_json = json.dumps(_build_light_schema(schema), ensure_ascii=False, indent=2)
    candidates_text = json.dumps(entity_candidates[:10], ensure_ascii=False, indent=2)
    candidates_section = (
        f"\nСущности-кандидаты (item_name/supplier/sheet_period):\n{candidates_text}"
        if entity_candidates
        else ""
    )
    user_message = f"""Вопрос пользователя: {question}{candidates_section}

Тип запроса: {query_type.value if query_type else 'unknown'}
Сущности: {', '.join(entities) if entities else 'не определены'}

Схема mart.price_facts:
{schema_json}

Составь план действий для SQL-запроса по mart.price_facts."""

    messages = [
        {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    try:
        structured = get_structured_llm(PlannerResult, temperature=0.0)
        result: PlannerResult = await structured.ainvoke(messages)
        state["plan"] = (result.plan or "").strip()
        logger.info(
            "Planner Node [{}]: plan generated ({} chars)",
            request_id,
            len(state["plan"]),
        )
    except Exception as exc:
        logger.error("Planner Node [{}]: structured LLM failed: {}", request_id, exc)
        state["plan"] = f"Ошибка при генерации плана: {exc}"

    state["trace"] = state.get("trace", {})
    state["trace"][NODE_PLANNER] = {
        "plan": state["plan"],
        "schema_used": schema,
    }

    return state