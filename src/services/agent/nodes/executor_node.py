from __future__ import annotations
import re
from typing import Any, Dict, List, Optional, Set
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.db.database import async_session_maker
from src.core.logging_settings import logger
from src.services.agent.graph_state import GraphState, NODE_EXECUTOR

MAX_RESULT_ROWS = 100

QUERY_TIMEOUT_SECONDS = 30


def _extract_iliase_from_sql(sql: str) -> List[str]:
    """Извлекает все ILIKE-паттерны из SQL-запроса.
    
    Возвращает список строк, которые ищутся через ILIKE.
    Например: '%медь%' → 'медь', '%лом алюминия%' → 'лом алюминия'
    """
    patterns = re.findall(r"ILIKE\s+'%([^']+)%'", sql, re.IGNORECASE)
    return [p.strip() for p in patterns]


def _extract_periods_from_sql(sql: str) -> List[str]:
    """Извлекает все условия по period из SQL-запроса."""
    periods = re.findall(r"period\s*=\s*'([^']+)'", sql, re.IGNORECASE)
    periods += re.findall(r"period\s+IN\s*\(([^)]+)\)", sql, re.IGNORECASE)
    # Разбираем IN-список
    expanded = []
    for p in periods:
        if "," in p:
            expanded.extend([x.strip().strip("'") for x in p.split(",")])
        else:
            expanded.append(p.strip().strip("'"))
    return expanded


