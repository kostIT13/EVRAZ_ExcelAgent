from __future__ import annotations

from fastapi import APIRouter, Depends
from src.api.schemas import LLMConfigResponse
from src.api.security import verify_api_key
from src.core.config import settings
from src.services.agent.nodes.routing import MAX_RETRY_COUNT

router = APIRouter(prefix="/llm", tags=["llm"])


@router.get("/config", response_model=LLMConfigResponse)
async def get_llm_config(_key: str = Depends(verify_api_key)) -> LLMConfigResponse:
    """Возвращает текущую конфигурацию LLM: модель, temperature, retry и таймауты."""
    return LLMConfigResponse(
        model=settings.LLM_MODEL_PRIMARY,
        base_url=settings.LLM_BASE_URL,
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=settings.LLM_MAX_TOKENS,
        request_timeout_s=settings.REQUEST_TIMEOUT_S,
        llm_max_retries=settings.MAX_RETRIES,
        graph_max_retry_count=MAX_RETRY_COUNT,
        max_codegen_attempts=3,
    )
