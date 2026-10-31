from __future__ import annotations
import json
from typing import Any, Dict, Optional
from src.core.logging_settings import logger
from src.services.agent.graph_state import GraphState, NODE_ANSWER
from src.services.agent.prompts import build_memory_context
from src.services.llm.llm_client import LLMClient

ANSWER_SYSTEM_PROMPT = """Ты — финальный ассистент по данным о ценах на цветной лом.

У тебя есть:
1. Исходный вопрос пользователя
2. SQL-запрос (что было выполнено)
3. Результат запроса (данные из базы)

Твоя задача — дать ЕСТЕСТВЕННЫЙ, ПОЛНЫЙ и ЧЕЛОВЕЧЕСКИЙ ответ на русском языке,
используя информацию из вопроса и данных. НЕ просто "средняя_цена: X", а полноценное
предложение, которое повторяет контекст вопроса и объясняет результат.

Требования:
- Повтори контекст из вопроса (что за лом, какой период, какой поставщик/источник).
- Чётко назови искомую метрику (средняя/минимальная/максимальная цена, сумма и т.д.).
- Приведи число с форматированием (разделители тысяч), укажи валюту/единицы (руб/тн), если уместно.
- Если данных нет — объясни, что по данному запросу цен в источнике не нашлось.
- Ответ — 1-3 предложения, без markdown, без перечисления полей JSON.

Пример:
Вопрос: "Средняя цена всех видов медного лома по Сплав-21 в декабре 2025?"
Результат: [{"средняя_цена": 759991.4}]
Ответ: "Средняя цена всех видов медного лома по данным компании Сплав-21 в декабре 2025 года составила 759 991.4 руб./тн."
"""

CHART_SYSTEM_PROMPT = """Ты — ассистент, который только что построил график по данным о ценах на цветной лом.

У тебя есть:
1. Исходный запрос пользователя (просьба построить график)
2. SQL-запрос (что было выполнено)
3. Данные — точки построенного графика

Твоя задача — КРАТКО и ПО ДЕЛУ объяснить построенный график на русском языке:
- Что изображено: какой показатель (цена/средняя цена и т.п.), какой товар, какая
  группировка (по месяцам — динамика, по поставщикам — сравнение).
- Главный вывод: динамика (цена растёт/падает/стабильна) или лидер/аутсайдер
  среди поставщиков.
- Минимум и максимум с числами и единицами (руб/тн), если они есть в данных.

Требования:
- 1-3 предложения, без markdown и без перечисления полей JSON.
- Используй ТОЛЬКО данные из точек графика, ничего не выдумывай.
- Не пиши «на графике видно то-то» про то, чего нет в данных.
- НЕ отвечай «только число» — пользователь просил график, объясни его словами.

Пример:
Данные: [{"месяц": "2025-01", "средняя_цена": 100000}, {"месяц": "2025-02", "средняя_цена": 105000}]
Ответ: "Линейный график динамики средней цены на медь по месяцам: за январь–февраль 2025 цена выросла со 100 000 до 105 000 руб/тн."
"""

CONCISE_SYSTEM_PROMPT = """Ты — краткий ассистент по данным о ценах на цветной лом.

У тебя есть:
1. Исходный вопрос пользователя
2. SQL-запрос (что было выполнено)
3. Результат запроса (данные из базы)

Твоя задача — ответить МАКСИМАЛЬНО КРАТКО: ТОЛЬКО число (с указанием валюты/единиц измерения, если уместно) ИЛИ одно короткое слово.

Правила:
- Никаких предложений, пояснений, вводных фраз, markdown и лишней пунктуации.
- Если в данных есть конкретное числовое значение — верни только его, например: "759 991.4 руб./тн" или "12 500".
- Если данных нет — верни одно слово: "нет" или "не найдено".
- Не добавляй ничего сверх самого ответа.

Пример:
Вопрос: "Средняя цена всех видов медного лома по Сплав-21 в декабре 2025?"
Результат: [{"средняя_цена": 759991.4}]
Ответ: 759 991.4 руб./тн
"""


def _deterministic_answer(sql_result: list, is_concise: bool) -> str:
    if is_concise:
        return "не найдено"
    if sql_result:
        return (
            "Получены данные, но не удалось сформировать ответ. "
            "Пожалуйста, уточните вопрос."
        )
    return (
        "Не удалось найти ответ на ваш вопрос. "
        "Попробуйте переформулировать запрос."
    )


def _result_has_numbers(sql_result: list) -> bool:
    """True, если в результате запроса есть хотя бы одно числовое значение.

    Число в ответе критично для вопросов «какая цена/сумма/дельта» — если LLM
    сгенерировал усечённый ответ без числа, его нельзя отдавать пользователю.
    """
    for row in sql_result or []:
        if not isinstance(row, dict):
            continue
        for v in row.values():
            if isinstance(v, bool):
                continue
            if isinstance(v, (int, float)):
                return True
    return False


def _has_digit(text: str) -> bool:
    """True, если в тексте есть хотя бы одна цифра."""
    return any(ch.isdigit() for ch in (text or ""))


