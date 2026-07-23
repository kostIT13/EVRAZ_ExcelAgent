# """
# Что делает Planner:

# Берёт вопрос + query_type + entities + relevant_sheets из AgentState (заполненные Classifier'ом)
# Для каждого релевантного листа получает схему колонок из БД
# Отправляет в LLM вопрос + схему листов
# LLM возвращает текстовый план действий (что искать, какие колонки, какие условия)
# Planner сохраняет план в state.plan
# """

# """Planner — LLM-планировщик.

# На основе вопроса и схемы релевантных листов генерирует
# текстовый план действий для CodeGen.
# """

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from src.core.db.database import async_session_maker
from src.core.db.models import ColumnMetadata, Sheet
from src.core.logging_settings import logger
from src.services.agent.state import AgentState, AgentStep
from src.services.llm.llm_client import LLMClient

PLANNER_SYSTEM_PROMPT = """Ты — планировщик запросов к базе данных Excel-файла с ценами на металлы.

У тебя есть:
1. Вопрос пользователя
2. Тип запроса (lookup/aggregate/cross_sheet/delta)
3. Сущности, извлечённые из вопроса
4. Схема релевантных листов (таблиц) с их колонками

Схема листа содержит:
- id листа
- название листа (например, "январь_2025")
- колонки: имя, тип данных (price/date/number/text/id), примеры значений

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
- План должен быть на русском языке, кратким (3-5 предложений)

Верни ТОЛЬКО текст плана без лишних пояснений.
"""

async def get_sheet_schema(sheet_ids: List[int]) -> List[Dict[str, Any]]:
    """ПОлучить схему колонок для указанных листов"""
    if not sheet_ids:
        return []
    
    async with async_session_maker() as session:
        from sqlalchemy import select
        
        # Получаем листы
        sheets_result = await session.execute(
            select(Sheet).where(Sheet.id.in_(sheet_ids))
        )
        sheets = sheets_result.scalars().all()
        sheet_map = {s.id: s for s in sheets}
        
        # Получаем колонки для этих листов
        columns_result = await session.execute(
            select(ColumnMetadata).where(ColumnMetadata.sheet_id.in_(sheet_ids))
        )
        columns = columns_result.scalars().all()
        
        # Групперуем колонки по листам
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
            
            schema.append({
                "id": sheet.id,
                "name": sheet.normalized_name,
                "original_name": sheet.original_name,
                "description": sheet.description or "",
                "columns": sheet_columns,
            })
        return schema
    
async def planner_step(state: AgentState, llm: Optional[LLMClient] = None) -> AgentState:
    """Шаг Planner: генерирует текстовый план действий.

    Args:
        state: Текущее состояние агента (должен быть заполнен classifier'ом).
        llm: LLMClient (создаётся по умолчанию, если не передан).

    Returns:
        AgentState с заполненным plan.
    """
    llm = llm or LLMClient()
    logger.info(
        "Planner [{}]: planning for type={}, sheets={}",
        state.request_id[:8],
        state.query_type.value,
        [s.get("name", str(s)) for s in state.relevant_sheets],
    )
    
    # 1. Получаем схему релевантных листов
    sheet_ids = [s["id"] for s in state.relevant_sheets]
    schema = await get_sheet_schema(sheet_ids)
    
    if not schema:
        logger.warning(
            "Planner [{}]: no schema found for sheets {}",
            state.request_id[:8],
            sheet_ids,
        )
        state.plan = "Не найдена схема релевантных листов"
        state.trace["planner"] = {"error": "no_schema", "sheet_ids": sheet_ids}
        state.current_step = "planner"
        return state
    
    # 2. Формируем промпт
    schema_json = json.dumps(schema, ensure_ascii=False, indent=2)
    user_message = f"""Вопрос пользователя: {state.question}

Тип запроса: {state.query_type.value}
Сущности: {', '.join(state.entities) if state.entities else 'не определены'}

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

        state.plan = plan.strip()

        logger.info(
            "Planner [{}]: plan generated ({} chars)",
            state.request_id[:8],
            len(state.plan),
        )

    except Exception as exc:
        logger.error(
            "Planner [{}]: LLM call failed: {}",
            state.request_id[:8],
            exc,
        )
        state.plan = f"Ошибка при генерации плана: {exc}"

    # 4. Сохраняем trace
    state.trace["planner"] = {
        "plan": state.plan,
        "schema_used": schema,
    }

    state.current_step = AgentStep.CODEGEN
    return state