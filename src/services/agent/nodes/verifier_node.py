"""Verifier Node — узел верификации в графе LangGraph.

Проверяет SQL, а не текст ответа:
1. Semantic-проверка SQL: соответствует ли он query_type/entities (LLM-critic)
2. Sanity-checks на результат: пустой result, все NULL, аномальный размер набора
3. Детерминированное форматирование ответа из sql_result (без LLM-пересказа)
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from src.core.logging_settings import logger
from src.services.agent.graph_state import GraphState, NODE_VERIFIER
from src.services.llm.llm_client import LLMClient

VERIFIER_SYSTEM_PROMPT = """Ты — верификатор SQL-запросов для базы данных Excel-файла с ценами на металлы.

У тебя есть:
1. Исходный вопрос пользователя
2. Тип запроса (lookup/aggregate/cross_sheet/delta)
3. Сущности, извлечённые из вопроса
4. Сгенерированный SQL-запрос

Твоя задача — проверить, правильно ли SQL отвечает на вопрос пользователя.
Проверяй SQL, а не данные! Ты проверяешь логику запроса.

Верни JSON с полями:
1. "is_correct": true/false — правильно ли SQL отвечает на вопрос
2. "confidence": число от 0.0 до 1.0 — насколько ты уверен
3. "issues": список проблем, если есть (пустой массив если всё ок)
4. "needs_retry": true/false — нужно ли перегенерировать SQL
5. "retry_reason": причина retry (если needs_retry=true), например:
   - "wrong_table" — не тот лист/таблица
   - "wrong_column" — не та колонка
   - "wrong_aggregation" — не та агрегация (SUM вместо AVG и т.д.)
   - "missing_filter" — не хватает фильтра (WHERE)
   - "wrong_filter" — неправильный фильтр
   - "missing_join" — не хватает JOIN
   - "syntax_error" — синтаксическая ошибка

Правила проверки:
- Если тип запроса aggregate — SQL должен содержать агрегатную функцию (SUM/AVG/MIN/MAX/COUNT)
- Если тип запроса delta — SQL должен вычислять разницу между значениями
- Если тип запроса cross_sheet — SQL должен обращаться к нескольким листам
- Если в entities есть конкретные названия — SQL должен их фильтровать
- SQL должен использовать правильные имена таблиц и колонок
- Не будь излишне строгим к синтаксису — сосредоточься на семантике

Верни ТОЛЬКО JSON без дополнительного текста.
"""

# Максимальное количество retry
MAX_RETRY_COUNT = 3

# Пороги для sanity checks
MAX_ROWS_WARNING = 1000  # если больше этого числа строк — возможно, не хватает фильтра
MIN_CONFIDENCE_PASS = 0.5


def _format_result_deterministically(sql_result: List[Dict[str, Any]], max_rows: int = 10) -> str:
    """Детерминированно форматирует sql_result в читаемый ответ.

    Без LLM — чисто шаблонное форматирование.
    """
    if not sql_result:
        return "Данные не найдены."

    rows = sql_result[:max_rows]
    total = len(sql_result)

    # Определяем колонки
    columns = list(rows[0].keys()) if rows else []

    # Форматируем как таблицу
    lines = []
    for row in rows:
        parts = []
        for col in columns:
            val = row.get(col)
            if val is None:
                continue
            # Пытаемся красиво отформатировать числа
            if isinstance(val, float):
                if val == int(val):
                    val_str = f"{int(val):,}".replace(",", " ")
                else:
                    val_str = f"{val:,.2f}".replace(",", " ")
            else:
                val_str = str(val)
            parts.append(f"{col}: {val_str}")
        if parts:
            lines.append("; ".join(parts))

    result = "\n".join(lines)

    if total > max_rows:
        result += f"\n\n... и ещё {total - max_rows} строк(и)"

    return result


def _sanity_check_result(sql_result: List[Dict[str, Any]]) -> List[str]:
    """Sanity checks на результат SQL."""
    issues: List[str] = []

    if not sql_result:
        issues.append("empty_result")
        return issues

    # Проверка на аномальный размер
    if len(sql_result) > MAX_ROWS_WARNING:
        issues.append(f"large_result:{len(sql_result)}")

    # Проверка на NULL-значения
    if sql_result:
        first_row = sql_result[0]
        all_nulls = all(v is None for v in first_row.values())
        if all_nulls:
            issues.append("all_null_values")

    return issues


async def verifier_node(
    state: GraphState,
    llm: Optional[LLMClient] = None,
    **kwargs: Any,
) -> GraphState:
    """Узел Verifier: проверяет SQL и результат.

    Args:
        state: Состояние с заполненными question, sql_query, sql_result.
        llm: LLMClient.

    Returns:
        Обновлённое состояние с answer, confidence, needs_retry.
    """
    llm = llm or LLMClient()
    request_id = state.get("request_id", "?")[:8]
    question = state.get("question", "")
    query_type = state.get("query_type")
    entities = state.get("entities", [])
    sql_query = state.get("sql_query", "")
    sql_result = state.get("sql_result", [])
    sql_error = state.get("sql_error")
    retry_count = state.get("retry_count", 0)

    logger.info(
        "Verifier Node [{}]: verifying SQL+result (retry #{})",
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

    # 2. Sanity checks на результат
    sanity_issues = _sanity_check_result(sql_result)
    if "empty_result" in sanity_issues:
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
            "sanity_issues": sanity_issues,
        }
        return state

    # 3. Semantic-проверка SQL через LLM-critic
    try:
        user_message = f"""Вопрос пользователя: {question}

