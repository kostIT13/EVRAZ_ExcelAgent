import pytest
from prometheus_client import Histogram

from src.core.config import settings
from src.core.metrics import _histogram_quantile, _quantile_from_buckets
from src.core.ratelimit import ask_limit, cache_clear_limit, upload_limit
from src.services.agent.checkpointer import build_psycopg_dsn


# --- ratelimit ---


def test_ratelimit_limits_from_settings(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ASK", "30/minute")
    monkeypatch.setattr(settings, "RATE_LIMIT_UPLOAD", "10/minute")
    monkeypatch.setattr(settings, "RATE_LIMIT_CACHE_CLEAR", "5/minute")
    assert ask_limit() == "30/minute"
    assert upload_limit() == "10/minute"
    assert cache_clear_limit() == "5/minute"


def test_ratelimit_fallback_when_empty(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ASK", "")
    monkeypatch.setattr(settings, "RATE_LIMIT_UPLOAD", "")
    monkeypatch.setattr(settings, "RATE_LIMIT_CACHE_CLEAR", "")
    assert ask_limit() == "30/minute"
    assert upload_limit() == "10/minute"
    assert cache_clear_limit() == "10/minute"


# --- checkpointer ---


def test_build_psycopg_dsn_format(monkeypatch):
    monkeypatch.setattr(settings, "POSTGRES_USER", "evraz")
    monkeypatch.setattr(settings, "POSTGRES_PASSWORD", "secret")
    monkeypatch.setattr(settings, "POSTGRES_HOST", "localhost")
    monkeypatch.setattr(settings, "POSTGRES_PORT", 5432)
    monkeypatch.setattr(settings, "POSTGRES_DB", "evraz_db")
    assert build_psycopg_dsn() == (
        "postgresql://evraz:secret@localhost:5432/evraz_db"
    )


# --- metrics helpers ---


def test_quantile_from_buckets():
    buckets = [(0.5, 1), (1, 2), (2, 3), (5, 4), (10, 5), (30, 6), (60, 7), (120, 8), (float("inf"), 8)]
    assert _quantile_from_buckets(buckets, 8, 0.5) == 5.0
    # p95: target = 0.95 * 8 = 7.6 -> интерполяция между 60 (7) и 120 (8)
    assert _quantile_from_buckets(buckets, 8, 0.95) == pytest.approx(96.0)


def test_histogram_quantile_fresh_histogram():
    h = Histogram("test_hist_quantile", "test", buckets=(1, 2, 5))
    h.observe(0.5)
    h.observe(1.5)
    h.observe(4.0)
    assert _histogram_quantile(h, 0.5) == 1.5


def test_histogram_quantile_empty_returns_zero():
    h = Histogram("test_hist_empty", "test", buckets=(1, 2, 5))
    assert _histogram_quantile(h, 0.95) == 0.0