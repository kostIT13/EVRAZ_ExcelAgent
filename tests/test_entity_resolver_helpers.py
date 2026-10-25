from src.services.entity_resolution.entity_resolver import (
    EntityCandidate,
    _expand_query_words,
    _extract_query_words,
    _unique,
)


def test_extract_query_words_skips_stopwords():
    words = _extract_query_words(
        "Какова была минимальная цена на цинковый лом за все месяцы?"
    )
    assert "цинковый" in words
    assert "лом" in words
    assert "какова" not in words
    assert "цена" not in words


def test_extract_query_words_dedups():
    words = _extract_query_words("медь медь латунь")
    assert words == ["медь", "латунь"]


def test_extract_query_words_max_words():
    words = _extract_query_words(
        "медь латунь бронза никель цинк свинец алюминий олово железо сталь чугун",
        max_words=3,
    )
    assert words == ["медь", "латунь", "бронза"]


def test_extract_query_words_ignores_short_words():
    words = _extract_query_words("на медь и лом")
    assert "на" not in words
    assert "и" not in words


def test_expand_query_words_adds_material_nouns():
    words = _expand_query_words(["цинковый", "лом"])
    assert "цинк" in words
    assert "цинковый" in words


def test_unique_strips_and_dedups():
    assert _unique([" a ", "a", "", "b", "a"]) == ["a", "b"]
    assert _unique([]) == []


def test_entity_candidate_to_dict_rounds_score():
    c = EntityCandidate(entity_type="item", entity_value="Лом цинка", score=1.03456, method="trigram")
    d = c.to_dict()
    assert d == {
        "entity_type": "item",
        "entity_value": "Лом цинка",
        "score": 1.0346,
        "method": "trigram",
    }