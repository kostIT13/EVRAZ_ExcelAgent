"""Временный скрипт: инжест Faked-файла и проверка mart.metrics."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select, text

from src.core.db.database import async_session_maker
from src.core.db.models import File, Metric, Sheet
from src.services.excel.ingestion_service import ExcelIngestionService

OUT = "scripts/faked_ingest_dump.txt"
PATH = "data/Faked_List_proportional (2).xlsx"


async def main() -> None:
    lines = []
    service = ExcelIngestionService()
    file_record = await service.process_file(Path(PATH))
    lines.append(f"file_id={file_record.id} filename={file_record.filename}")

    async with async_session_maker() as s:
        sheets = (await s.execute(
            select(Sheet).where(Sheet.file_id == file_record.id)
        )).scalars().all()
        for sh in sheets:
            lines.append(f"  sheet: {sh.original_name} | kind={sh.sheet_kind} | period={sh.period}")

        total_metrics = (await s.execute(
            select(func.count()).select_from(Metric).where(Metric.file_id == file_record.id)
        )).scalar()
        lines.append(f"metrics total: {total_metrics}")

        # Топ метрик по количеству
        top = (await s.execute(
            select(Metric.metric, func.count().label("cnt"))
            .where(Metric.file_id == file_record.id)
            .group_by(Metric.metric)
            .order_by(func.count().desc())
            .limit(25)
        )).all()
        lines.append("top metrics:")
        for metric, cnt in top:
            lines.append(f"  {metric}: {cnt}")

        # Проверка ключевых значений
        checks = [
            ("расход из силосов Краснокаменская КЖ (2 блок)",
             "SELECT SUM(value) FROM mart.metrics WHERE dimension ILIKE '%краснокаменская%' AND metric ILIKE '%силос%'"),
            ("утв план Распадская ГЖ (2 блок)",
             "SELECT value FROM mart.metrics WHERE dimension ILIKE '%распадская%' AND metric ILIKE '%утв_план%' AND sheet_id = (SELECT id FROM sheets WHERE original_name LIKE '%2 блок%' LIMIT 1)"),
            ("факт Распадская ГЖ (2 блок)",
             "SELECT value FROM mart.metrics WHERE dimension ILIKE '%распадская%' AND metric ILIKE '%факт%' AND sheet_id = (SELECT id FROM sheets WHERE original_name LIKE '%2 блок%' LIMIT 1)"),
            ("2 блок факт стоимость (отклонения)",
             "SELECT value FROM mart.metrics WHERE dimension = 'сводная_строка' AND metric = '2_блок_факт'"),
            ("3 блок факт стоимость (отклонения)",
             "SELECT value FROM mart.metrics WHERE dimension = 'сводная_строка' AND metric = '3_блок_факт'"),
            ("отклонение факт (отклонения)",
             "SELECT value FROM mart.metrics WHERE dimension = 'сводная_строка' AND metric = 'отклонение_факт'"),
        ]
        lines.append("")
        lines.append("checks:")
        for name, sql in checks:
            try:
                result = (await s.execute(text(sql))).all()
                lines.append(f"  {name}: {[tuple(r) for r in result]}")
            except Exception as exc:
                lines.append(f"  {name}: ERROR {exc}")

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print("written", OUT)


if __name__ == "__main__":
    asyncio.run(main())