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

    logger.info(
        "Answer Node [{}]: finalizing answer ({} chars)",
        request_id,
        len(answer),
    )

    # Детерминированный ответ — fallback на случай ошибки LLM.
    if not answer:
        if sql_result:
            deterministic = (
                "Получены данные, но не удалось сформировать ответ. "
                "Пожалуйста, уточните вопрос."
            )
        else:
            deterministic = (
                "Не удалось найти ответ на ваш вопрос. "
                "Попробуйте переформулировать запрос."
            )
    else:
        deterministic = answer

    if sql_result and question:
        # Пытаемся сгенерировать естественный ответ по вопросу + данным.
        try:
            user_message = f"""Вопрос пользователя: {question}

SQL-запрос:
{sql_query}

Результат ({len(sql_result)} строк):
{json.dumps(sql_result[:5], ensure_ascii=False, indent=2, default=str)}

Сформулируй естественный, полный ответ на вопрос пользователя на основе этих данных."""
            messages = [
                {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
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
                    "Answer Node [{}]: natural answer generated ({} chars)",
                    request_id,
                    len(answer),
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
    }

    logger.info(
        "Answer Node [{}]: done, confidence={:.2f}",
        request_id,
        state.get("confidence", 0.0),
    )

    return state