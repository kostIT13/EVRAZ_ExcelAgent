"""Структурированный вывод через langchain ``with_structured_output``.

Обёртка над ``ChatOpenAI`` (langchain-openai), использующая те же настройки
приложения, что и ``LLMClient`` (base_url, api_key, модель, timeout, retries).

Фабрика возвращает ``Runnable`` с ``with_structured_output(PydanticSchema)``,
который автоматически парсит ответ модели в валидированный Pydantic-объект —
без ручного ``json.loads`` + try/except.

Дополнительно предоставляет ``ainvoke_structured`` — надёжную обёртку вызова
с ретраями: flash-модели/прокси иногда возвращают пустой контент или невалидный
JSON, из-за чего ``with_structured_output`` бросает исключение. Вместо падения
всего узла делаем повторный вызов с корректирующим сообщением.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Type, TypeVar

from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from src.core.config import settings
from src.core.logging_settings import logger

T = TypeVar("T", bound=BaseModel)

# Кэш построенных Runnable по схеме, чтобы не пересоздавать на каждый вызов.
_STRUCTURED_CACHE: Dict[Type[BaseModel], Runnable] = {}


def _build_chat(model: str, temperature: float) -> ChatOpenAI:
    return ChatOpenAI(
        base_url=settings.LLM_BASE_URL,
        api_key=settings.LLM_API_KEY,
        model=model,
        temperature=temperature,
        timeout=settings.REQUEST_TIMEOUT_S,
        max_retries=settings.MAX_RETRIES,
    )


def get_structured_llm(
    schema: Type[T],
    temperature: float = 0.0,
    method: str = "json_mode",
) -> Runnable:
    """Возвращает Runnable, который возвращает валидированный ``schema``.

    ``method="json_mode"`` максимально совместим с OpenAI-совместимыми прокси
    (vLLM и т.п.) и гарантирует парсинг в Pydantic без ручной обработки JSON.
    """
    if schema in _STRUCTURED_CACHE:
        return _STRUCTURED_CACHE[schema]

    runnable = _build_chat(settings.LLM_MODEL_PRIMARY, temperature).with_structured_output(
        schema, method=method
    )

    _STRUCTURED_CACHE[schema] = runnable
    logger.info(
        "Structured LLM built for {} (method={})",
        schema.__name__,
        method,
    )
    return runnable


async def ainvoke_structured(
    runnable: Runnable,
    messages: List[Dict[str, str]],
    schema: Type[T],
    max_retries: int = 2,
) -> T:
    """Вызывает ``runnable.ainvoke(messages)`` с ретраями при сбое парсинга.

    При ошибке (пустой контент, невалидный JSON, несоответствие схеме)
    повторяем запрос с корректирующим сообщением вместо того, чтобы ронять
    весь узел графа. Возвращает валидированный объект ``schema``.
    """
    last_exc: Exception | None = None
    current_messages = list(messages)

    for attempt in range(max_retries + 1):
        try:
            return await runnable.ainvoke(current_messages)
        except Exception as exc:  # OutputParserException, ValidationError и т.п.
            last_exc = exc
            logger.warning(
                "Structured ainvoke attempt {}/{} for {} failed: {}",
                attempt + 1,
                max_retries + 1,
                getattr(schema, "__name__", "?"),
                exc,
            )
            if attempt >= max_retries:
                break
            await asyncio.sleep(0.5)
            schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
            current_messages = current_messages + [
                {
                    "role": "user",
                    "content": (
                        "Твой предыдущий ответ не прошёл проверку JSON-схемы "
                        f"({exc}). Верни строго один JSON-объект, соответствующий схеме:\n"
                        f"{schema_json}"
                    ),
                }
            ]

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Structured output failed without an exception")