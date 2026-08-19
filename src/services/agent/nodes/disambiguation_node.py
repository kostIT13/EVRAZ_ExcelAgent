from __future__ import annotations
import json
from typing import Any, List, Optional
from langgraph.types import Command, interrupt

from src.core.logging_settings import logger
from src.services.agent.graph_state import GraphState, QueryType, NODE_DISAMBIGUATION, NODE_PLANNER
from src.services.agent.structured_schemas import DisambiguationResult
from src.services.llm.llm_client import LLMClient
from src.services.llm.structured import get_structured_llm

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

Верни строго JSON-объект с полями:
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
):
    request_id = state.get("request_id", "?")[:8]
    question = state.get("question", "")
    query_type = state.get("query_type")
    entities = list(state.get("entities", []))

    logger.info(
        "Disambiguation Node [{}]: checking '{}'",
        request_id,
        question[:80],
    )

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

    needs_disambiguation = False
    ambiguity_type = None
    clarifying_question = ""
    options: List[str] = []
    suggested_resolution = None

    try:
        structured = get_structured_llm(DisambiguationResult, temperature=0.0)
        result: DisambiguationResult = await structured.ainvoke(messages)

        needs_disambiguation = result.needs_disambiguation
        ambiguity_type = result.ambiguity_type
        clarifying_question = result.clarifying_question
        options = result.options or []
        suggested_resolution = result.suggested_resolution

        logger.info(
            "Disambiguation Node [{}]: needs={}, type={}, auto_resolved={}",
            request_id,
            needs_disambiguation,
            ambiguity_type,
            bool(suggested_resolution) if needs_disambiguation else False,
        )
    except Exception as exc:
        logger.error(
            "Disambiguation Node [{}]: structured LLM failed: {}",
            request_id,
            exc,
        )
        needs_disambiguation = False

    base_trace = dict(state.get("trace", {}))
    base_trace[NODE_DISAMBIGUATION] = {
        "needs_disambiguation": needs_disambiguation,
        "ambiguity_type": ambiguity_type,
        "clarifying_question": clarifying_question,
        "options": options,
    }

    # --- Ветвление -----------------------------------------------------
    # 1) Неоднозначность можно разрешить автоматически.
    if needs_disambiguation and suggested_resolution:
        if suggested_resolution not in entities:
            entities.append(suggested_resolution)
        return Command(
            goto=NODE_PLANNER,
            update={
                "entities": entities,
                "disambiguation_needed": False,
                "disambiguation_info": {
                    "ambiguity_type": ambiguity_type,
                    "clarifying_question": clarifying_question,
                    "options": options,
                    "suggested_resolution": suggested_resolution,
                },
                "trace": base_trace,
            },
        )

    # 2) Нужен уточняющий вопрос — приостанавливаем граф через interrupt().
    if needs_disambiguation:
        user_choice = interrupt(
            {
                "question": clarifying_question
                or "Уточните, пожалуйста, что именно вас интересует:",
                "options": options or AVAILABLE_PRICE_SOURCES,
            }
        )
        user_choice_text = (
            user_choice if isinstance(user_choice, str) else json.dumps(user_choice, ensure_ascii=False)
        )
        if user_choice_text and user_choice_text not in entities:
            entities.append(user_choice_text)
        return Command(
            goto=NODE_PLANNER,
            update={
                "entities": entities,
                "disambiguation_needed": False,
                "user_resolution": user_choice_text,
                "disambiguation_info": {
                    "ambiguity_type": ambiguity_type,
                    "clarifying_question": clarifying_question,
                    "options": options or AVAILABLE_PRICE_SOURCES,
                    "user_choice": user_choice_text,
                },
                "trace": {
                    **base_trace,
                    "user_resolution": user_choice_text,
                },
            },
        )

    # 3) Неоднозначности нет — идём дальше без изменений.
    return Command(
        goto=NODE_PLANNER,
        update={
            "disambiguation_needed": False,
            "disambiguation_info": state.get("disambiguation_info", {}),
            "trace": base_trace,
        },
    )