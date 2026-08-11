"""Auth (API-key) + rate limiting (slowapi) для защищённых эндпоинтов.

- /files/* и /ask/* требуют API-ключ в заголовке X-API-Key (или OAuth2 Bearer).
- Rate limiting через slowapi (ключ по клиентскому IP / API-ключу).

Конфигурация:
- API_KEY (в .env) — ожидаемый ключ. Если пустой — auth отключён (dev-режим).
- RATE_LIMIT_ASK, RATE_LIMIT_UPLOAD — лимиты slowapi.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader

from src.core.config import settings

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(
    request: Request,
    api_key: Optional[str] = Depends(API_KEY_HEADER),
) -> str:
    """Проверяет API-ключ. Если settings.API_KEY пуст — пропускает (dev)."""
    if not settings.API_KEY:
        return "dev"
    if api_key != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return api_key