import pytest
from fastapi import HTTPException

from src.api.errors import (
    AppError,
    FileTooLargeError,
    NotFoundError,
    ProcessingError,
    ValidationError,
)
from src.api.security import verify_api_key
from src.core.config import settings


def test_verify_api_key_dev_mode_when_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", "")
    assert verify_api_key(None, api_key=None) == "dev"
    assert verify_api_key(None, api_key="anything") == "dev"


def test_verify_api_key_valid_key(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", "secret-key")
    assert verify_api_key(None, api_key="secret-key") == "secret-key"


def test_verify_api_key_invalid_key_raises_401(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", "secret-key")
    with pytest.raises(HTTPException) as exc_info:
        verify_api_key(None, api_key="wrong")
    assert exc_info.value.status_code == 401


def test_verify_api_key_missing_key_raises_401(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", "secret-key")
    with pytest.raises(HTTPException) as exc_info:
        verify_api_key(None, api_key=None)
    assert exc_info.value.status_code == 401


def test_app_error_default_status_400():
    err = AppError("плохой запрос")
    assert err.status_code == 400
    assert err.message == "плохой запрос"


def test_app_error_custom_status_code():
    err = AppError("ошибка", status_code=418)
    assert err.status_code == 418


def test_error_hierarchy_status_codes():
    assert NotFoundError("нет").status_code == 404
    assert ValidationError("невалидно").status_code == 422
    assert FileTooLargeError("слишком большой").status_code == 413
    assert ProcessingError("упало").status_code == 500
    assert issubclass(NotFoundError, AppError)
    assert issubclass(ProcessingError, AppError)