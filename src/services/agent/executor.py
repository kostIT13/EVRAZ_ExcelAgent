# """Что делает Executor:

# Берёт SQL-запрос из AgentState (после валидации)
# Выполняет его через асинхронную сессию SQLAlchemy (read-only транзакция)
# Возвращает результат в виде списка dict'ов
# Если ошибка — сохраняет в state.sql_error
# """

# """Executor — безопасное выполнение SQL-запросов.

# Выполняет SQL через асинхронную сессию SQLAlchemy в read-only режиме.
# """

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db.database import async_session_maker
from src.core.logging_settings import logger
from src.services.agent.state import AgentState, AgentStep

# Максимальное количество строк в результате
MAX_RESULT_ROWS = 100

# Максимальное время выполнения запроса (сек)
QUERY_TIMEOUT_SECONDS = 30

async def executor_step(
    state: AgentState,
    session: Optional[AsyncSession] = None
) -> AgentState:
    """Шаг Executor: выполняет SQL-запрос и возвращает результат.

    Args:
        state: Текущее состояние агента (должен быть заполнен codegen'ом).
        session: Опциональная асинхронная сессия (для тестов).

    Returns:
        AgentState с заполненными sql_result или sql_error.
    """
    logger.info(
        "Executor [{}]: executing SQL ({} chars)",
        state.request_id[:8],
        len(state.sql_query),
    )

    # 1. Проверяем, есть ли что выполнить
    if not state.sql_query:
        state.sql_error = "Нет SQL-запроса для выполнения"
        state.trace["executor"] = {"error": state.sql_error}
        state.current_step = "executor"
        return state
    
    if state.validation_errors:
        state.sql_error = f"SQL не прошёл валидацию: {'; '.join(state.validation_errors)}"
        state.trace["executor"] = {"error": state.sql_error}
        state.current_step = "executor"
        return state
    
    # 2. Выполняем пользовательский запрос
    try:
        async with session or async_session_maker() as s:
            # Устанавливаем таймаут для транзакции
            await s.execute(
                text(f"SET LOCAL statement_timeout = '{QUERY_TIMEOUT_SECONDS}s'")
            )

            # Выполняем запрос
            result = await s.execute(text(state.sql_query))

            # Получаем имена колонок
            if result.returns_rows:
                columns = result.keys()
                rows = result.fetchmany(MAX_RESULT_ROWS)

                # Преобразуем в список dict'ов
                state.sql_result = [
                    dict(zip(columns, row)) for row in rows
                ]

                logger.info(
                    "Executor [{}]: query returned {} rows",
                    state.request_id[:8],
                    len(state.sql_result),
                )
            else:
                state.sql_result = []
                logger.info(
                    "Executor [{}]: query did not return rows",
                    state.request_id[:8],
                )

        state.sql_error = None

    except Exception as exc:
        error_msg = str(exc)
        logger.error(
            "Executor [{}]: SQL execution failed: {}",
            state.request_id[:8],
            error_msg,
        )
        state.sql_error = error_msg
        state.sql_result = []
        
        
    # 3. Сохраняем trace
    state.trace["executor"] = {
        "sql_query": state.sql_query,
        "row_count": len(state.sql_result),
        "error": state.sql_error,
        "result_preview": state.sql_result[:5],  # только первые 5 строк
    }

    # 4. Определяем следующий шаг
    if state.sql_error:
        state.current_step = AgentStep.EXECUTOR  # ошибка — остаёмся
    else:
        state.current_step = AgentStep.VERIFIER  # успех — идём к верификатору

    return state