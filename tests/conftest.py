# Общие фикстуры и настройка pytest.

# Важно: conftest.py импортируется ДО всех тестовых модулей, поэтому здесь
# задаются переменные окружения по умолчанию. Без них `src.core.config.Settings()`
# (обязательные поля LLM_*, POSTGRES_*) упадёт на этапе импорта в окружениях,
# где нет файла `.env` (GitHub Actions, чистый CI).
import asyncio
import os
import sys

for _key, _default in {
    "LLM_BASE_URL": "http://localhost:11434/v1",
    "LLM_API_KEY": "test-api-key",
    "LLM_MODEL_PRIMARY": "test-model",
    "POSTGRES_URL": "postgresql+asyncpg://test:test@localhost:5432/test",
    "POSTGRES_DB": "test",
    "POSTGRES_HOST": "localhost",
    "POSTGRES_PASSWORD": "test",
    "POSTGRES_USER": "test",
    "POSTGRES_PORT": "5432",
}.items():
    os.environ.setdefault(_key, _default)

# Windows: asyncpg/psycopg несовместимы с ProactorEventLoop
# (asyncio.run по умолчанию) — переключаемся на selector-политику.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


import pytest  # noqa: E402


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "golden: интеграционные тесты golden-dataset, требующие LLM-модель и данные.",
    )
    config.addinivalue_line(
        "markers",
        "integration: интеграционные тесты с реальной PostgreSQL "
        "(требуют переменную окружения TEST_POSTGRES_URL).",
    )


def pytest_addoption(parser):
    parser.addoption(
        "--golden",
        action="store_true",
        default=False,
        help="Включить golden-интеграционные тесты (требуют LLM и загруженные данные).",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--golden"):
        return
    # Если пользователь явно выбрал golden-тесты через `pytest -m golden`,
    # не добавляем skip — прогон должен выполниться.
    markexpr = getattr(config.option, "markexpr", "") or ""
    if "golden" in [m.strip().lstrip("!") for m in markexpr.split(" and ")]:
        return
    skip_golden = pytest.mark.skip(reason="Включите --golden для LLM-интеграции")
    for item in items:
        if "golden" in item.keywords:
            item.add_marker(skip_golden)