import pytest
from pydantic import ValidationError

from src.api.schemas import AskRequest, AskResponse, ConversationTurn


def test_ask_request_valid():
    req = AskRequest(question="Какая цена на медь?")
    assert req.question == "Какая цена на медь?"
    assert req.top_k == 10
    assert req.mode == "auto"
    assert req.response_mode == "detailed"
    assert req.conversation_history == []
    assert req.conversation_id is None


def test_ask_request_empty_question_rejected():
    with pytest.raises(ValidationError):
        AskRequest(question="")


def test_ask_request_invalid_mode_rejected():
    with pytest.raises(ValidationError):
        AskRequest(question="вопрос", mode="unknown_mode")


def test_ask_request_invalid_response_mode_rejected():
    with pytest.raises(ValidationError):
        AskRequest(question="вопрос", response_mode="verbose")


def test_ask_request_top_k_bounds():
    with pytest.raises(ValidationError):
        AskRequest(question="вопрос", top_k=0)
    with pytest.raises(ValidationError):
        AskRequest(question="вопрос", top_k=51)
    assert AskRequest(question="вопрос", top_k=1).top_k == 1
    assert AskRequest(question="вопрос", top_k=50).top_k == 50


def test_conversation_turn_role_pattern():
    assert ConversationTurn(role="user", content="привет").role == "user"
    assert ConversationTurn(role="assistant", content="ответ").role == "assistant"
    with pytest.raises(ValidationError):
        ConversationTurn(role="system", content="нельзя")


def test_ask_response_confidence_bounds():
    with pytest.raises(ValidationError):
        AskResponse(answer="ответ", confidence=1.5, request_id="r1", latency_ms=10)
    with pytest.raises(ValidationError):
        AskResponse(answer="ответ", confidence=-0.1, request_id="r1", latency_ms=10)
    resp = AskResponse(answer="ответ", confidence=0.7, request_id="r1", latency_ms=10)
    assert resp.confidence == 0.7
    assert resp.status == "success"
    assert resp.mode_used == "rag"