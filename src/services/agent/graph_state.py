"""LangGraph State — типизированное состояние графа агента.

Использует TypedDict для совместимости с LangGraph.
Все узлы графа читают и пишут в это состояние.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, TypedDict


class QueryType(str, Enum):
    """Тип запроса, определяемый Classifier."""
    LOOKUP = "lookup"
    """Простой поиск значения ('какая цена на медь в январе')"""
    AGGREGATE = "aggregate"
    """Агрегатный запрос (сумма, среднее, минимум)"""
    CROSS_SHEET = "cross_sheet"
    """Сравнение между разными листами/месяцами"""
    DELTA = "delta"
    """Разница между значениями во времени"""
    UNKNOWN = "unknown"
    """Classifier не смог определить тип"""


class GraphState(TypedDict, total=False):
    """Состояние графа LangGraph.
    
    Все поля опциональны (total=False), чтобы можно было создавать
    состояние с минимальным набором полей.
    """
    # === Вход ===
    question: str
    """Исходный вопрос пользователя."""
    request_id: str
    """UUID запроса."""
    top_k: int
    """Количество чанков для RAG-поиска."""

    # === RAG Node ===
    rag_context: str
    """Контекст из RAG (отформатированные чанки)."""
    rag_chunks: List[Dict[str, Any]]
    """Сырые результаты гибридного поиска."""
    rag_error: Optional[str]
    """Ошибка RAG, если есть."""

    # === Classifier Node ===
    query_type: QueryType
    """Тип запроса."""
    entities: List[str]
    """Сущности из вопроса (например, ['медь', 'январь 2025'])."""
    relevant_sheets: List[Dict[str, Any]]
    """Список релевантных листов."""

    # === Disambiguation Node ===
    disambiguation_needed: bool
    """Флаг: нуждается ли вопрос в уточнении."""
    disambiguation_info: Dict[str, Any]
    """Информация о неоднозначности (тип, уточняющий вопрос, опции)."""

    # === Planner Node ===
    plan: str
    """Текстовый план действий для CodeGen."""
    schema: List[Dict[str, Any]]
    """Схема релевантных листов (передаётся напрямую, не через trace)."""

    # === CodeGen Node ===
    sql_query: str
    """Сгенерированный SQL-запрос."""
    validation_errors: List[str]
    """Ошибки валидации SQL (пусто = ОК)."""

    # === Executor Node ===
    sql_result: List[Dict[str, Any]]
    """Результат выполнения SQL."""
    sql_error: Optional[str]
    """Ошибка выполнения SQL."""

    # === Verifier Node ===
    answer: str
    """Финальный ответ пользователю."""
    confidence: float
    """Уверенность в ответе (0..1)."""
    retry_count: int
    """Счётчик retry (Verifier → CodeGen)."""
    needs_retry: bool
    """Флаг: нужен ли retry."""
    retry_reason: str
    """Причина retry."""

    # === Служебные ===
    trace: Dict[str, Any]
    """Полный trace каждого шага для /trace/{request_id}."""
    error: Optional[str]
    """Фатальная ошибка, если есть."""


# Константы: имена узлов графа
NODE_RAG = "rag"
NODE_CLASSIFIER = "classifier"
NODE_DISAMBIGUATION = "disambiguation"
NODE_PLANNER = "planner"
NODE_CODEGEN = "codegen"
NODE_EXECUTOR = "executor"
NODE_VERIFIER = "verifier"
NODE_ANSWER = "answer"
NODE_FAILED = "failed"
