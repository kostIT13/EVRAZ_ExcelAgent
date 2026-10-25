from src.core.config import _coerce_bool


def test_coerce_bool_true_strings():
    for v in ("1", "true", "True", "TRUE", "yes", "on", "release", " 1 "):
        assert _coerce_bool(v) is True


def test_coerce_bool_false_strings():
    for v in ("0", "false", "False", "no", "off", ""):
        assert _coerce_bool(v) is False


def test_coerce_bool_actual_bool():
    assert _coerce_bool(True) is True
    assert _coerce_bool(False) is False


def test_coerce_bool_unknown_string_falls_back_to_bool():
    assert _coerce_bool("что-то") is True
    assert _coerce_bool("") is False


def test_coerce_bool_numeric():
    assert _coerce_bool(1) is True
    assert _coerce_bool(0) is False