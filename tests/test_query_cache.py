import asyncio
from types import SimpleNamespace

from src.services.entity_resolution.query_cache import _hash_question, _normalize_question


def test_normalize_question_lowercases_and_strips():
    assert _normalize_question("  Какова Цена на Медь?  ") == "какова цена на медь"


def test_normalize_question_removes_punctuation():
    assert _normalize_question("Цена на медь, латунь!") == "цена на медь латунь"


def test_normalize_question_collapses_spaces():
    assert _normalize_question("цена   на   медь") == "цена на медь"


def test_normalize_question_empty():
    assert _normalize_question("") == ""
    assert _normalize_question("   ") == ""


def test_hash_question_deterministic():
    assert _hash_question("Какая цена на медь?") == _hash_question("какая цена на медь")


def test_hash_question_differs_by_response_mode():
    assert _hash_question("Какая цена на медь?", "detailed") != _hash_question(
        "Какая цена на медь?", "concise"
    )


def test_hash_question_is_sha256_hex():
    h = _hash_question("вопрос")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_cached_result_sources_reads_stored_list():
    from src.services.agent.graph import _cached_result_sources

    sources = [{"chunk": "data.xlsx · лист «цв.лом(на дек25)» · 2025-12", "source_id": 67}]
    assert _cached_result_sources({"result": {"sources": sources}}) == sources


def test_cached_result_sources_empty_for_rows_without_sources():
    from src.services.agent.graph import _cached_result_sources

    assert _cached_result_sources({}) == []
    assert _cached_result_sources({"result": {"data": []}}) == []
    assert _cached_result_sources({"result": {"sources": []}}) == []


def _agent_result(trace):
    from src.services.agent.graph import AgentResult

    return AgentResult(
        answer="ответ",
        confidence=0.9,
        request_id="req-1",
        question="вопрос",
        latency_ms=31000,
        trace=trace,
        query_type="lookup",
        sql_query="SELECT 1",
        sql_result=[{"v": 1}],
        retry_count=0,
        status="success",
    )


def test_cache_agent_trace_keeps_node_steps_and_provenance():
    from src.services.agent.graph import _cache_agent_trace

    snapshot = _cache_agent_trace(
        _agent_result(
            {
                "classifier": {"query_type": "lookup", "duration_ms": 800},
                "verifier": {"confidence": 0.9, "duration_ms": 120},
                "conversation_history": [{"role": "user", "content": "…"}],
            }
        )
    )

    assert snapshot["classifier"]["duration_ms"] == 800
    assert snapshot["verifier"]["confidence"] == 0.9
    assert "conversation_history" not in snapshot
    assert snapshot["source_request_id"] == "req-1"
    assert snapshot["source_latency_ms"] == 31000


def test_cached_agent_trace_replays_nodes_and_marks_cache():
    from src.services.agent.graph import _cached_agent_trace

    trace = _cached_agent_trace(
        {
            "sql_query": "SELECT 1",
            "agent_trace": {"classifier": {"query_type": "lookup"}, "source_latency_ms": 31000},
        }
    )

    assert trace["classifier"] == {"query_type": "lookup"}
    assert trace["from_cache"] is True
    assert trace["cached_sql"] == "SELECT 1"
    assert trace["source_latency_ms"] == 31000


def test_cached_agent_trace_without_snapshot_is_cache_marker_only():
    """Старые строки кэша снимка узлов не хранят."""
    from src.services.agent.graph import _cached_agent_trace

    trace = _cached_agent_trace({"sql_query": "SELECT 1"})

    assert trace == {"from_cache": True, "cached_sql": "SELECT 1"}


def test_cached_payload_stores_agent_trace_next_to_answer():
    from decimal import Decimal

    from src.services.entity_resolution.query_cache import _cached_payload

    payload = _cached_payload(
        {"data": [{"v": Decimal("1.5")}], "formatted_answer": "ответ"},
        {"classifier": {"query_type": "lookup"}},
    )

    assert payload["data"] == [{"v": 1.5}]
    assert payload["agent_trace"] == {"classifier": {"query_type": "lookup"}}


