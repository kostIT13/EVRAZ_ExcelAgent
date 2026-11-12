"""Н-2 (ПМИ): повторы клиента LLM при таймауте, HTTP 429 и пустом ответе.

Запросы идут через настоящий openai-клиент на настоящий сервер заглушки
benchmark/llm_fault_stub.py (uvicorn в потоке), поэтому проверяется реальная ветка
RETRYABLE в LLMClient._try_with_retries, а не её имитация.
"""
import asyncio
import json
import socket
import threading
import time
import urllib.request

import pytest
import uvicorn
from openai import (
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)

from src.core.config import settings
from src.services.llm.llm_client import LLMClient

import benchmark.llm_fault_stub as stub


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _Stub:
    def __init__(self):
        self.port = _free_port()
        self.server = uvicorn.Server(
            uvicorn.Config(stub.app, host="127.0.0.1", port=self.port, log_level="error")
        )
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                if self._get("/health")["status"] == "ok":
                    return
            except Exception:
                time.sleep(0.1)
        raise RuntimeError("заглушка не поднялась")

    def _get(self, path: str) -> dict:
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=5) as r:
            return json.loads(r.read())

    def set_mode(self, mode: str, **extra):
        self._post("/admin/fault", {"mode": mode, **extra})
        self._post("/admin/reset", {})  # счётчик — на время теста

    def _post(self, path: str, payload: dict):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            r.read()

    def requests(self) -> int:
        return int(self._get("/admin/stats")["requests"])

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def stop(self):
        self.server.should_exit = True
        self.thread.join(timeout=15)


@pytest.fixture()
def srv():
    runner = _Stub()
    try:
        yield runner
    finally:
        runner.set_mode("normal")
        runner.stop()


def _client(base_url: str, timeout_s: float) -> AsyncOpenAI:
    # max_retries=0 — внутренние повторы openai-клиента выключены, чтобы считать
    # повторы нашего цикла: их число задаётся конфигурацией MAX_RETRIES.
    return AsyncOpenAI(api_key="test", base_url=base_url, timeout=timeout_s, max_retries=0)


def _attempt(client, monkeypatch, max_retries: int):
    monkeypatch.setattr(settings, "MAX_RETRIES", max_retries)
    return asyncio.run(
        LLMClient._try_with_retries(
            client=client,
            model="fault-stub",
            messages=[{"role": "user", "content": "цена?"}],
        )
    )


def test_rate_limit_retries_follow_configuration(srv, monkeypatch):
    srv.set_mode("rate_limit")
    result, error = _attempt(_client(srv.base_url, 5.0), monkeypatch, max_retries=2)

    assert result == ""
    assert isinstance(error, RateLimitError)
    assert error.status_code == 429
    assert srv.requests() == 2


def test_timeout_retries_and_raises(srv, monkeypatch):
    srv.set_mode("timeout", hold=3)
    # Клиентский таймаут заведомо короче, чем заглушка держит соединение.
    result, error = _attempt(_client(srv.base_url, 0.5), monkeypatch, max_retries=2)

    assert result == ""
    assert isinstance(error, APITimeoutError)
    assert srv.requests() == 2


def test_empty_answer_returns_empty_without_retry(srv, monkeypatch):
    srv.set_mode("empty")
    result, error = _attempt(_client(srv.base_url, 5.0), monkeypatch, max_retries=3)

    assert error is None
    assert result == ""  # пустой ответ — не сетевая ошибка: повтор не делается
    assert srv.requests() == 1


def test_server_error_is_not_retryable(srv, monkeypatch):
    srv.set_mode("error_500")
    with pytest.raises(InternalServerError) as exc:
        _attempt(_client(srv.base_url, 5.0), monkeypatch, max_retries=3)

    assert isinstance(exc.value, APIStatusError)
    assert exc.value.status_code == 500
    assert srv.requests() == 1


def test_normal_mode_returns_answer(srv, monkeypatch):
    srv.set_mode("normal")
    result, error = _attempt(_client(srv.base_url, 5.0), monkeypatch, max_retries=3)

    assert error is None
    assert json.loads(result)["confidence"] == 0.9
    assert srv.requests() == 1
