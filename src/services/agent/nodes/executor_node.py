from __future__ import annotations
from typing import Any, Dict, List, Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.db.database import async_session_maker
from src.core.logging_settings import logger
from src.services.agent.graph_state import GraphState, NODE_EXECUTOR

MAX_RESULT_ROWS = 100

QUERY_TIMEOUT_SECONDS = 30


async def executor_node(
    state: GraphState,
    session: Optional[AsyncSession] = None,
    **kwargs: Any,
) -> GraphState:
    request_id = state.get("request_id", "?")[:8]
    sql_query = state.get("sql_query", "")
    validation_errors = state.get("validation_errors", [])

    logger.info(
        "Executor Node [{}]: executing SQL ({} chars)",
        request_id,
        len(sql_query),
    )

    if not sql_query:
        state["sql_error"] = "Нет SQL-запроса для выполнения"
        state["sql_result"] = []
        state["trace"] = state.get("trace", {})
        state["trace"][NODE_EXECUTOR] = {"error": state["sql_error"]}
        return state

    if validation_errors:
        state["sql_error"] = (
            f"SQL не прошёл валидацию: {'; '.join(validation_errors)}"
        )
        state["sql_result"] = []
        state["trace"] = state.get("trace", {})
        state["trace"][NODE_EXECUTOR] = {"error": state["sql_error"]}
        return state

    try:
        async with (session or async_session_maker()) as s:
            async with s.begin():
                await s.execute(
                    text(f"SET LOCAL statement_timeout = '{QUERY_TIMEOUT_SECONDS}s'")
                )
                result = await s.execute(text(sql_query))

            if result.returns_rows:
                columns = result.keys()
                rows = result.fetchmany(MAX_RESULT_ROWS)
                state["sql_result"] = [
                    dict(zip(columns, row)) for row in rows
                ]
                logger.info(
                    "Executor Node [{}]: query returned {} rows",
                    request_id,
                    len(state["sql_result"]),
                )
            else:
                state["sql_result"] = []
                logger.info(
                    "Executor Node [{}]: query did not return rows",
                    request_id,
                )

        state["sql_error"] = None

    except Exception as exc:
        error_msg = str(exc)
        logger.error(
            "Executor Node [{}]: SQL execution failed: {}",
            request_id,
            error_msg,
        )
        state["sql_error"] = error_msg
        state["sql_result"] = []

    state["trace"] = state.get("trace", {})
    state["trace"][NODE_EXECUTOR] = {
        "sql_query": sql_query,
        "row_count": len(state.get("sql_result", [])),
        "error": state.get("sql_error"),
        "result_preview": state.get("sql_result", [])[:5],
    }

    return state