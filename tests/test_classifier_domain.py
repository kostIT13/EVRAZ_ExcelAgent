from src.services.agent.nodes.classifier_node import _heuristic_domain


def test_consumption_from_silos_is_metrics():
    q = "Каков суммарный расход из силосов по всем строкам поставщика «Краснокаменская КЖ» на листе «2 блок»?"
    assert _heuristic_domain(q) == "metrics"


def test_budget_deviation_is_metrics():
    assert _heuristic_domain("Отклонение по бюджету на шихту") == "metrics"


def test_price_question_still_prices():
    q = "Какова среднерыночная цена на Лом меди кусок в декабре 2025?"
    assert _heuristic_domain(q) == "prices"


def test_supplier_price_question_still_prices():
    q = "Какая цена предложения победителя на аукционе за лом латуни?"
    assert _heuristic_domain(q) == "prices"