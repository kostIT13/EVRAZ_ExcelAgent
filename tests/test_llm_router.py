import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.llm_router import MODEL_DEFAULT, router
from src.core.config import settings
from src.services.llm.llm_client import LLMClient


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(settings, "LLM_MODEL_PRIMARY", "model-a")
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _probe_ok(monkeypatch, ms=42):
    async def probe(self, model):
        return ms

    monkeypatch.setattr(LLMClient, "probe", probe)


def test_list_models_returns_proxy_models(client, monkeypatch):
    async def list_models(self):
        return ["model-b", "model-a"]

    monkeypatch.setattr(LLMClient, "list_models", list_models)
    body = client.get("/llm/models").json()
    assert body["models"] == ["model-b", "model-a"]
    assert body["current"] == "model-a"
    assert body["default"] == MODEL_DEFAULT
    assert body["listed"] is True


def test_list_models_reports_proxy_failure(client, monkeypatch):
    async def list_models(self):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(LLMClient, "list_models", list_models)
    body = client.get("/llm/models").json()
    assert body["listed"] is False
    assert "connection refused" in body["error"]
    assert body["current"] == "model-a"


def test_switch_without_verify_applies_immediately(client):
    res = client.put("/llm/model", json={"model": "  model-b  ", "verify": False})
    assert res.status_code == 200
    body = res.json()
    assert (body["previous"], body["current"], body["changed"], body["verified"]) == (
        "model-a",
        "model-b",
        True,
        False,
    )
    assert settings.LLM_MODEL_PRIMARY == "model-b"
    assert client.get("/llm/config").json()["model"] == "model-b"


def test_switch_verified_uses_probe_duration(client, monkeypatch):
    _probe_ok(monkeypatch, ms=137)
    body = client.put("/llm/model", json={"model": "model-b", "verify": True}).json()
    assert body["verified"] is True
    assert body["probe_ms"] == 137
    assert settings.LLM_MODEL_PRIMARY == "model-b"


def test_switch_keeps_previous_model_when_candidate_silent(client, monkeypatch):
    async def probe(self, model):
        raise RuntimeError("404 model not found")

    monkeypatch.setattr(LLMClient, "probe", probe)
    res = client.put("/llm/model", json={"model": "ghost-model", "verify": True})
    assert res.status_code == 400
    assert "ghost-model" in res.json()["detail"]
    assert settings.LLM_MODEL_PRIMARY == "model-a"


def test_switch_rejects_blank_model(client):
    assert client.put("/llm/model", json={"model": "   ", "verify": False}).status_code == 422


def test_reset_returns_to_dotenv_value(client):
    client.put("/llm/model", json={"model": "model-b", "verify": False})
    body = client.post("/llm/model/reset").json()
    assert body["previous"] == "model-b"
    assert body["current"] == MODEL_DEFAULT
    assert settings.LLM_MODEL_PRIMARY == MODEL_DEFAULT


def test_switch_requires_api_key_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", "secret-key")
    monkeypatch.setattr(settings, "LLM_MODEL_PRIMARY", "model-a")
    app = FastAPI()
    app.include_router(router)
    guarded = TestClient(app)
    assert guarded.put("/llm/model", json={"model": "model-b"}).status_code == 401
    assert settings.LLM_MODEL_PRIMARY == "model-a"
