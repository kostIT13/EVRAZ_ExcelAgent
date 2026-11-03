from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from src.api.schemas import (
    LLMConfigResponse,
    LLMModelSwitchRequest,
    LLMModelSwitchResponse,
    LLMModelsResponse,
)
from src.api.security import verify_api_key
from src.core.config import settings
from src.core.logging_settings import logger
from src.services.agent.nodes.routing import MAX_RETRY_COUNT
from src.services.llm.llm_client import LLMClient

router = APIRouter(prefix="/llm", tags=["llm"])

# LLM_MODEL_PRIMARY на старте процесса. Горячая смена через PUT /llm/model живёт
# в памяти этого воркера и сбрасывается к этому значению перезапуском сервиса —
# приёмочная проверка Ф-4 по-прежнему правит .env и пересоздаёт контейнер.
MODEL_DEFAULT = settings.LLM_MODEL_PRIMARY
VOLATILE_NOTE = (
    "Переключение действует до перезапуска контейнера service; "
    "после него вернётся значение из .env."
)


def _error_text(exc: BaseException) -> str:
    return " ".join(str(exc).split())[:300]


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


@router.get("/models", response_model=LLMModelsResponse)
async def list_llm_models(_key: str = Depends(verify_api_key)) -> LLMModelsResponse:
    """Модели с LLM-прокси: переключать интерфейс предлагает только на них."""
    try:
        models = await LLMClient().list_models()
    except Exception as exc:
        logger.warning("LLM model list unavailable: {}", exc)
        return LLMModelsResponse(
            models=[],
            current=settings.LLM_MODEL_PRIMARY,
            default=MODEL_DEFAULT,
            listed=False,
            error=_error_text(exc),
        )
    return LLMModelsResponse(
        models=models,
        current=settings.LLM_MODEL_PRIMARY,
        default=MODEL_DEFAULT,
    )


@router.put("/model", response_model=LLMModelSwitchResponse)
async def switch_llm_model(
    payload: LLMModelSwitchRequest,
    _key: str = Depends(verify_api_key),
) -> LLMModelSwitchResponse:
    """Меняет модель на живом стенде без правки кода; ответ кандидата проверяется до смены."""
    previous = settings.LLM_MODEL_PRIMARY
    target = payload.model
    probe_ms = 0
    if payload.verify:
        try:
            probe_ms = await LLMClient().probe(target)
        except Exception as exc:
            logger.warning("Model switch rejected, '{}' did not answer: {}", target, exc)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Модель «{target}» не ответила: {_error_text(exc)}. Текущая модель не изменена.",
            ) from exc
    settings.LLM_MODEL_PRIMARY = target
    changed = previous != target
    logger.info(
        "LLM model switched via API: '{}' -> '{}' (probe {} ms)", previous, target, probe_ms
    )
    return LLMModelSwitchResponse(
        previous=previous,
        current=target,
        default=MODEL_DEFAULT,
        changed=changed,
        verified=payload.verify,
        probe_ms=probe_ms,
        note=VOLATILE_NOTE,
    )


@router.post("/model/reset", response_model=LLMModelSwitchResponse)
async def reset_llm_model(
    _key: str = Depends(verify_api_key),
) -> LLMModelSwitchResponse:
    """Возвращает модель, заданную в .env, — состояние после перезапуска сервиса."""
    previous = settings.LLM_MODEL_PRIMARY
    settings.LLM_MODEL_PRIMARY = MODEL_DEFAULT
    if previous != MODEL_DEFAULT:
        logger.info("LLM model reset to .env value: '{}' -> '{}'", previous, MODEL_DEFAULT)
    return LLMModelSwitchResponse(
        previous=previous,
        current=MODEL_DEFAULT,
        default=MODEL_DEFAULT,
        changed=previous != MODEL_DEFAULT,
        verified=False,
        note=VOLATILE_NOTE,
    )
