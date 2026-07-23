# """Что делает Verifier:

# Берёт вопрос + SQL-запрос + результат выполнения
# Отправляет в LLM — проверяет, отвечает ли результат на вопрос
# Если ответ правильный — LLM генерирует человекочитаемый ответ и confidence score
# Если ответ неправильный — Verifier возвращает needs_retry=true с описанием проблемы
# Оркестратор решает, делать retry (до 3 раз) или завершать
# """

# """Verifier — LLM-проверка ответа.

# Проверяет, отвечает ли результат SQL-запроса на исходный вопрос.
# Если нет — возвращает причину для retry (нужно повторить попытку).
# """

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from src.core.logging_settings import logger
from src.services.agent.state import AgentState, AgentStep
from src.services.llm.llm_client import LLMClient

VERIFIER_SYSTEM_PROMPT = """Ты — верификатор ответов на вопросы по Excel-файлу с ценами на металлы.

У тебя есть:
1. Исходный вопрос пользователя
2. SQL-запрос, который был выполнен
3. Результат SQL-запроса (таблица с данными)

Твоя задача — проверить, отвечает ли результат на вопрос пользователя.

Верни JSON с полями:
1. "is_correct": true/false — отвечает ли результат на вопрос
2. "confidence": число от 0.0 до 1.0 — насколько ты уверен
3. "answer": человекочитаемый ответ на русском языке (если is_correct=true)
4. "needs_retry": true/false — нужно ли перегенерировать SQL
5. "retry_reason": причина retry (если needs_retry=true), например:
   - "wrong_sheet" — не тот лист
   - "wrong_column" — не та колонка
   - "wrong_aggregation" — не та агрегация
   - "missing_filter" — не хватает фильтра
   - "incomplete_result" — неполный результат
   - "sql_error" — ошибка выполнения SQL

Правила:
- Если результат пустой — скорее всего needs_retry=true
- Если в результате есть нужные данные — сформируй понятный ответ на русском
- Если SQL-запрос содержит ошибку — needs_retry=true
- Не выдумывай данные, которых нет в результате

Верни ТОЛЬКО JSON без дополнительного текста.
"""

VERIFIER_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "is_correct": {"type": "boolean"},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "answer": {"type": "string"},
        "needs_retry": {"type": "boolean"},
        "retry_reason": {"type": "string"},
    },
    "required": ["is_correct", "confidence", "answer", "needs_retry"],
}
# Максимальное количество retry
MAX_RETRY_COUNT = 3


async def verifier_step(state: AgentState, llm: Optional[LLMClient] = None) -> AgentState:
    """Шаг Verifier: проверяет, отвечает ли результат на вопрос
    
    Args:
        state: Текущее состояние агента (должен быть заполнен executor'ом).
        llm: LLMClient (создаётся по умолчанию, если не передан).

    Returns:
        AgentState с заполненными answer, confidence, retry_count.
    """
    llm = llm or LLMClient()
    logger.info(
        "Verifier [{}]: verifying result (retry #{})",
        state.request_id[:8],
        state.retry_count,
    )
    
    # 1. Если SQL-ошибка - сразу retry
    if state.sql_error:
        state.answer = f"Ошибка при выполнении запроса: {state.sql_error}"
        state.confidence = 0.0
        
        state.trace["verifier"] = {
            "is_correct": False,
            "confidence": 0.0,
            "needs_retry": True,
            "retry_reason": f"sql_error: {state.sql_error}",
        }
        state.retry_count += 1
        if state.retry_count < MAX_RETRY_COUNT:
            state.current_step = AgentStep.CODEGEN
        else:
            state.current_step = AgentStep.DONE
        return state
    
    # 2. Если результат пустой
    if not state.sql_result:
        state.answer = "Запрос не вернул данных."
        state.confidence = 0.0

        state.trace["verifier"] = {
            "is_correct": False,
            "confidence": 0.0,
            "needs_retry": True,
            "retry_reason": "empty_result",
        }

        state.retry_count += 1
        if state.retry_count < MAX_RETRY_COUNT:
            state.current_step = AgentStep.CODEGEN
        else:
            state.current_step = AgentStep.DONE
        return state
    
    # 3. Формируем промпт для LLM
    result_preview = json.dumps(
        state.sql_result[:20],  # первые 20 строк
        ensure_ascii=False,
        indent=2,
        default=str,
    )
    
    user_message = f"""Вопрос пользователя: {state.question}

SQL-запрос:
{state.sql_query}

Результат запроса ({len(state.sql_result)} строк):
{result_preview}

Проверь, отвечает ли результат на вопрос пользователя."""

    messages = [
        {"role": "system", "content": VERIFIER_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]
    
    # 4. Вызываем LLM
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

        is_correct = result.get("is_correct", False)
        state.confidence = float(result.get("confidence", 0.0))
        state.answer = result.get("answer", "")
        needs_retry = result.get("needs_retry", not is_correct)
        retry_reason = result.get("retry_reason", "")

        logger.info(
            "Verifier [{}]: correct={}, confidence={:.2f}, needs_retry={}",
            state.request_id[:8],
            is_correct,
            state.confidence,
            needs_retry,
        )
        
        # Сохраняем trace
        state.trace["verifier"] = {
            "is_correct": is_correct,
            "confidence": state.confidence,
            "needs_retry": needs_retry,
            "retry_reason": retry_reason,
        }
        
        # 5. Определяем следующий шаг
        if needs_retry and state.retry_count < MAX_RETRY_COUNT:
            state.retry_count += 1
            state.current_step = AgentStep.CODEGEN  # retry → назад к CodeGen
            logger.info(
                "Verifier [{}]: retry #{}/{} → codegen",
                state.request_id[:8],
                state.retry_count,
                MAX_RETRY_COUNT,
            )
        else:
            state.current_step = AgentStep.DONE  # готово
            
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.error(
            "Verifier [{}]: failed to parse LLM response: {}",
            state.request_id[:8],
            exc,
        )
        # Если не смогли распарсить — считаем, что ответ правильный
        # (лучше отдать результат, чем ничего)
        state.answer = json.dumps(
            state.sql_result[:10],
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        state.confidence = 0.5
        state.trace["verifier"] = {
            "error": str(exc),
            "fallback": True,
        }
        state.current_step = AgentStep.DONE

    return state