def test_cached_payload_without_trace_keeps_previous_shape():
    from src.services.entity_resolution.query_cache import _cached_payload

    assert _cached_payload({"formatted_answer": "ответ"}) == {
        "formatted_answer": "ответ"
    }
    assert _cached_payload(None) is None


def test_cached_chart_restores_series_and_type():
    """Попадание в кэш обязано отдать и график: checkpoint'а потока у него нет."""
    from src.services.agent.graph import _cached_chart

    points = [
        {"period": "2025-01", "value": 891480.0},
        {"period": "2025-02", "value": 906729.0},
    ]

    assert _cached_chart({"result": {"chart_data": points, "chart_type": "line"}}) == (
        points,
        "line",
    )


def test_cached_chart_empty_without_a_series():
    from src.services.agent.graph import _cached_chart

    assert _cached_chart({}) == (None, None)
    assert _cached_chart({"result": {"chart_data": [], "chart_type": "bar"}}) == (None, None)
    # Одна точка — не ряд; неизвестный тип графика не восстанавливаем.
    assert _cached_chart(
        {"result": {"chart_data": [{"period": "2025-01", "value": 1.0}], "chart_type": "pie"}}
    ) == (None, None)


def test_cached_confidence_reads_stored_value():
    """Попадание в кэш обязано отдать уверенность прогона-источника, а не 1.0."""
    from src.services.agent.graph import _cached_confidence

    assert _cached_confidence({"result": {"confidence": 0.0}}) == 0.0
    assert _cached_confidence({"result": {"confidence": 0.7}}) == 0.7


def test_cached_confidence_falls_back_to_verifier_snapshot():
    from src.services.agent.graph import _cached_confidence

    cached = {"result": {"formatted_answer": "ответ"}, "agent_trace": {"verifier": {"confidence": 0.0}}}

    assert _cached_confidence(cached) == 0.0


def test_cached_confidence_ignores_garbage_and_clamps():
    from src.services.agent.graph import _cached_confidence

    assert _cached_confidence({"result": {"confidence": "0.5"}}) == 1.0
    assert _cached_confidence({"result": {"confidence": True}}) == 1.0
    assert _cached_confidence({"result": {"confidence": 4.0}}) == 1.0
    # Строки, закэшированные до появления поля и без снимка узлов.
    assert _cached_confidence({"result": {"formatted_answer": "ответ"}}) == 1.0


def test_clear_on_borrowed_session_deletes_without_committing():
    """Сессия вызывающего (удаление файла) владеет транзакцией — коммитит она."""
    from types import SimpleNamespace

    from src.services.entity_resolution.query_cache import QueryCacheService

    class _Session:
        def __init__(self):
            self.statements = []

        async def execute(self, statement):
            self.statements.append(str(statement))
            return SimpleNamespace(rowcount=7)

        async def flush(self):
            self.flushed = True

        async def commit(self):
            raise AssertionError("заимствованную сессию кэш коммитить не должен")

    session = _Session()

    cleared = asyncio.run(QueryCacheService().clear(session=session))

    assert cleared == 7
    assert session.flushed is True
    assert len(session.statements) == 1
    assert "DELETE FROM query_cache" in session.statements[0]


def test_delete_file_invalidates_answer_cache():
    """Строка кэша переживает удаление витрины: без сброса вопрос ответил бы из кэша."""
    from src.services.db_tables.file_service.service import FileService

    calls = []

    class _Session:
        flushed = False

        async def execute(self, statement):
            calls.append(str(statement))
            return SimpleNamespace(rowcount=2)

        async def flush(self):
            self.flushed = True

    class _Repo:
        async def get_by_id(self, file_id):
            return SimpleNamespace(id=file_id)

        async def delete(self, record):
            calls.append(f"file:{record.id}")

    service = FileService(_Session())
    service.repository = _Repo()

    asyncio.run(service.delete(3))

    assert calls == ["file:3", "DELETE FROM query_cache"]