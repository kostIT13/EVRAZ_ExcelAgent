from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from src.core.db.database import async_session_maker
from src.core.db.models import Sheet
from src.core.logging_settings import logger
from src.services.agent.state import AgentState, QueryType, AgentStep
from src.services.llm.llm_client import LLMClient

CLASSIFIER_SYSTEM_PROMPT = """Ты - классификатор запросов к базе данных Excel-файла Evraz с ценами на металлы

У тебя есть список листов (таблиц) в формате JSON. Каждый лист содержит:
- id: уникальный id
- name: название листа (например, "январь 2025", "февраль 2025")
- description: описание содержимого листа

Твоя задача - проанализировать вопрос пользователя и вернуть JSON с полями:
1. query_type - тип запроса (один из lookup, aggregate, cross_sheet, delta, unknown)
2. entities - список сущностей, упомянутых в вопросе (например, ["медь", "январь 2025"])
3. relevant_sheet_ids - список ID листов, которые релевантны вопросу

Правила определения query_type:
- lookup: вопрос про конкретное значение ("какая цена меди в январе?", "сколько стоит никель?")
- aggregate: вопрос про сумму, среднее, минимум, максимум ("найди максимальную цену", "средняя цена по всем месяцам")
- cross_sheet: сравнение между разными листами/месяцами ("сравни цены января и февраля", "как менялась цена меди по месяцам")
- delta: разница между значениями ("на сколько изменилась цена никеля с января по февраль?", "прирост цены")
- unknown: если не подходит ни под один из вышеперечисленных

Верни ТОЛЬКО JSON без дополнительного текста.
"""

CLASSIFIER_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "query_type": {
            "type": "string",
            "enum": ["lookup", "aggregate", "cross_sheet", "delta", "unknown"],
        },
        "entities": {
            "type": "array",
            "items": {"type": "string"},
        },
        "relevant_sheet_ids": {
            "type": "array",
            "items": {"type": "integer"},
        },
    },
    "required": ["query_type", "entities", "relevant_sheet_ids"],
}

async def get_all_sheets() -> List[Dict[str, Any]]:
    """Получить список всех листов из БД"""
    async with async_session_maker() as session:
        from sqlalchemy import select
        
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
    

async def classifier_step(state: AgentState, llm: Optional[LLMClient] = None) -> AgentState:
    """Шаг Classifier: определяет тип запроса и релевантные листы
    Args:
        state: Текущее состояние агента.
        llm: LLMClient (создаётся по умолчанию, если не передан).

    Returns:
        AgentState с заполненными query_type, entities, relevant_sheets.
    """
    llm = llm or LLMClient()
    logger.info(
        "Classifier [{}]: classifying question '{}",
        state.request_id[:8],
        state.question[:80],
    )
    
    # 1. Получаем список всех листов
    sheets = await get_all_sheets()
    logger.info(
        "Classifier [{}]: found {} sheets in DB",
        state.request_id[:8],
        len(sheets),
    )
    
    # 2. Формируем наш промпт
    sheets_json = json.dumps(sheets, ensure_ascii=False, indent=2)
    user_message = f"""Вопрос пользователя: {state.question}

Список листов в базе данных:
{sheets_json}

Определи тип запроса, сущности и ID релевантных листов."""

    messages = [
        {"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]
    
    # 3. Выызываем LLM с парсингом JSON
    try:
        raw_response = await llm.chat(
            messages=messages,
            model=None,
            temperature=0.1,
            max_tokens=1024
        )
        
        # Пробуем распарсить JSON из ответа
        # LLM может вернуть JSON как есть или обернуть в ```json ... ```
        cleaned = raw_response.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        result = json.loads(cleaned)
        
        # 4. Валидируем наш ответ
        query_type_str = result.get("query_type", "unknown")
        if query_type_str not in ("lookup", "aggregate", "cross_sheet", "delta", "unknown"):
            query_type_str = "unknown"
            
        state.query_type = QueryType(query_type_str)
        state.entities = result.get("entities", [])
        
        # Маппим ID листов на полные объекты
        sheet_map = {s["id"]: s for s in sheets}
        relevant_ids = result.get("relevant_sheet_ids", [])
        state.relevant_sheets = [
            sheet_map[sid] for sid in relevant_ids if sid in sheet_map
        ]
        logger.info(
            "Classifier [{}]: type={}, entities={}, sheets={}",
            state.request_id[:8],
            state.query_type.value,
            state.entities,
            [s["name"] for s in state.relevant_sheets],
        )
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.error(
            "Classifier [{}]: failed to parse LLM response: {}. Raw: {}",
            state.request_id[:8],
            exc,
            raw_response if 'raw_response' in dir() else "N/A",
        )
        state.query_type = QueryType.UNKNOWN
        state.entities = []
        state.relevant_sheets = []
        
    # 5. Сохраняем trace(след)
    state.trace["classifier"] = {
        "query_type": state.query_type.value,
        "entities": state.entities,
        "relevant_sheets": state.relevant_sheets,
    }
    
    state.current_step = AgentStep.PLANNER
    return state