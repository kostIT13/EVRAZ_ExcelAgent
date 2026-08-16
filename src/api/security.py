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
    if not settings.API_KEY:
        return "dev"
    if api_key != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return api_key