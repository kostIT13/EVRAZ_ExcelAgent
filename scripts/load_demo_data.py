"""
Загрузка демо-данных (data/*.xlsx) в БД для прогона golden-датасета.

Использование:
    python scripts/load_demo_data.py                # все файлы из data/
    python scripts/load_demo_data.py --file data/data_proportional_prices.xlsx
    python scripts/load_demo_data.py --check-mart   # дополнительно проверить витрину

Требования:
  - PostgreSQL запущена и схема применена (alembic upgrade head);
  - POSTGRES_* / POSTGRES_URL настроены в .env.

Скрипт использует тот же путь обработки, что и прод-очередь
(ExcelIngestionService.process_file), поэтому данные попадают в RAW-таблицы
и витрину mart ровно так же, как при загрузке через веб-интерфейс.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA_DIR = ROOT / "data"


def _run_async(coro):
    """asyncio.run() с совместимым event loop для Windows (psycopg)."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(coro)


async def _mart_counts() -> dict:
    from sqlalchemy import text
    from src.core.db.database import async_session_maker

    counts: dict = {}
    async with async_session_maker() as session:
        for table in ("price_facts", "metrics"):
            try:
                result = await session.execute(text(f"SELECT COUNT(*) FROM mart.{table}"))
                counts[table] = result.scalar_one()
            except Exception as exc:  # noqa: BLE001
                counts[table] = f"error: {exc}"
    return counts


async def main(args: argparse.Namespace) -> int:
    from src.services.excel.ingestion_service import ExcelIngestionService

    if args.file:
        files = [Path(args.file)]
    else:
        files = sorted(
            p for p in DATA_DIR.glob("*.xlsx") if p.is_file()
        )
    if not files:
        print(f"Не найдено .xlsx файлов в {DATA_DIR}")
        return 1

    service = ExcelIngestionService()
    total = len(files)
    for i, path in enumerate(files, 1):
        print(f"[{i}/{total}] Обработка {path.name} ...")
        try:
            file_record = await service.process_file(path)
            print(f"  -> файл #{file_record.id}, статус={file_record.status}, "
                  f"листов={file_record.total_sheets}")
        except Exception as exc:  # noqa: BLE001
            print(f"  -> ОШИБКА: {exc}")
            return 1

    if args.check_mart:
        counts = await _mart_counts()
        print("Витрина данных:")
        for table, count in counts.items():
            print(f"  mart.{table}: {count}")
        pf = counts.get("price_facts")
        if isinstance(pf, int) and pf > 0:
            return 0
        print("ВНИМАНИЕ: витрина mart.price_facts пуста или недоступна.")
        return 1

    print("Готово. Данные загружены.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Загрузка демо-данных для golden-прогона")
    parser.add_argument("--file", type=str, default="", help="Путь к конкретному .xlsx файлу")
    parser.add_argument(
        "--check-mart",
        action="store_true",
        help="Проверить, что витрина mart.price_facts не пуста",
    )
    return parser


if __name__ == "__main__":
    sys.exit(_run_async(main(build_parser().parse_args())))