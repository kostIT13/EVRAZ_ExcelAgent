"""Conditional edges (маршрутизация) для графа LangGraph.

Определяет, в какой узел переходить после каждого шага,
в зависимости от текущего состояния.
"""

from __future__ import annotations

from typing import Literal

from src.core.logging_settings import logger
from src.services.agent.graph_state import (
    GraphState,
    NODE_RAG,
    NODE_CLASSIFIER,
    NODE_PLANNER,
    NODE_CODEGEN,
    NODE_EXECUTOR,
    NODE_VERIFIER,
    NODE_ANSWER,
    NODE_FAILED,
)

# Максимальное количество retry
MAX_RETRY_COUNT = 3


def route_after_rag(state: GraphState) -> Literal["classifier", "failed"]:
    """После RAG всегда идём в Classifier.
    Если RAG упал с ошибкой — всё равно продолжаем (Classifier может работать без контекста).
    """
    rag_error = state.get("rag_error")
    if rag_error:
        logger.warning(
            "Routing: RAG had error ({}), continuing to classifier anyway",
            rag_error,
        )
    return NODE_CLASSIFIER


def route_after_classifier(state: GraphState) -> Literal["planner", "failed"]:
    """После Classifier всегда идём в Planner."""
    return NODE_PLANNER


def route_after_planner(state: GraphState) -> Literal["codegen", "failed"]:
    """После Planner всегда идём в CodeGen."""
    return NODE_CODEGEN


def route_after_codegen(state: GraphState) -> Literal["executor", "codegen", "failed"]:
    """После CodeGen:
    - Если валидация пройдена → Executor
    - Если ошибки валидации и retry < лимита → CodeGen (retry)
    - Если превышен лимит retry → Executor (пробуем выполнить, даже с ошибками)
    """
    validation_errors = state.get("validation_errors", [])
    sql_query = state.get("sql_query", "")
    retry_count = state.get("retry_count", 0)

    if not sql_query:
        if retry_count < MAX_RETRY_COUNT:
            logger.warning(
                "Routing: empty SQL, retry #{}/{} → codegen",
                retry_count + 1,
                MAX_RETRY_COUNT,
            )
            return NODE_CODEGEN
        else:
            logger.warning(
                "Routing: empty SQL, max retries ({}) reached → failed",
                MAX_RETRY_COUNT,
            )
            return NODE_FAILED

    if validation_errors:
        if retry_count < MAX_RETRY_COUNT:
            logger.warning(
                "Routing: validation errors ({}): {}, retry #{}/{} → codegen",
                len(validation_errors),
                validation_errors[0][:80],
                retry_count + 1,
                MAX_RETRY_COUNT,
            )
            return NODE_CODEGEN
        else:
            logger.warning(
                "Routing: validation errors ({}), max retries ({}) reached → executor anyway",
                len(validation_errors),
                MAX_RETRY_COUNT,
            )
            return NODE_EXECUTOR

    return NODE_EXECUTOR


def route_after_executor(state: GraphState) -> Literal["verifier", "codegen", "failed"]:
    """После Executor:
    - Если SQL успешен → Verifier
    - Если SQL ошибка → CodeGen (retry)
    - Если превышен лимит retry → Failed
    """
    sql_error = state.get("sql_error")
    retry_count = state.get("retry_count", 0)

    if sql_error:
        if retry_count < MAX_RETRY_COUNT:
            logger.warning(
                "Routing: SQL error ({}), retry #{}/{} → codegen",
                sql_error[:50],
                retry_count + 1,
                MAX_RETRY_COUNT,
            )
            return NODE_CODEGEN
        else:
            logger.warning(
                "Routing: max retries ({}) reached for SQL errors → failed",
                MAX_RETRY_COUNT,
            )
            return NODE_FAILED

    return NODE_VERIFIER


def route_after_verifier(state: GraphState) -> Literal["answer", "codegen", "failed"]:
    """После Verifier:
    - Если ответ корректен → Answer
    - Если нужен retry и лимит не превышен → CodeGen
    - Если превышен лимит retry → Answer (отдаём что есть)
    """
    needs_retry = state.get("needs_retry", False)
    retry_count = state.get("retry_count", 0)

    if needs_retry and retry_count < MAX_RETRY_COUNT:
        logger.warning(
            "Routing: needs_retry ({}), retry #{}/{} → codegen",
            state.get("retry_reason", "?"),
            retry_count + 1,
            MAX_RETRY_COUNT,
        )
        return NODE_CODEGEN

    if needs_retry and retry_count >= MAX_RETRY_COUNT:
        logger.warning(
            "Routing: max retries ({}) reached, sending to answer anyway",
            MAX_RETRY_COUNT,
        )

    return NODE_ANSWER