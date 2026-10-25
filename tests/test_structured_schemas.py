import pytest
from pydantic import ValidationError

from src.services.agent.structured_schemas import (
    ClassifierResult,
    DisambiguationResult,
    PlannerResult,
    VerifierResult,
)


def test_classifier_result_null_lists_coerced_to_empty():
    result = ClassifierResult(
        query_type="aggregate",
        domain="prices",
        entities=None,
        relevant_sheet_ids=None,
    )
    assert result.entities == []
    assert result.relevant_sheet_ids == []


def test_classifier_result_defaults():
    result = ClassifierResult(query_type="lookup")
    assert result.domain == "generic"
    assert result.entities == []
    assert result.relevant_sheet_ids == []


def test_disambiguation_result_null_fields_coerced():
    result = DisambiguationResult(
        needs_disambiguation=False,
        clarifying_question=None,
        options=None,
        suggested_resolution=None,
    )
    assert result.clarifying_question == ""
    assert result.options == []
    assert result.suggested_resolution is None


def test_disambiguation_result_defaults():
    result = DisambiguationResult()
    assert result.needs_disambiguation is False
    assert result.clarifying_question == ""
    assert result.options == []


def test_planner_result_null_plan_coerced():
    assert PlannerResult(plan=None).plan == ""


def test_verifier_result_null_fields_coerced():
    result = VerifierResult(
        is_correct=True,
        confidence=0.9,
        issues=None,
        retry_reason=None,
    )
    assert result.issues == []
    assert result.retry_reason == ""


def test_verifier_result_defaults():
    result = VerifierResult()
    assert result.is_correct is True
    assert result.confidence == 0.8
    assert result.issues == []
    assert result.needs_retry is False


def test_verifier_result_confidence_bounds():
    with pytest.raises(ValidationError):
        VerifierResult(confidence=1.5)
    with pytest.raises(ValidationError):
        VerifierResult(confidence=-0.1)
    assert VerifierResult(confidence=0.0).confidence == 0.0
    assert VerifierResult(confidence=1.0).confidence == 1.0