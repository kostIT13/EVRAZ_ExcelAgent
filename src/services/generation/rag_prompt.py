from __future__ import annotations
from typing import List, Optional, Dict, Any
from src.services.rag.hybrid import HybridSearchResult


SYSTEM_PROMPT = """Ты — ассистент по анализу Excel-данных ЕВРАЗ. Твоя задача — отвечать на вопросы пользователя, используя ТОЛЬКО предоставленный контекст из базы данных Excel-файлов.

Правила:
1. Отвечай на русском языке, чётко и по делу.
2. Если контекста недостаточно для ответа — скажи об этом, не выдумывай.
3. Если вопрос требует расчёта (сумма, среднее, количество) — сделай расчёт на основе данных из контекста.
4. Ссылайся на конкретные листы, колонки и значения из контекста.
5. Не используй внешние знания — только то, что в контексте.
6. Если в контексте есть табличные данные — представь ответ в структурированном виде.
"""

SELF_CORRECT_INSTRUCTION = """
Дополнительная информация: это повторная попытка ответить на вопрос.
Предыдущая попытка не дала удовлетворительного результата.
Вот история предыдущих попыток:

{history}

Пожалуйста, проанализируй, почему предыдущий ответ мог быть неудовлетворительным,
и попробуй другой подход к ответу. Обрати внимание на детали, которые могли быть упущены.
"""


def format_context(results: List[HybridSearchResult], max_chars: int = 48000) -> str:
    parts: List[str] = []
    total = 0

    for i, r in enumerate(results, start=1):
        header = f"[Источник {i}] (релевантность: {r.score:.3f})"
        if r.source_type != "unknown":
            header += f" | тип: {r.source_type}, id: {r.source_id}"

        entry = f"{header}\n{r.chunk}\n"
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
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ]

    # Если есть история self-correction — добавляем её как контекст
    if conversation_history:
        history_text = "\n".join(
            f"{'Пользователь' if turn.get('role') == 'user' else 'Ассистент'}: {turn.get('content', '')}"
            for turn in conversation_history
        )
        correction_msg = SELF_CORRECT_INSTRUCTION.format(history=history_text)
        messages.append({"role": "system", "content": correction_msg})

    user_content = f"""Вопрос пользователя:
{question}

Контекст из базы данных Excel:
{context}

Дай ответ на основе контекста."""

    messages.append({"role": "user", "content": user_content})
    return messages


SQL_GENERATION_PROMPT = """Ты — генератор SQL-запросов для Excel-данных. На основе вопроса пользователя и схемы таблиц напиши SQL-запрос.

Схема таблиц:
{schemas}

Вопрос: {question}

Напиши только SQL-запрос без пояснений."""