def _extract_price_source_from_sql(sql: str) -> Optional[str]:
    """Извлекает условие по price_source из SQL."""
    # ILIKE по price_source
    match = re.search(r"price_source\s+ILIKE\s+'%([^']+)%'", sql, re.IGNORECASE)
    if match:
        return match.group(1)
    # Точное равенство
    match = re.search(r"price_source\s*=\s*'([^']+)'", sql, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def _collect_samples_from_schema(schema: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Собирает все fact_prices_samples из схемы в единый список.

    Колонка item_name берётся из mart.price_facts (нормализованная long-таблица).
    """
    all_samples: List[Dict[str, Any]] = []
    seen_items: Set[str] = set()
    for sheet in schema:
        samples = sheet.get("fact_prices_samples", [])
        for s in samples:
            item = s.get("item_name") or s.get("item_name_normalized", "")
            if item and item not in seen_items:
                seen_items.add(item)
                all_samples.append(s)
    return all_samples


def _build_samples_fallback_sql(
    original_sql: str,
    samples: List[Dict[str, Any]],
) -> Optional[str]:
    """Строит fallback SQL, заменяя ILIKE-маски на реальные item_name из samples.

    Работает по март-таблице mart.price_facts: заменяет ILIKE-маски по item_name
    на точные значения через IN (если LLM выдумал маску, а в БД реальное название).
    """
    sql_lower = original_sql.lower().strip()
    if "price_facts" not in sql_lower:
        return None
    if not samples:
        return None

    # Извлекаем ILIKE-паттерны из оригинального SQL
    ilike_patterns = _extract_iliase_from_sql(original_sql)
    if not ilike_patterns:
        return None

    # Для каждого паттерна ищем подходящие реальные названия
    matched_items: Set[str] = set()
    for pattern in ilike_patterns:
        pattern_lower = pattern.lower()
        for s in samples:
            item = s.get("item_name_normalized", "")
            if item and pattern_lower in item.lower():
                matched_items.add(item)

    if not matched_items:
        return None

    # Строим новый SQL, заменяя ILIKE на IN
    # Находим первое ILIKE-условие и заменяем его на IN
    items_list = sorted(matched_items)
    items_formatted = ", ".join(f"'{item}'" for item in items_list)
    
    # Заменяем все ILIKE по item_name (колонка mart.price_facts) на IN.
    new_sql = re.sub(
        r"AND\s+fp\.item_name\s+ILIKE\s+'[^']+'\s*",
        f"AND fp.item_name IN ({items_formatted})",
        original_sql,
        flags=re.IGNORECASE,
    )
    new_sql = re.sub(
        r"WHERE\s+fp\.item_name\s+ILIKE\s+'[^']+'\s*",
        f"WHERE fp.item_name IN ({items_formatted})",
        new_sql,
        flags=re.IGNORECASE,
    )
    # Вариант без префикса fp.
    new_sql = re.sub(
        r"AND\s+item_name\s+ILIKE\s+'[^']+'\s*",
        f"AND item_name IN ({items_formatted})",
        new_sql,
        flags=re.IGNORECASE,
    )
    new_sql = re.sub(
        r"WHERE\s+item_name\s+ILIKE\s+'[^']+'\s*",
        f"WHERE item_name IN ({items_formatted})",
        new_sql,
        flags=re.IGNORECASE,
    )

    if new_sql == original_sql:
        return None

    return new_sql


def _build_no_item_filter_sql(original_sql: str) -> Optional[str]:
    """Строит fallback SQL, полностью убирая фильтрацию по item_name (mart.price_facts).

    Используется как крайняя мера, когда даже с реальными названиями из samples
    ничего не нашлось. Оставляет только фильтры по period и price_source.
    """
    sql_lower = original_sql.lower().strip()
    if "price_facts" not in sql_lower:
        return None

    # Убираем все строки, содержащие item_name
    lines = original_sql.split('\n')
    filtered_lines = []
    item_filter_removed = False
    for line in lines:
        stripped = line.strip()
        if 'item_name' in stripped.lower():
            item_filter_removed = True
            continue
        if item_filter_removed and stripped:
            # Убираем leading AND/OR
            stripped = re.sub(r'^(AND|OR)\s+', '', stripped, flags=re.IGNORECASE)
            item_filter_removed = False
        if stripped:
            filtered_lines.append(stripped)

    if not item_filter_removed:
        filtered_lines = [l for l in lines if 'item_name' not in l.lower()]

    fallback_sql = '\n'.join(filtered_lines).strip()
    
    # Убираем пустые WHERE
    fallback_sql = re.sub(r'WHERE\s*AND', 'WHERE', fallback_sql, flags=re.IGNORECASE)
    fallback_sql = re.sub(r'WHERE\s*$', '', fallback_sql, flags=re.IGNORECASE)
    
    if not fallback_sql or 'select' not in fallback_sql.lower():
        return None
    
    return fallback_sql


def _build_fallback_sql(original_sql: str) -> Optional[str]:
    """Строит fallback SQL, убирая price_source и смягчая ILIKE-условия.
    
    Если оригинальный SQL не нашёл данных, пробуем:
    1. Убрать условие по price_source
    2. Сохранить ORDER BY и LIMIT (если были)
    """
    sql_lower = original_sql.lower().strip()
    
    # Проверяем, что это SELECT из mart.price_facts
    if "price_facts" not in sql_lower:
        return None
    
    # Извлекаем ORDER BY и LIMIT чтобы сохранить их после трансформации
    order_by_match = re.search(r'\bORDER\s+BY\s+.+$', original_sql, re.IGNORECASE | re.DOTALL)
    order_by_clause = order_by_match.group(0) if order_by_match else ""
    
    # Убираем ORDER BY и LIMIT из основной части для обработки
    core_sql = original_sql
    if order_by_clause:
        core_sql = core_sql[:order_by_match.start()].strip()
    
    # Убираем LIMIT из core если он был перед ORDER BY
    core_sql = re.sub(r'\s*LIMIT\s+\d+\s*$', '', core_sql, flags=re.IGNORECASE)
    
    # Убираем условие по price_source
    lines = core_sql.split('\n')
    filtered_lines = []
    price_source_removed = False
    for line in lines:
        stripped = line.strip()
        if 'price_source' in stripped.lower():
            price_source_removed = True
            continue
        if price_source_removed and stripped:
            # Убираем leading AND/OR
            stripped = re.sub(r'^(AND|OR)\s+', '', stripped, flags=re.IGNORECASE)
            price_source_removed = False
        if stripped:
            filtered_lines.append(stripped)
    
    if not price_source_removed:
        filtered_lines = [l for l in lines if 'price_source' not in l.lower()]
    
    fallback_sql = '\n'.join(filtered_lines).strip()
    
    # Убираем пустые WHERE
    fallback_sql = re.sub(r'WHERE\s*AND', 'WHERE', fallback_sql, flags=re.IGNORECASE)
    fallback_sql = re.sub(r'WHERE\s*$', '', fallback_sql, flags=re.IGNORECASE)
    
    # Добавляем обратно ORDER BY и LIMIT
    if order_by_clause:
        fallback_sql += '\n' + order_by_clause
    
    # Если после всех изменений SQL стал пустым или некорректным
    if not fallback_sql or 'select' not in fallback_sql.lower():
        return None
    
    return fallback_sql


async def _execute_sql(
    sql_query: str,
    session: Optional[AsyncSession],
    request_id: str,
) -> tuple[List[Dict[str, Any]], Optional[str]]:
    """Выполняет SQL через read-only роль app_readonly (защита на уровне БД).

    Помимо keyword-blacklist валидации в codegen, Executor подключается к БД
    через отдельную роль с GRANT SELECT только на mart.*, поэтому любые попытки
    INSERT/UPDATE/DELETE/DROP и доступ к не-mart таблицам блокируются сервером.
    statement_timeout задаётся на уровне сессии в дополнение к REQUEST_TIMEOUT_S
    для LLM.
    """
    from src.core.db.database import readonly_session_maker
    from src.core.config import settings

    try:
        async with (session or readonly_session_maker()) as s:
            async with s.begin():
                await s.execute(
                    text(f"SET LOCAL statement_timeout = '{settings.DB_STATEMENT_TIMEOUT_MS}'")
                )
                result = await s.execute(text(sql_query))

            if result.returns_rows:
                columns = result.keys()
                rows = result.fetchmany(MAX_RESULT_ROWS)
                rows_list = [dict(zip(columns, row)) for row in rows]
                logger.info(
                    "Executor Node [{}]: query returned {} rows",
                    request_id,
                    len(rows_list),
                )
                return rows_list, None
            else:
                logger.info(
                    "Executor Node [{}]: query did not return rows",
                    request_id,
                )
                return [], None
    except Exception as exc:
        error_msg = str(exc)
        logger.error(
            "Executor Node [{}]: SQL execution failed: {}",
            request_id,
            error_msg,
        )
        return [], error_msg


async def executor_node(
    state: GraphState,
    session: Optional[AsyncSession] = None,
    **kwargs: Any,
) -> GraphState:
    from src.core.metrics import observe_node
    import time as _time
    _node_start = _time.monotonic()
    request_id = state.get("request_id", "?")[:8]
    sql_query = state.get("sql_query", "")
    validation_errors = state.get("validation_errors", [])
    schema = state.get("schema", [])

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

    # Пытаемся выполнить оригинальный SQL
    result, error = await _execute_sql(sql_query, session, request_id)

    # Если оригинальный SQL вернул ошибку — сразу возвращаем
    if error:
        state["sql_error"] = error
        state["sql_result"] = []
        state["trace"] = state.get("trace", {})
        state["trace"][NODE_EXECUTOR] = {
            "sql_query": sql_query,
            "row_count": 0,
            "error": error,
            "result_preview": [],
            "fallback_used": False,
        }
        return state

    # Если оригинальный SQL вернул данные — отлично
    if result:
        state["sql_result"] = result
        state["sql_error"] = None
        state["trace"] = state.get("trace", {})
        state["trace"][NODE_EXECUTOR] = {
            "sql_query": sql_query,
            "row_count": len(result),
            "error": None,
            "result_preview": result[:5],
            "fallback_used": False,
        }
        return state

    # Оригинальный SQL не вернул данных — пробуем серию fallback-ов
    logger.warning(
        "Executor Node [{}]: original SQL returned 0 rows, trying fallbacks",
        request_id,
    )

    # Собираем samples из схемы для fallback-ов с реальными названиями
    samples = _collect_samples_from_schema(schema)

    # Определяем порядок fallback-ов
    fallback_chain = []

    # Fallback 1: убрать price_source (существующий)
    fb1 = _build_fallback_sql(sql_query)
    if fb1 and fb1 != sql_query:
        fallback_chain.append(("без price_source", fb1))

    # Fallback 2: заменить ILIKE на реальные названия из samples
    if samples:
        fb2 = _build_samples_fallback_sql(sql_query, samples)
        if fb2 and fb2 != sql_query:
            fallback_chain.append(("с реальными названиями из samples", fb2))

    # Fallback 3: убрать price_source + заменить ILIKE на реальные названия
    if samples and fb1 and fb1 != sql_query:
        fb3 = _build_samples_fallback_sql(fb1, samples)
        if fb3 and fb3 != fb1 and fb3 != sql_query:
            fallback_chain.append(("без price_source + реальные названия", fb3))

    # Fallback 4: убрать фильтрацию по item_name_normalized вообще
    fb4 = _build_no_item_filter_sql(sql_query)
    if fb4 and fb4 != sql_query:
        fallback_chain.append(("без фильтра по названию", fb4))

    # Fallback 5: убрать price_source + убрать фильтр по названию
    if fb1 and fb1 != sql_query:
        fb5 = _build_no_item_filter_sql(fb1)
        if fb5 and fb5 != fb1 and fb5 != sql_query:
            fallback_chain.append(("без price_source + без фильтра по названию", fb5))

    # Пробуем каждый fallback по порядку
    for fb_label, fb_sql in fallback_chain:
        logger.info(
            "Executor Node [{}]: trying fallback '{}': {}",
            request_id,
            fb_label,
            fb_sql[:200],
        )
        fb_result, fb_error = await _execute_sql(fb_sql, session, request_id)

        if fb_error:
            logger.warning(
                "Executor Node [{}]: fallback '{}' failed: {}",
                request_id,
                fb_label,
                fb_error,
            )
            continue

        if fb_result:
            logger.info(
                "Executor Node [{}]: fallback '{}' returned {} rows",
                request_id,
                fb_label,
                len(fb_result),
            )
            state["sql_result"] = fb_result
            state["sql_error"] = None
            state["trace"] = state.get("trace", {})
            state["trace"][NODE_EXECUTOR] = {
                "sql_query": sql_query,
                "row_count": len(fb_result),
                "error": None,
                "result_preview": fb_result[:5],
                "fallback_used": True,
                "fallback_label": fb_label,
                "fallback_sql": fb_sql,
            }
            return state

        logger.warning(
            "Executor Node [{}]: fallback '{}' also returned 0 rows",
            request_id,
            fb_label,
        )

    # Все fallback-ы не дали результатов
    state["sql_result"] = []
    state["sql_error"] = None
    state["trace"] = state.get("trace", {})
    state["trace"][NODE_EXECUTOR] = {
        "sql_query": sql_query,
        "row_count": 0,
        "error": None,
        "result_preview": [],
        "fallback_used": len(fallback_chain) > 0,
        "fallbacks_tried": [label for label, _ in fallback_chain],
    }

    # Латентность узла для Prometheus.
    try:
        observe_node("executor", _time.monotonic() - _node_start)
    except Exception:
        pass

    return state