"""Заглушка OpenAI-совместимого API для проверок надёжности (ПМИ п. 5.2, метод 6.3).

Эмулирует сбои модели, которые иначе нельзя воспроизвести по требованию: таймаут ответа,
HTTP 429 (ограничение частоты) и пустой ответ. Режим переключается на ходу, поэтому один
и тот же стенд проходит и ветку успеха, и ветку отказа.

Запуск на стенде:
    python -m benchmark.llm_fault_stub            # :8100, режим normal
    FAULT_MODE=rate_limit python -m benchmark.llm_fault_stub

Переключение режима без перезапуска:
    curl -X POST http://localhost:8100/admin/fault -d '{"mode":"timeout"}'
    curl http://localhost:8100/admin/stats        # счётчики обращений по режимам

Агент переключается на заглушку без правки кода: LLM_BASE_URL=http://host.docker.internal:8100/v1
в .env (или PUT /api/llm/model на стенде — смена модели в памяти сервиса).
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

FAULT_MODES = ("normal", "timeout", "rate_limit", "empty", "error_500")
DEFAULT_TIMEOUT_HOLD_S = 75.0

MODE = os.environ.get("FAULT_MODE", "normal")
TIMEOUT_HOLD_S = float(os.environ.get("FAULT_TIMEOUT_HOLD_S", DEFAULT_TIMEOUT_HOLD_S))

_stats: Dict[str, Any] = {"started_at": time.time(), "requests": 0, "by_mode": {}}

app = FastAPI(title="EVRAZ LLM fault stub", version="1.0")


def _chat_completion(content: str, model: str) -> Dict[str, Any]:
    return {
        "id": "chatcmpl-stub",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def _error(status: int, message: str, err_type: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"message": message, "type": err_type, "code": status}},
    )


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    try:
        body = await request.json()
    except json.JSONDecodeError:
        body = {}
    mode = MODE
    _stats["requests"] += 1
    _stats["by_mode"][mode] = _stats["by_mode"].get(mode, 0) + 1
    model = body.get("model", "fault-stub")
    messages: List[Dict[str, str]] = body.get("messages") or []

    if mode == "timeout":
        # Держим соединение дольше REQUEST_TIMEOUT_S клиента — клиент обязан
        # отвалиться по таймауту и сделать повтор по своей конфигурации.
        await asyncio.sleep(TIMEOUT_HOLD_S)
        return _chat_completion("поздний ответ", model)

    if mode == "rate_limit":
        return _error(429, "Rate limit reached by fault stub", "rate_limit_error")

    if mode == "error_500":
        return _error(500, "Internal error by fault stub", "server_error")

    if mode == "empty":
        return _chat_completion("", model)

    # normal: правдоподобный JSON-ответ, пригодный для структурированного парсера.
    return _chat_completion(json.dumps(_plausible_answer(messages), ensure_ascii=False), model)


def _plausible_answer(messages: List[Dict[str, str]]) -> Dict[str, Any]:
    """Минимальный ответ по схеме узла: узлы просят разный JSON, поэтому поля
    собираются по ключевым словам запроса, а эталонные числа возвращает нормальный режим."""
    text = " ".join(m.get("content", "") for m in messages).lower()
    if "query_type" in text:
        return {"query_type": "lookup", "confidence": 0.9}
    if "sql" in text:
        return {
            "sql": "SELECT 1",
            "confidence": 0.9,
            "explanation": "ответ заглушки",
        }
    return {"answer": "Заглушка: 0", "confidence": 0.9}


@app.get("/v1/models")
def models():
    return {"object": "list", "data": [{"id": "fault-stub", "object": "model"}]}


@app.post("/admin/fault")
async def set_fault(request: Request):
    global MODE, TIMEOUT_HOLD_S
    body = await request.json()
    mode = body.get("mode", "normal")
    if mode not in FAULT_MODES:
        return _error(400, f"mode должен быть одним из {list(FAULT_MODES)}", "invalid_request")
    MODE = mode
    if body.get("hold") is not None:
        TIMEOUT_HOLD_S = float(body["hold"])
    return {"mode": MODE, "timeout_hold_s": TIMEOUT_HOLD_S}


@app.get("/admin/stats")
def stats():
    return {"mode": MODE, "timeout_hold_s": TIMEOUT_HOLD_S, **_stats}


@app.post("/admin/reset")
def reset_stats():
    _stats["requests"] = 0
    _stats["by_mode"] = {}
    return {"mode": MODE}


@app.get("/health")
def health():
    return {"status": "ok", "mode": MODE}


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("STUB_PORT", "8100")), log_level="warning")


if __name__ == "__main__":
    main()
