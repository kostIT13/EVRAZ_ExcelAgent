"""Проверка фикса: «цинковый лом» == «Лом цинка».

Проверяет:
1. Расширение слов вопроса синонимами материалов (entity_resolver).
2. Детерминированную правку codegen: item_name ILIKE '%цинк%' -> item_name = 'Лом цинка'.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.material_synonyms import material_noun_from_adjective
from src.services.entity_resolution.entity_resolver import _expand_query_words, _extract_query_words
from src.services.agent.nodes.codegen_node import (
    _find_exact_item_candidate,
    _refine_material_adjective_filter,
)

QUESTION = "Какова была минимальная цена на цинковый лом за все месяцы?"

# Кандидаты, как их вернёт entity_resolver (после фикса «Лом цинка» — первый).
CANDIDATES = [
    {"entity_type": "item", "entity_value": "Лом цинка", "score": 1.0303, "method": "trigram"},
    {"entity_type": "item", "entity_value": "Лом Р18", "score": 0.5, "method": "trigram"},
    {"entity_type": "item", "entity_value": "Лом латуни", "score": 0.4, "method": "trigram"},
    {"entity_type": "item", "entity_value": "Лом алюминия", "score": 0.3077, "method": "trigram"},
]

# SQL, который раньше генерировал codegen (широкий %цинк%).
SQL_BEFORE = """SELECT MIN(fp.value) AS минимальная_цена
FROM mart.price_facts fp
WHERE fp.item_name ILIKE '%цинк%'
  AND fp.price_type = 'среднерыночная'"""


def main() -> None:
    print("=== 1. Синонимы материалов ===")
    for w in ("цинковый", "медный", "алюминиевый", "латунный", "бронзовый", "свинцовый"):
        print(f"  {w!r:20} -> {material_noun_from_adjective(w)!r}")

    print("\n=== 2. Расширение слов вопроса ===")
    words = _extract_query_words(QUESTION)
    expanded = _expand_query_words(words)
    print(f"  слова: {words}")
    print(f"  расширено: {expanded}")
    assert "цинк" in expanded, "Ожидалось расширение 'цинковый' -> 'цинк'"

    print("\n=== 3. Поиск точного кандидата ===")
    exact = _find_exact_item_candidate(CANDIDATES, "цинк")
    print(f"  точный кандидат для 'цинк': {exact!r}")
    assert exact == "Лом цинка", f"Ожидалось 'Лом цинка', получено {exact!r}"

    print("\n=== 4. Детерминированная правка SQL ===")
    refined = _refine_material_adjective_filter(QUESTION, SQL_BEFORE, CANDIDATES)
    print(f"  ДО:    {SQL_BEFORE!r}")
    print(f"  ПОСЛЕ: {refined!r}")
    assert "item_name = 'Лом цинка'" in refined, "Правка не применилась"
    assert "%цинк%" not in refined, "Широкий фильтр %цинк% не заменён"
    print("\n  OK: широкий %цинк% заменён на точное item_name = 'Лом цинка'")

    print("\n=== 5. Проверка итогового SQL на реальных данных ===")
    # Итоговый SQL должен вернуть 164220 (минимальная среднерыночная цена на Лом цинка).
    final_sql = """SELECT MIN(fp.value) AS минимальная_цена
FROM mart.price_facts fp
WHERE fp.item_name = 'Лом цинка'
  AND fp.price_type = 'среднерыночная'"""
    print(f"  SQL: {final_sql}")
    print("  (выполняется в БД отдельной командой)")


if __name__ == "__main__":
    main()
