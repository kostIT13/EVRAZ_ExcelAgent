"""Н-2/Н-1 (ПМИ): отказ модели доходит до журнала как статус + причина, без стека в ответе."""
import asyncio
import time

from src.services.agent.graph import LangGraphAgent, _last_failure_detail, failed_node


def _state(**extra):
    base = {
        "question": "цена?",
        "request_id": "11111111-1111-1111-1111-111111111111",
        "top_k": 30,
        "response_mode": "detailed",
        "conversation_id": "t-1",
        "conversation_history": [],
        "entity_candidates": [],
        "entities_for_prompt": None,
        "chart_request": None,
        "query_type": None,
        "entities": [],
        "relevant_sheets": [],
        "plan": None,
        "sql_query": "",
        "sql_result": [],
        "sql_error": None,
        "validation_errors": [],
        "confidence": 0.0,
        "answer": "",
        "retry_count": 3,
        "needs_retry": False,
        "retry_reason": "",
        "trace": {},
        "error": None,
    }
    base.update(extra)
    return base


def test_failed_node_records_codegen_cause():
    state = _state(
        validation_errors=["Ошибка генерации SQL: Request timed out."],
        trace={"codegen": {"error": "Request timed out."}},
    )
    out = asyncio.run(failed_node(state))

    assert out["error"] == "Ошибка генерации SQL: Request timed out."


def test_failed_node_falls_back_to_sql_error_then_generic():
    by_sql = asyncio.run(failed_node(_state(sql_error="column x does not exist")))
    assert "column x does not exist" in by_sql["error"]

    generic = asyncio.run(failed_node(_state()))
    assert generic["error"] == "Граф достиг ошибочного состояния"


def test_finalize_maps_error_to_failed_status_and_keeps_it_out_of_the_answer():
    state = _state(error="RateLimitError: 429 Rate limit reached by fault stub")
    result = LangGraphAgent._finalize(
        LangGraphAgent.__new__(LangGraphAgent),
        state,
        "цена?",
        "req-1",
        "t-1",
        time.monotonic(),
        "detailed",
    )

    assert result.status == "failed"
    assert result.error == "RateLimitError: 429 Rate limit reached by fault stub"
    assert "Traceback" not in result.answer
    assert "RateLimitError" not in result.answer  # пользователю — понятный текст, не исключение


def test_failure_detail_prefers_the_cause_over_the_generic_phrase():
    assert _last_failure_detail(_state(validation_errors=["first", "second"])) == "first"
    assert _last_failure_detail(_state(trace={"planner": {"error": "boom"}})) == "planner: boom"


def test_pipeline_writes_failure_status_and_reason_to_query_log():
    """Н-2: «ошибка в журнале» — строка query_logs со статусом и причиной отказа."""
    from src.core.db.models import QueryLog
    from src.services.agent.graph import AgentResult
    from src.services.generation.pipeline import GenerationPipeline

    class _Session:
        def __init__(self):
            self.added = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def add(self, obj):
            self.added.append(obj)

        async def commit(self):
            pass

    result = AgentResult(
        answer="Произошла внутренняя ошибка при обработке запроса. Пожалуйста, попробуйте позже.",
        confidence=0.0,
        request_id="req-1",
        question="цена?",
        latency_ms=4120,
        trace={},
        query_type="lookup",
        sql_query="",
        sql_result=[],
        retry_count=3,
        status="failed",
        error="Ошибка генерации SQL: 429 Rate limit reached by fault stub",
    )
    session = _Session()

    asyncio.run(
        GenerationPipeline.__new__(GenerationPipeline)._log_agent_to_db(
            result=result, session=session
        )
    )

    assert len(session.added) == 1
    row = session.added[0]
    assert isinstance(row, QueryLog)
    assert row.status == "failed"
    assert "429 Rate limit reached by fault stub" in row.error_message
