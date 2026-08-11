"""Rate limiting через slowapi.

Инициализация: limiter = get_limiter(). Используется в main.py как middleware
и в защищённых роутерах через @limiter.limit().
"""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from src.core.config import settings

_limiter: Limiter = Limiter(key_func=get_remote_address)


def get_limiter() -> Limiter:
    return _limiter


def ask_limit() -> str:
    return settings.RATE_LIMIT_ASK or "30/minute"


def upload_limit() -> str:
    return settings.RATE_LIMIT_UPLOAD or "10/minute"