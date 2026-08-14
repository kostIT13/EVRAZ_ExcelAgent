"""Проверка нормализации: запускает normalize_file_to_mart для последнего файла."""
import asyncio

from sqlalchemy import text

from src.core.db.database import async_session_maker
from src.services.mart.normalizer import normalize_file_to_mart


async def main() -> None:
    async with async_session_maker() as s:
        r = await s.execute(text("SELECT id, filename FROM files ORDER BY id DESC LIMIT 1"))
        row = r.fetchone()
        if row is None:
            print("No files found")
            return
        print("Last file:", row.id, row.filename)
        stats = await normalize_file_to_mart(row.id, session=s)
        print("normalize stats:", stats)

        for table in ("mart.price_facts", "mart.metrics", "mart.supplier_aliases", "mart.sheet_templates"):
            cnt = (await s.execute(text(f"SELECT count(*) FROM {table}"))).scalar()
            print(f"{table}: {cnt}")


if __name__ == "__main__":
    asyncio.run(main())