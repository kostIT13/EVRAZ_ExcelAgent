"""Verifier Node — узел верификации ответа в графе LangGraph.

Проверяет, отвечает ли результат SQL-запроса на исходный вопрос.
Если нет — возвращает причину для retry.
"""

from __future__ import annotations

import json
from typing import Optional

from src.core.logging_settings import logger
from src.services.agent.graph_state import GraphState, NODE_VERIFIER
from src.services.llm.llm_client import LLMClient

VERIFIER_SYSTEM_PROMPT = """Ты — верификатор ответов на вопросы по Excel-файлу с ценами на металлы.

У тебя есть:
1. Исходный вопрос пользователя
2. RAG-контекст (релевантные данные из Excel)
3. SQL-запрос, который был выполнен
4. Результат SQL-запроса (таблица с данными)

Твоя задача — проверить, отвечает ли результат на вопрос пользователя.

Верни JSON с полями:
1. "is_correct": true/false — отвечает ли результат на вопрос
2. "confidence": число от 0.0 до 1.0 — насколько ты уверен
3. "answer": человекочитаемый ответ на русском языке (всегда, даже если is_correct=false, напиши что пошло не так)
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
- ЕСЛИ В РЕЗУЛЬТАТЕ ЕСТЬ ДАННЫЕ, КОТОРЫЕ ОТВЕЧАЮТ НА ВОПРОС — is_correct=true, сформируй ответ
- Не будь излишне строгим: если в результате есть число, похожее на цену, и оно соответствует вопросу — считай ответ правильным
- Если SQL-запрос содержит ошибку — needs_retry=true
- Не выдумывай данные, которых нет в результате
- Сверяйся с RAG-контекстом: если результат совпадает с контекстом — это подтверждение правильности
- Если не уверен — лучше is_correct=true с низким confidence, чем ложный retry
- Всегда заполняй answer: если ответ правильный — напиши его понятно, если нет — объясни проблему

Верни ТОЛЬКО JSON без дополнительного текста.
"""

# Максимальное количество retry
MAX_RETRY_COUNT = 3


async def verifier_node(
    state: GraphState,
    llm: Optional[LLMClient] = None,
) -> GraphState:
    """Узел Verifier: проверяет, отвечает ли результат на вопрос.

    Args:
        state: Состояние с заполненными question, sql_query, sql_result,
               rag_context.
        llm: LLMClient.

    Returns:
        Обновлённое состояние с answer, confidence, retry_count, needs_retry.
    """
    llm = llm or LLMClient()
    request_id = state.get("request_id", "?")[:8]
    question = state.get("question", "")
    sql_query = state.get("sql_query", "")
    sql_result = state.get("sql_result", [])
    sql_error = state.get("sql_error")
    rag_context = state.get("rag_context", "")
    retry_count = state.get("retry_count", 0)

    logger.info(
        "Verifier Node [{}]: verifying result (retry #{})",
        request_id,
        retry_count,
    )

    # 1. Если SQL-ошибка — сразу retry
    if sql_error:
        state["answer"] = f"Ошибка при выполнении запроса: {sql_error}"
        state["confidence"] = 0.0
        state["needs_retry"] = True
        state["retry_reason"] = f"sql_error: {sql_error}"
        state["retry_count"] = retry_count + 1

        state["trace"] = state.get("trace", {})
        state["trace"][NODE_VERIFIER] = {
            "is_correct": False,
            "confidence": 0.0,
            "needs_retry": True,
            "retry_reason": state["retry_reason"],
        }
        return state

    # 2. Если результат пустой
    if not sql_result:
        state["answer"] = "Запрос не вернул данных."
        state["confidence"] = 0.0
        state["needs_retry"] = True
        state["retry_reason"] = "empty_result"
        state["retry_count"] = retry_count + 1

        state["trace"] = state.get("trace", {})
        state["trace"][NODE_VERIFIER] = {
            "is_correct": False,
            "confidence": 0.0,
            "needs_retry": True,
            "retry_reason": "empty_result",
        }
        return state

    # 3. Формируем промпт для LLM
    result_preview = json.dumps(
        sql_result[:20],
        ensure_ascii=False,
        indent=2,
        default=str,
    )
    rag_section = (
        f"\nRAG-контекст (релевантные данные):\n{rag_context[:2000]}"
        if rag_context
        else ""
    )
    user_message = f"""Вопрос пользователя: {question}{rag_section}

SQL-запрос:
{sql_query}

Результат запроса ({len(sql_result)} строк):
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
        state["confidence"] = float(result.get("confidence", 0.0))
        state["answer"] = result.get("answer", "")
        state["needs_retry"] = result.get("needs_retry", not is_correct)
        state["retry_reason"] = result.get("retry_reason", "")

        if state["needs_retry"]:
            state["retry_count"] = retry_count + 1
        else:
            state["retry_count"] = retry_count

        logger.info(
            "Verifier Node [{}]: correct={}, confidence={:.2f}, needs_retry={}",
            request_id,
            is_correct,
            state["confidence"],
            state["needs_retry"],
        )

        state["trace"] = state.get("trace", {})
        state["trace"][NODE_VERIFIER] = {
            "is_correct": is_correct,
            "confidence": state["confidence"],
            "needs_retry": state["needs_retry"],
            "retry_reason": state["retry_reason"],
        }

    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.error(
            "Verifier Node [{}]: failed to parse LLM response: {}",
            request_id,
            exc,
        )
        # Fallback: отдаём сырой результат
        state["answer"] = json.dumps(
            sql_result[:10],
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        state["confidence"] = 0.5
        state["needs_retry"] = False
        state["retry_reason"] = ""
        state["trace"] = state.get("trace", {})
        state["trace"][NODE_VERIFIER] = {
            "error": str(exc),
            "fallback": True,
        }

    return state