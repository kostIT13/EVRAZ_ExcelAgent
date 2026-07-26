"""Disambiguation Node — узел разрешения неоднозначностей в графе LangGraph.

Если вопрос пользователя содержит неоднозначные термины (например, "цена меди" —
это среднерыночная, конкретный поставщик или итог аукциона?), узел задаёт
уточняющий вопрос, а не гадает.

Встраивается между Classifier и Planner.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from src.core.logging_settings import logger
from src.services.agent.graph_state import GraphState, QueryType, NODE_DISAMBIGUATION
from src.services.llm.llm_client import LLMClient

DISAMBIGUATION_SYSTEM_PROMPT = """Ты — узел разрешения неоднозначностей для вопросов по Excel-файлу с ценами на металлы.

У тебя есть:
1. Вопрос пользователя
2. Тип запроса (lookup/aggregate/cross_sheet/delta)
3. Сущности, извлечённые из вопроса
4. Список доступных источников цены

Твоя задача — определить, нуждается ли вопрос в уточнении.
Неоднозначность возникает, когда:
- Спрашивают "цена" без уточнения источника (среднерыночная/поставщик/аукцион)
- Спрашивают про "медь" без уточнения типа лома (кусок/стружка/гранулы)
- Не указан период/месяц
- Указано несколько возможных периодов

Верни JSON с полями:
1. "needs_disambiguation": true/false — нуждается ли вопрос в уточнении
2. "ambiguity_type": тип неоднозначности (или null):
   - "price_source" — не указан источник цены
   - "item_type" — не указан тип лома
   - "period" — не указан период
   - "multiple_periods" — указано несколько периодов
   - "multiple_items" — указано несколько материалов
3. "clarifying_question": вопрос для уточнения (на русском, если needs_disambiguation=true)
4. "options": список вариантов для уточнения (если needs_disambiguation=true)
5. "suggested_resolution": если неоднозначность можно разрешить автоматически —
   предложение (например, "среднерыночная" как источник по умолчанию)

Правила:
- Если вопрос явно указывает источник ("среднерыночная цена", "цена поставщика",
  "стартовая цена аукциона") — неоднозначности нет
- Если вопрос явно указывает период ("в январе", "за декабрь") — неоднозначности нет
- Если вопрос содержит конкретное название ("Лом меди кусок") — неоднозначности нет
- Если неоднозначность можно разумно разрешить автоматически (например,
  "цена меди" → скорее всего среднерыночная) — предложи suggested_resolution
- Если неоднозначность серьёзная — установи needs_disambiguation=true

Верни ТОЛЬКО JSON без дополнительного текста.
"""

# Доступные источники цены для подсказок
AVAILABLE_PRICE_SOURCES = [
    "среднерыночная",
    "аукцион_старт (стартовая цена аукциона)",
    "аукцион_победитель (цена победителя аукциона)",
    "поставщик (конкретная организация)",
]


async def disambiguation_node(
    state: GraphState,
    llm: Optional[LLMClient] = None,
    **kwargs: Any,
) -> GraphState:
    """Узел Disambiguation: проверяет вопрос на неоднозначность.

    Args:
        state: Состояние с заполненными question, query_type, entities.
        llm: LLMClient.

    Returns:
        Обновлённое состояние с disambiguation_result.
    """
    llm = llm or LLMClient()
    request_id = state.get("request_id", "?")[:8]
    question = state.get("question", "")
    query_type = state.get("query_type")
    entities = state.get("entities", [])

    logger.info(
        "Disambiguation Node [{}]: checking '{}'",
        request_id,
        question[:80],
    )

    # Формируем промпт
    user_message = f"""Вопрос пользователя: {question}

Тип запроса: {query_type.value if query_type else 'unknown'}
Сущности: {', '.join(entities) if entities else 'не определены'}

Доступные источники цены:
{chr(10).join(f'- {s}' for s in AVAILABLE_PRICE_SOURCES)}

Определи, нуждается ли вопрос в уточнении."""

    messages = [
        {"role": "system", "content": DISAMBIGUATION_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    try:
        raw_response = await llm.chat(
            messages=messages,
            model=None,
            temperature=0.1,
            max_tokens=1024,
        )

        # Парсим JSON
        cleaned = raw_response.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        result = json.loads(cleaned)

        needs_disambiguation = result.get("needs_disambiguation", False)
        ambiguity_type = result.get("ambiguity_type")
        clarifying_question = result.get("clarifying_question", "")
        options = result.get("options", [])
        suggested_resolution = result.get("suggested_resolution")

        # Сохраняем результат disambiguation в state
        state["disambiguation_needed"] = needs_disambiguation
        state["disambiguation_info"] = {
            "ambiguity_type": ambiguity_type,
            "clarifying_question": clarifying_question,
            "options": options,
            "suggested_resolution": suggested_resolution,
        }

        # Если есть suggested_resolution и неоднозначность не критична —
        # автоматически разрешаем
        if needs_disambiguation and suggested_resolution:
            logger.info(
                "Disambiguation Node [{}]: auto-resolving with '{}'",
                request_id,
                suggested_resolution,
            )
            # Добавляем suggested_resolution в entities для контекста
            if suggested_resolution not in entities:
                entities.append(suggested_resolution)
                state["entities"] = entities
            state["disambiguation_needed"] = False  # auto-resolved

        logger.info(
            "Disambiguation Node [{}]: needs={}, type={}, auto_resolved={}",
            request_id,
            needs_disambiguation,
            ambiguity_type,
            bool(suggested_resolution) if needs_disambiguation else False,
        )

    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.error(
            "Disambiguation Node [{}]: failed to parse LLM response: {}",
            request_id,
            exc,
        )
        state["disambiguation_needed"] = False
        state["disambiguation_info"] = {}

    # Trace
    state["trace"] = state.get("trace", {})
    state["trace"][NODE_DISAMBIGUATION] = {
        "needs_disambiguation": state.get("disambiguation_needed", False),
        "disambiguation_info": state.get("disambiguation_info", {}),
    }

    return state