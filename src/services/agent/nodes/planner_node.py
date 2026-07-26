"""Planner Node — узел планирования в графе LangGraph.

На основе вопроса, RAG-контекста и схемы релевантных листов
генерирует текстовый план действий для CodeGen.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from src.core.db.database import async_session_maker
from src.core.db.models import ColumnMetadata, Sheet
from src.core.logging_settings import logger
from src.services.agent.graph_state import (
    GraphState,
    NODE_PLANNER,
)
from src.services.llm.llm_client import LLMClient

PLANNER_SYSTEM_PROMPT = """Ты — планировщик запросов к базе данных Excel-файла с ценами на металлы.

У тебя есть:
1. Вопрос пользователя
2. RAG-контекст (релевантные фрагменты данных из Excel)
3. Тип запроса (lookup/aggregate/cross_sheet/delta)
4. Сущности, извлечённые из вопроса
5. Схема релевантных листов (таблиц) с их колонками

Твоя задача — составить текстовый план действий для генерации SQL-запроса.
План должен быть конкретным и содержать:
1. Какие листы (таблицы) нужно использовать
2. Какие колонки нужны для ответа
3. Какие условия фильтрации (WHERE)
4. Нужна ли агрегация (SUM/AVG/MIN/MAX) или группировка
5. Нужна ли сортировка

Правила:
- Не выдумывай колонки — используй только те, что есть в схеме
- Если тип запроса cross_sheet или delta — нужны несколько листов
- Для delta нужна разница между значениями из разных листов/периодов
- Используй RAG-контекст чтобы понять, какие именно данные искать
- План должен быть на русском языке, кратким (3-5 предложений)

Верни ТОЛЬКО текст плана без лишних пояснений.
"""


async def get_sheet_schema(sheet_ids: List[int]) -> List[Dict[str, Any]]:
    """Получить схему колонок для указанных листов.

    Возвращает две секции для каждого листа:
    1. generic_schema — колонки из column_metadata (исходная структура Excel)
    2. fact_prices_schema — нормализованная факт-таблица с примерами данных
    """
    if not sheet_ids:
        return []

    async with async_session_maker() as session:
        from sqlalchemy import select

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

            # Получаем sample-данные из fact_prices для этого листа
            from src.core.db.models import FactPrice
            fact_result = await session.execute(
                select(FactPrice)
                .where(FactPrice.sheet_id == sid)
                .limit(20)
            )
            fact_rows = fact_result.scalars().all()

            # Группируем fact_prices по item_name_normalized для компактности
            fact_samples = []
            seen_items = set()
            for fp in fact_rows:
                if fp.item_name_normalized not in seen_items:
                    seen_items.add(fp.item_name_normalized)
                    fact_samples.append({
                        "item_name_normalized": fp.item_name_normalized,
                        "period": fp.period,
                        "price_source": fp.price_source,
                        "price_value": fp.price_value,
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
                "fact_prices_samples": fact_samples,
                "fact_prices_schema": {
                    "table": "fact_prices",
                    "columns": [
                        {"name": "period", "type": "TEXT", "description": "период (например, '2025-11')"},
                        {"name": "item_name_normalized", "type": "TEXT", "description": "нормализованное название лома"},
                        {"name": "price_source", "type": "TEXT", "description": "источник цены: среднерыночная, аукцион_старт, аукцион_победитель, или название поставщика"},
                        {"name": "price_value", "type": "FLOAT", "description": "значение цены в руб/тн"},
                    ],
                },
            })
        return schema


async def planner_node(
    state: GraphState,
    llm: Optional[LLMClient] = None,
    **kwargs: Any,
) -> GraphState:
    """Узел Planner: генерирует текстовый план действий.

    Args:
        state: Состояние с заполненными question, query_type, entities,
               relevant_sheets, rag_context.
        llm: LLMClient.

    Returns:
        Обновлённое состояние с plan.
    """
    llm = llm or LLMClient()
    request_id = state.get("request_id", "?")[:8]
    question = state.get("question", "")
    query_type = state.get("query_type")
    entities = state.get("entities", [])
    relevant_sheets = state.get("relevant_sheets", [])
    rag_context = state.get("rag_context", "")

    logger.info(
        "Planner Node [{}]: planning for type={}, sheets={}",
        request_id,
        query_type.value if query_type else "?",
        [s.get("name", str(s)) for s in relevant_sheets],
    )

    # 1. Получаем схему
    sheet_ids = [s["id"] for s in relevant_sheets]
    schema = await get_sheet_schema(sheet_ids)

    if not schema:
        logger.warning(
            "Planner Node [{}]: no schema for sheets {}",
            request_id,
            sheet_ids,
        )
        state["plan"] = "Не найдена схема релевантных листов"
        state["trace"] = state.get("trace", {})
        state["trace"][NODE_PLANNER] = {"error": "no_schema", "sheet_ids": sheet_ids}
        return state

    # 2. Сохраняем схему в state для CodeGen (напрямую, не через trace)
    state["schema"] = schema

    # 3. Формируем промпт с RAG-контекстом
    schema_json = json.dumps(schema, ensure_ascii=False, indent=2)
    rag_section = (
        f"\nRAG-контекст (релевантные данные):\n{rag_context[:20000]}"
        if rag_context
        else ""
    )
    user_message = f"""Вопрос пользователя: {question}{rag_section}

Тип запроса: {query_type.value if query_type else 'unknown'}
Сущности: {', '.join(entities) if entities else 'не определены'}

Схема релевантных листов:
{schema_json}

Составь план действий для SQL-запроса."""

    messages = [
        {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    # 3. Вызываем LLM
    try:
        plan = await llm.chat(
            messages=messages,
            model=None,
            temperature=0.1,
            max_tokens=1024,
        )
        state["plan"] = plan.strip()
        logger.info(
            "Planner Node [{}]: plan generated ({} chars)",
            request_id,
            len(state["plan"]),
        )
    except Exception as exc:
        logger.error("Planner Node [{}]: LLM failed: {}", request_id, exc)
        state["plan"] = f"Ошибка при генерации плана: {exc}"

    # 4. Trace
    state["trace"] = state.get("trace", {})
    state["trace"][NODE_PLANNER] = {
        "plan": state["plan"],
        "schema_used": schema,
    }

    return state