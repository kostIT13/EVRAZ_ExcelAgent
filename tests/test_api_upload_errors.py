import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import get_excel_service
from src.api.errors import InvalidFileError, register_exception_handlers
from src.api.router import router
from src.core.ratelimit import get_limiter
from src.services.excel.ingestion_service import ExcelIngestionService


class _NoDbIngestionService:
    """Загружаемый файл отклоняется до обращения к сервису-обработчику."""


@pytest.fixture()
def client():
    app = FastAPI()
    register_exception_handlers(app)
    app.state.limiter = get_limiter()
    app.include_router(router)
    app.dependency_overrides[get_excel_service] = lambda: _NoDbIngestionService()
    return TestClient(app)


def _upload(client, filename, payload):
    return client.post(
        "/files/upload",
        files={"file": (filename, payload, "application/octet-stream")},
    )


def test_foreign_file_type_rejected_with_400(client):
    res = _upload(client, "pmi_test.docx", b"not a workbook")
    assert res.status_code == 400
    assert "Invalid file type '.docx'" in res.json()["detail"]


def test_broken_workbook_is_a_client_error(tmp_path):
    broken = tmp_path / "broken.xlsx"
    broken.write_bytes(b"C" * 4096)

    with pytest.raises(InvalidFileError) as excinfo:
        asyncio.run(
            ExcelIngestionService().create_pending_file(broken, original_name="broken.xlsx")
        )

    assert excinfo.value.status_code == 400
    assert "broken.xlsx" in excinfo.value.message
    assert "\n" not in excinfo.value.message


def test_broken_workbook_upload_returns_400_not_500(client):
    # Разбор падает до записи в реестр, поэтому БД в этом пути не участвует.
    res = _upload(client, "broken.xlsx", b"C" * 4096)
    assert res.status_code == 400
    assert res.json()["detail"].startswith("Invalid Excel workbook 'broken.xlsx'")