def _chart_fallback_answer(sql_result: list, chart_request: Optional[Dict[str, str]]) -> str:
    """Детерминированное описание графика, если LLM не смог сформулировать.

    Используется при графическом запросе вместо общего fallback-ответа,
    чтобы пользователь получил внятное пояснение к построенному графику.
    """
    chart_request = chart_request or {}
    group_by = chart_request.get("group_by", "period")
    kind = (
        "Линейный график"
        if chart_request.get("chart_type") == "line"
        else "Столбчатая диаграмма"
    )
    grouping = "по месяцам" if group_by == "period" else "по поставщикам"
    nums = [
        v
        for row in sql_result or []
        if isinstance(row, dict)
        for v in row.values()
        if isinstance(v, (int, float)) and not isinstance(v, bool)
    ]
    if nums:
        return (
            f"{kind} {grouping}: точек — {len(nums)}, "
            f"минимум — {min(nums):,.2f}, максимум — {max(nums):,.2f} (руб/тн)."
        ).replace(",", " ")
    return f"Построен {kind.lower()} {grouping}."


async def answer_node(
    state: GraphState,
    llm: Optional[LLMClient] = None,
    **kwargs: Any,
) -> GraphState:
    llm = llm or LLMClient()
    request_id = state.get("request_id", "?")[:8]
    question = state.get("question", "")
    answer = state.get("answer", "")
    sql_result = state.get("sql_result", [])
    sql_query = state.get("sql_query", "")
    response_mode = state.get("response_mode", "detailed")
    is_concise = response_mode == "concise"
    chart_request = state.get("chart_request")
    is_chart_request = bool(chart_request)

    logger.info(
        "Answer Node [{}]: finalizing answer ({} chars, mode={})",
        request_id,
        len(answer),
        response_mode,
    )

    # Детерминированный ответ — fallback на случай ошибки LLM.
    if not answer:
        deterministic = _deterministic_answer(sql_result, is_concise)
    else:
        deterministic = answer

    if is_chart_request and sql_result and question:
        # Графический запрос: объясняем построенный график, а не отвечаем числом
        # (игнорируем concise-режим — «только число» к графику не имеет смысла).
        try:
            user_message = f"""Запрос пользователя: {question}

SQL-запрос:
{sql_query}

Данные графика ({len(sql_result)} точек):
{json.dumps(sql_result[:15], ensure_ascii=False, indent=2, default=str)}

Кратко объясни построенный график."""
            messages = [
                {"role": "system", "content": CHART_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ]
            generated = (await llm.chat(
                messages=messages,
                model=None,
                temperature=0.2,
                max_tokens=256,
            )).strip()

            if generated and len(generated) > 10:
                answer = generated
                logger.info(
                    "Answer Node [{}]: chart explanation generated ({} chars)",
                    request_id,
                    len(answer),
                )
            else:
                answer = _chart_fallback_answer(sql_result, chart_request)
        except Exception as exc:
            logger.warning(
                "Answer Node [{}]: chart explanation failed ({}), using fallback",
                request_id,
                exc,
            )
            answer = _chart_fallback_answer(sql_result, chart_request)
    elif sql_result and question:
        # Пытаемся сгенерировать ответ по вопросу + данным в выбранном режиме.
        try:
            system_prompt = (
                CONCISE_SYSTEM_PROMPT if is_concise else ANSWER_SYSTEM_PROMPT
            )
            if is_concise:
                instruction = (
                    "Дай ответ в формате «только число или слово» на основе этих данных."
                )
                temperature = 0.0
                max_tokens = 40
            else:
                instruction = (
                    "Сформулируй естественный, полный ответ на вопрос пользователя "
                    "на основе этих данных."
                )
                temperature = 0.2
                max_tokens = 512

            memory_ctx = build_memory_context(state.get("conversation_history", []))
            memory_section = (
                f"\n\nИстория диалога (контекст предыдущих вопросов):\n{memory_ctx}"
                if memory_ctx
                else ""
            )
            user_message = f"""Вопрос пользователя: {question}{memory_section}

SQL-запрос:
{sql_query}

Результат ({len(sql_result)} строк):
{json.dumps(sql_result[:5], ensure_ascii=False, indent=2, default=str)}

{instruction}"""
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]
            generated = (await llm.chat(
                messages=messages,
                model=None,
                temperature=temperature,
                max_tokens=max_tokens,
            )).strip()

            min_len = 1 if is_concise else 10
            if generated and len(generated) > min_len:
                # Страховка от усечённых ответов LLM: если в данных есть числовое
                # значение (цена/сумма/дельта), а сгенерированный ответ потерял
                # все цифры ("Минимальная среднерыночная цена на цинковый...") —
                # отдаём детерминированный ответ, где число гарантированно есть.
                if not is_concise and _result_has_numbers(sql_result) and not _has_digit(generated):
                    logger.warning(
                        "Answer Node [{}]: generated answer lost the numeric value, "
                        "using deterministic fallback",
                        request_id,
                    )
                    answer = deterministic
                else:
                    answer = generated
                logger.info(
                    "Answer Node [{}]: natural answer generated ({} chars, mode={})",
                    request_id,
                    len(answer),
                    response_mode,
                )
            else:
                answer = deterministic
        except Exception as exc:
            logger.warning(
                "Answer Node [{}]: natural answer failed ({}), using deterministic",
                request_id,
                exc,
            )
            answer = deterministic
    else:
        answer = deterministic

    state["answer"] = answer
    state["confidence"] = state.get("confidence", 0.0)

    state["trace"] = state.get("trace", {})
    state["trace"][NODE_ANSWER] = {
        "answer_length": len(answer),
        "confidence": state.get("confidence", 0.0),
        "response_mode": response_mode,
        "chart_request": chart_request,
    }

    logger.info(
        "Answer Node [{}]: done, confidence={:.2f}, mode={}",
        request_id,
        state.get("confidence", 0.0),
        response_mode,
    )

    return state