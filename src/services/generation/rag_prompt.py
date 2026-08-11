"""Prompt templates для генерации ответов (устаревший RAG-модуль).

RAG-over-cells и векторные эмбеддинги удалены из архитектуры. Агент работает по
нормализованной факт-таблице mart.price_facts и не использует chunk-context.
Данный модуль сохранён только для обратной совместимости импортов и содержит
простые текстовые промпты без ссылок на vector-retrieval.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


SYSTEM_PROMPT = """Ты — ассистент по анализу Excel-данных ЕВРАЗ. Твоя задача — отвечать на вопросы пользователя, используя данные из нормализованной факт-таблицы цен.

Правила:
1. Отвечай на русском языке, чётко и по делу.
2. Если данных недостаточно для ответа — скажи об этом, не выдумывай.
3. Если вопрос требует расчёта (сумма, среднее, количество) — сделай расчёт на основе данных.
4. Не используй внешние знания — только данные из базы.
"""

SELF_CORRECT_INSTRUCTION = """
Дополнительная информация: это повторная попытка ответить на вопрос.
Предыдущая попытка не дала удовлетворительного результата.
Вот история предыдущих попыток:

{history}

Пожалуйста, проанализируй, почему предыдущий ответ мог быть неудовлетворительным,
и попробуй другой подход к ответу.
"""


def format_context(results, max_chars: int = 64000) -> str:
    """Форматирует сущности/кандидатов в текст для контекста (RAG-режим удалён).

    Принимает любые итерируемые объекты с атрибутами score/chunk для совместимости,
    но фактически больше не используется графом.
    """
    parts: List[str] = []
    total = 0

    for i, r in enumerate(results, start=1):
        chunk = getattr(r, "chunk", str(r))
        score = getattr(r, "score", 0.0)
        entry = f"[Источник {i}] (релевантность: {score:.3f})\n{chunk}\n"
        if total + len(entry) > max_chars:
            break
        parts.append(entry)
        total += len(entry)

    return "\n".join(parts)


def build_rag_prompt(
    question: str,
    context: str,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> list[dict]:
    """Строит список сообщений для LLM (обратная совместимость)."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ]

    if conversation_history:
        history_text = "\n".join(
            f"{'Пользователь' if turn.get('role') == 'user' else 'Ассистент'}: {turn.get('content', '')}"
            for turn in conversation_history
        )
        messages.append({
            "role": "system",
            "content": SELF_CORRECT_INSTRUCTION.format(history=history_text),
        })

    messages.append({
        "role": "user",
        "content": f"Вопрос: {question}\n\nКонтекст:\n{context}",
    })

    return messages