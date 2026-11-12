"""А-9 (ПМИ): на паузе уточнения агент задаёт вопрос текстом ответа.

Пока waiting_for_input приходил с пустым answer, чат показывал пустое сообщение,
а в query_logs попадала запись без текста уточнения.
"""
import time

from langgraph.types import Interrupt

from src.services.agent.graph import (
    CLARIFY_FALLBACK_QUESTION,
    STATUS_WAITING,
    LangGraphAgent,
    _clarifying_answer,
)


def _state(**extra):
    base = {
        "question": "Цена на лом меди",
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
        "retry_count": 0,
        "needs_retry": False,
        "retry_reason": "",
        "trace": {},
        "error": None,
    }
    base.update(extra)
    return base


def _finalize(state):
    return LangGraphAgent._finalize(
        LangGraphAgent.__new__(LangGraphAgent),
        state,
        state["question"],
        "req-1",
        "t-1",
        time.monotonic(),
        "detailed",
    )


def test_waiting_answer_carries_the_clarifying_question_and_options():
    state = _state(
        **{
            "__interrupt__": [
                Interrupt(
                    value={
                        "question": "Уточните источник цены по логу меди",
                        "options": ["среднерыночная", "поставщик"],
                    }
                )
            ]
        }
    )
    result = _finalize(state)

    assert result.status == STATUS_WAITING
    assert result.answer.startswith("Уточните источник цены по логу меди")
    assert "среднерыночная" in result.answer and "поставщик" in result.answer
    assert result.waiting_question == {
        "question": "Уточните источник цены по логу меди",
        "options": ["среднерыночная", "поставщик"],
    }


def test_waiting_answer_falls_back_when_payload_has_no_question_text():
    state = _state(
        **{
            "__interrupt__": [
                Interrupt(value={"question": "", "options": ["среднерыночная"]})
            ]
        }
    )
    result = _finalize(state)

    assert result.status == STATUS_WAITING
    assert result.answer.startswith(CLARIFY_FALLBACK_QUESTION)
    assert result.waiting_question["question"] == CLARIFY_FALLBACK_QUESTION


def test_waiting_accepts_plain_string_interrupt_payload():
    state = _state(**{"__interrupt__": [Interrupt(value="Уточните период")]})
    result = _finalize(state)

    assert result.status == STATUS_WAITING
    assert result.answer == "Уточните период"


def test_waiting_without_options_adds_no_hint_line():
    assert _clarifying_answer("Можете уточнить подробнее?", []) == (
        "Можете уточнить подробнее?"
    )


def test_clarifying_answer_lists_at_most_five_options():
    answer = _clarifying_answer("Что считать?", [f"вариант {i}" for i in range(9)])

    assert answer.count("вариант") == 5
    assert "вариант 4." in answer
