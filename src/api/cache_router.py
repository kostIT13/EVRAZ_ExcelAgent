from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from src.api.security import verify_api_key
from src.core.logging_settings import logger
from src.core.ratelimit import get_limiter, cache_clear_limit
from src.services.entity_resolution.query_cache import query_cache_service

router = APIRouter(prefix="/cache", tags=["cache"])
_limiter = get_limiter()


@router.post("/clear", status_code=200)
@_limiter.limit(cache_clear_limit)
async def clear_cache(
    request: Request,
    _key: str = Depends(verify_api_key),
):
    logger.info("Cache clear requested")
    cleared = await query_cache_service.clear()
    logger.info("Cache clear done: {} records removed", cleared)
    return {"message": f"Cache cleared: {cleared} records removed", "cleared": cleared}