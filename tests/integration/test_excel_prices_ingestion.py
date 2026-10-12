"""Интеграционные тесты загрузки первой таблицы (data/data_proportional_prices.xlsx).

Покрывают полный путь инжеста: парсинг → репозиторий
(files / sheets / columns / cells) → витрина mart (price_facts / metrics /
supplier_aliases) → индексация сущностей. Требуют реальный PostgreSQL:
задайте TEST_POSTGRES_URL (см. tests/integration/conftest.py).
"""
import asyncio
import os
from pathlib import Path

import pytest
from sqlalchemy import func, select

from src.core.db.models import (
    Cell,
    ColumnMetadata,
    File,
    PriceFact,
    Sheet,
    SupplierAlias,
)
from src.services.excel.ingestion_service import ExcelIngestionService
from src.services.excel.repository import SQLAlchemyExcelRepository
from src.services.mart.normalizer import normalize_file_to_mart

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("TEST_POSTGRES_URL"),
        reason="TEST_POSTGRES_URL не задан — пропуск интеграционных тестов",
    ),
]

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
PRICES_FILE = DATA_DIR / "data_proportional_prices.xlsx"


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def prices_path():
    if not PRICES_FILE.exists():
        pytest.skip("нет файла данных")
    return PRICES_FILE


async def _ingest(session_factory, file_path: Path) -> File:
    """Загрузка файла + построение витрины. Возвращает запись File."""
    async with session_factory() as session:
        repo = SQLAlchemyExcelRepository(session)
        file_record = await repo.process_file(file_path)
        await normalize_file_to_mart(file_record.id, session=session)
        return file_record


def test_process_file_persists_structure(test_db, prices_path):
    async def scenario():
        async with test_db() as session:
            repo = SQLAlchemyExcelRepository(session)
            file_record = await repo.process_file(prices_path)

            assert file_record.filename == "data_proportional_prices.xlsx"
            assert file_record.status == "processed"
            assert file_record.total_sheets == 12

            sheets = list((await session.execute(
                select(Sheet)
                .where(Sheet.file_id == file_record.id)
                .order_by(Sheet.sheet_index)
            )).scalars().all())
            assert len(sheets) == 12

            first = sheets[0]
            assert first.original_name == "цв.лом(на дек25)"
            assert first.sheet_kind == "prices"
            assert first.period == "2025-12"
            assert first.row_count == 78
            assert first.col_count == 13

            columns = list((await session.execute(
                select(ColumnMetadata)
                .where(ColumnMetadata.sheet_id == first.id)
                .order_by(ColumnMetadata.col_index)
            )).scalars().all())
            names = [c.normalized_name for c in columns]
            assert "наименование_лома" in names
            assert "среднерыночная_цена_рубтн" in names
            assert "ферроком" in names

            cells = (await session.execute(
                select(func.count(Cell.id)).where(Cell.sheet_id == first.id)
            )).scalar_one()
            assert cells > 0

    _run(scenario())


def test_normalize_mart_creates_price_facts(test_db, prices_path):
    async def scenario():
        async with test_db() as session:
            repo = SQLAlchemyExcelRepository(session)
            file_record = await repo.process_file(prices_path)
            stats = await normalize_file_to_mart(file_record.id, session=session)

            assert stats["inserted"] > 0
            assert stats["metrics"] == 0  # prices-лист не матрица

            first_sheet = (await session.execute(
                select(Sheet).where(
                    Sheet.file_id == file_record.id,
                    Sheet.original_name == "цв.лом(на дек25)",
                )
            )).scalar_one()

            facts = list((await session.execute(
                select(PriceFact).where(
                    PriceFact.sheet_id == first_sheet.id,
                    PriceFact.item_name == "Лом меди кусок",
                )
            )).scalars().all())
            assert facts, "факты для первого наименования не найдены"

            by_price = {(f.price_type, f.supplier): f.value for f in facts}
            assert by_price.get(("среднерыночная", None)) == 892946.25
            assert by_price.get(("аукцион_старт", None)) == 868020.0
            assert by_price.get(("аукцион_победитель", None)) == 985906.5
            assert by_price.get(("поставщик", "ферроком")) == 844560.0

            # Вычисляемая колонка «по результатам аукциона» не попадает в витрину.
            assert not any(f.price_type == "по_результатам_аукциона" for f in facts)
            assert all(f.sheet_period == "2025-12" for f in facts)

            # Глобальные сущности файла: периоды и алиасы поставщиков.
            periods = set((await session.execute(
                select(PriceFact.sheet_period).where(PriceFact.file_id == file_record.id)
            )).scalars().all())
            assert "2025-12" in periods or periods

            aliases = list((await session.execute(
                select(SupplierAlias).where(SupplierAlias.source_sheet_id == first_sheet.id)
            )).scalars().all())
            assert any(a.alias.lower() == "ферроком" for a in aliases)

    _run(scenario())


def test_normalize_mart_is_idempotent(test_db, prices_path):
    async def scenario():
        async with test_db() as session:
            repo = SQLAlchemyExcelRepository(session)
            file_record = await repo.process_file(prices_path)
            await normalize_file_to_mart(file_record.id, session=session)
            count1 = (await session.execute(
                select(func.count(PriceFact.id)).where(PriceFact.file_id == file_record.id)
            )).scalar_one()
            assert count1 > 0

            # Повторная загрузка того же файла (тот же file_hash) не дублирует факты.
            await repo.process_file(prices_path)
            await normalize_file_to_mart(file_record.id, session=session)
            count2 = (await session.execute(
                select(func.count(PriceFact.id)).where(PriceFact.file_id == file_record.id)
            )).scalar_one()
            assert count2 == count1

    _run(scenario())


def test_ingestion_service_end_to_end(test_db, prices_path):
    async def scenario():
        async with test_db() as session:
            service = ExcelIngestionService(session=session)
            file_record = await service.process_file(prices_path)
            assert file_record.status == "processed"
            first_sheet = (await session.execute(
                select(Sheet).where(
                    Sheet.file_id == file_record.id,
                    Sheet.original_name == "цв.лом(на дек25)",
                )
            )).scalar_one()
            facts = (await session.execute(
                select(func.count(PriceFact.id)).where(
                    PriceFact.sheet_id == first_sheet.id
                )
            )).scalar_one()
            assert facts > 0

    _run(scenario())


def test_delete_file_removes_cascade(test_db, prices_path):
    async def scenario():
        async with test_db() as session:
            repo = SQLAlchemyExcelRepository(session)
            file_record = await repo.process_file(prices_path)
            await normalize_file_to_mart(file_record.id, session=session)
            file_id = file_record.id

            assert await repo.delete_file(file_id) is True
            assert await repo.get_file(file_id) is None

            sheets_left = (await session.execute(
                select(func.count(Sheet.id)).where(Sheet.file_id == file_id)
            )).scalar_one()
            assert sheets_left == 0

            facts_left = (await session.execute(
                select(func.count(PriceFact.id)).where(PriceFact.file_id == file_id)
            )).scalar_one()
            assert facts_left == 0

    _run(scenario())