Тип запроса: {query_type.value if query_type else 'unknown'}
Сущности: {', '.join(entities) if entities else 'не определены'}

SQL-запрос:
{sql_query}

Результат запроса ({len(sql_result)} строк):
{json.dumps(sql_result[:5], ensure_ascii=False, indent=2, default=str)}

Проверь, правильно ли SQL отвечает на вопрос пользователя."""

        messages = [
            {"role": "system", "content": VERIFIER_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

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
        llm_confidence = float(result.get("confidence", 0.0))
        issues = result.get("issues", [])
        state["needs_retry"] = result.get("needs_retry", not is_correct)
        state["retry_reason"] = result.get("retry_reason", "")

        # 4. Детерминированное форматирование ответа
        state["answer"] = _format_result_deterministically(sql_result)

        # 5. Итоговая confidence: комбинируем LLM-оценку и sanity checks
        confidence = llm_confidence
        if "large_result" in sanity_issues:
            confidence *= 0.8  # штраф за аномально большой результат
        if "all_null_values" in sanity_issues:
            confidence *= 0.5  # серьёзный штраф за NULL-значения

        state["confidence"] = max(0.0, min(1.0, confidence))

        # Инкрементируем retry_count только если нужен retry
        if state["needs_retry"]:
            state["retry_count"] = retry_count + 1
        else:
            state["retry_count"] = retry_count

        logger.info(
            "Verifier Node [{}]: correct={}, confidence={:.2f}, needs_retry={}, issues={}",
            request_id,
            is_correct,
            state["confidence"],
            state["needs_retry"],
            issues,
        )

        state["trace"] = state.get("trace", {})
        state["trace"][NODE_VERIFIER] = {
            "is_correct": is_correct,
            "confidence": state["confidence"],
            "needs_retry": state["needs_retry"],
            "retry_reason": state["retry_reason"],
            "issues": issues,
            "sanity_issues": sanity_issues,
        }

    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.error(
            "Verifier Node [{}]: failed to parse LLM response: {}",
            request_id,
            exc,
        )
        # Fallback: детерминированное форматирование
        state["answer"] = _format_result_deterministically(sql_result)
        state["confidence"] = 0.5
        state["needs_retry"] = False
        state["retry_reason"] = ""
        state["trace"] = state.get("trace", {})
        state["trace"][NODE_VERIFIER] = {
            "error": str(exc),
            "fallback": True,
        }

    return state