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