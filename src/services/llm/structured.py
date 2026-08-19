"""Структурированный вывод через langchain ``with_structured_output``.

Обёртка над ``ChatOpenAI`` (langchain-openai), использующая те же настройки
приложения, что и ``LLMClient`` (base_url, api_key, модель, timeout, retries).

Фабрика возвращает ``Runnable`` с ``with_structured_output(PydanticSchema)``,
который автоматически парсит ответ модели в валидированный Pydantic-объект —
без ручного ``json.loads`` + try/except. Добавлен fallback primary → cheap.
"""

from __future__ import annotations

from typing import Dict, Type, TypeVar

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

    primary = _build_chat(settings.LLM_MODEL_PRIMARY, temperature).with_structured_output(
        schema, method=method
    )
    cheap = _build_chat(settings.LLM_MODEL_CHEAP, temperature).with_structured_output(
        schema, method=method
    )
    runnable = primary.with_fallbacks([cheap])

    _STRUCTURED_CACHE[schema] = runnable
    logger.info(
        "Structured LLM built for {} (method={}, fallback primary->cheap)",
        schema.__name__,
        method,
    )
    return runnable