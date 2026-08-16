from __future__ import annotations
import json
from typing import Any, Optional
from src.core.logging_settings import logger
from src.services.agent.graph_state import GraphState, NODE_ANSWER
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

    if sql_result and question:
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
                max_tokens = 256

            user_message = f"""Вопрос пользователя: {question}

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
    }

    logger.info(
        "Answer Node [{}]: done, confidence={:.2f}, mode={}",
        request_id,
        state.get("confidence", 0.0),
        response_mode,
    )

    return state