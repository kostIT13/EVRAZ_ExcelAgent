"""Регрессионные тесты: «цинковый лом» == «лом цинка» (синонимы материалов).

Проверяют:
1. Словарь синонимов материалов (src.core.material_synonyms).
2. Расширение слов вопроса в entity_resolver.
3. Детерминированную правку codegen: item_name ILIKE '%цинк%' -> item_name = 'Лом цинка'.
"""
from __future__ import annotations

from src.core.material_synonyms import genitive_for_material, material_noun_from_adjective
from src.services.agent.nodes.answer_node import _has_digit, _result_has_numbers
from src.services.agent.nodes.codegen_node import (
    _find_exact_item_candidate,
    _refine_material_adjective_filter,
)
from src.services.agent.nodes.verifier_node import _format_result_deterministically
from src.services.entity_resolution.entity_resolver import (
    _expand_query_words,
    _extract_query_words,
)


def test_material_noun_from_adjective():
    assert material_noun_from_adjective("цинковый") == "цинк"
    assert material_noun_from_adjective("медный") == "медь"
    assert material_noun_from_adjective("алюминиевый") == "алюминий"
    assert material_noun_from_adjective("латунный") == "латунь"
    assert material_noun_from_adjective("обычный") is None


def test_genitive_for_material():
    assert genitive_for_material("цинк") == "цинка"
    assert genitive_for_material("медь") == "меди"
    assert genitive_for_material("алюминий") == "алюминия"


def test_expand_query_words_zinc():
    words = _extract_query_words("Какова была минимальная цена на цинковый лом за все месяцы?")
    expanded = _expand_query_words(words)
    assert "цинковый" in expanded
    assert "цинк" in expanded, "Ожидалось расширение «цинковый» -> «цинк»"


def test_find_exact_item_candidate():
    candidates = [
        {"entity_type": "item", "entity_value": "Лом цинка", "score": 1.03, "method": "trigram"},
        {"entity_type": "item", "entity_value": "Лом латуни", "score": 0.4, "method": "trigram"},
        {"entity_type": "supplier", "entity_value": "ООО Металл", "score": 0.5, "method": "trigram"},
    ]
    assert _find_exact_item_candidate(candidates, "цинк") == "Лом цинка"
    assert _find_exact_item_candidate(candidates, "несуществующий") is None


def test_refine_material_adjective_filter():
    question = "Какова была минимальная цена на цинковый лом за все месяцы?"
    sql = (
        "SELECT MIN(fp.value) AS минимальная_цена\n"
        "FROM mart.price_facts fp\n"
        "WHERE fp.item_name ILIKE '%цинк%'\n"
        "  AND fp.price_type = 'среднерыночная'"
    )
    candidates = [
        {"entity_type": "item", "entity_value": "Лом цинка", "score": 1.03, "method": "trigram"},
    ]
    refined = _refine_material_adjective_filter(question, sql, candidates)
    assert "item_name = 'Лом цинка'" in refined
    assert "%цинк%" not in refined


def test_refine_material_adjective_filter_no_candidate_unchanged():
    """Если кандидата нет — SQL не должен меняться."""
    question = "Какова была минимальная цена на цинковый лом за все месяцы?"
    sql = "SELECT 1"
    refined = _refine_material_adjective_filter(question, sql, [])
    assert refined == sql


def test_result_has_numbers():
    assert _result_has_numbers([{"минимальная_цена": 164220.0}]) is True
    assert _result_has_numbers([{"минимальная_цена": 164220}]) is True
    assert _result_has_numbers([{"item_name": "Лом цинка"}]) is False
    assert _result_has_numbers([]) is False


def test_has_digit():
    assert _has_digit("Минимальная среднерыночная цена на цинковый") is False
    assert _has_digit("Минимальная цена: 164 220 руб/тн") is True
    assert _has_digit("") is False


def test_deterministic_formatter_russian_aggregate_columns():
    """Детерминированный форматтер должен распознавать русские имена колонок."""
    result = [{"минимальная_цена": 164220.0}]
    formatted = _format_result_deterministically(result)
    assert "164 220" in formatted
    assert "минимальная цена" in formatted

    result = [{"максимальная_цена": 602922.0}]
    formatted = _format_result_deterministically(result)
    assert "602 922" in formatted
    assert "максимальная цена" in formatted