from src.services.agent.nodes.answer_node import _deterministic_answer
from src.services.agent.nodes.classifier_node import _heuristic_domain, _pick_best_candidate
from src.services.agent.nodes.verifier_node import (
    _format_result_deterministically,
    _sanity_check_result,
)


# --- classifier helpers ---


def test_pick_best_candidate_by_score():
    candidates = [
        {"entity_type": "item", "entity_value": "Лом латуни", "score": 0.4},
        {"entity_type": "item", "entity_value": "Лом цинка", "score": 1.03},
        {"entity_type": "supplier", "entity_value": "ООО Металл", "score": 0.9},
    ]
    assert _pick_best_candidate(candidates, "item") == "Лом цинка"
    assert _pick_best_candidate(candidates, "supplier") == "ООО Металл"


def test_pick_best_candidate_no_match_returns_none():
    assert _pick_best_candidate([], "item") is None
    assert _pick_best_candidate(
        [{"entity_type": "supplier", "entity_value": "X", "score": 1.0}], "item"
    ) is None


def test_heuristic_domain_metrics_keywords():
    assert _heuristic_domain("План и факт по шихте на 2 блок") == "metrics"
    assert _heuristic_domain("Остаток угля на складе") == "metrics"
    assert _heuristic_domain("Отклонение по бюджету") == "metrics"


def test_heuristic_domain_prices_keywords():
    assert _heuristic_domain("Цена на лом меди") == "prices"
    assert _heuristic_domain("Среднерыночная цена на латунь") == "prices"
    assert _heuristic_domain("Аукцион по бронзе") == "prices"


def test_heuristic_domain_generic():
    assert _heuristic_domain("Привет, как дела?") == "generic"
    assert _heuristic_domain("") == "generic"


# --- answer helpers ---


def test_deterministic_answer_concise():
    assert _deterministic_answer([{"цена": 100}], is_concise=True) == "не найдено"
    assert _deterministic_answer([], is_concise=True) == "не найдено"


def test_deterministic_answer_detailed_with_data():
    answer = _deterministic_answer([{"цена": 100}], is_concise=False)
    assert "Получены данные" in answer


def test_deterministic_answer_detailed_without_data():
    answer = _deterministic_answer([], is_concise=False)
    assert "Не удалось найти ответ" in answer


# --- verifier helpers ---


def test_sanity_check_empty_result():
    assert _sanity_check_result([]) == ["empty_result"]


def test_sanity_check_large_result():
    rows = [{"value": i} for i in range(1001)]
    issues = _sanity_check_result(rows)
    assert any(i.startswith("large_result:") for i in issues)


def test_sanity_check_all_null_values():
    issues = _sanity_check_result([{"value": None, "item_name": None}])
    assert "all_null_values" in issues


def test_sanity_check_ok():
    assert _sanity_check_result([{"value": 100.0}]) == []


def test_format_result_deterministically_empty():
    assert _format_result_deterministically([]) == "Данные не найдены."


def test_format_result_deterministically_numbers():
    result = [{"минимальная_цена": 164220.0}]
    formatted = _format_result_deterministically(result)
    assert "164 220" in formatted
    assert "минимальная цена" in formatted


def test_format_result_deterministically_truncates():
    rows = [{"value": i} for i in range(15)]
    formatted = _format_result_deterministically(rows, max_rows=5)
    assert "ещё 10 строк" in formatted


def test_format_result_deterministically_skips_none():
    result = [{"value": None, "item_name": "Лом меди"}]
    formatted = _format_result_deterministically(result)
    assert "Лом меди" in formatted
    assert "None" not in formatted