import asyncio

from sqlalchemy import text

from src.core.db.database import async_session_maker


async def main() -> None:
    async with async_session_maker() as s:
        sql = """
SELECT MIN(fp.value) AS минимальная_цена_победителя
FROM mart.price_facts fp
WHERE fp.item_name ILIKE '%алюмин%'
  AND fp.price_type = 'аукцион_победитель'
  AND fp.sheet_period >= '2025-01'
  AND fp.sheet_period <= '2025-12'
"""
        rows = (await s.execute(text(sql))).fetchall()
        print("MIN result:", rows)

        cnt = (await s.execute(text(
            "SELECT count(*) FROM mart.price_facts "
            "WHERE item_name ILIKE '%алюмин%' AND price_type='аукцион_победитель'"
        ))).scalar()
        print("count аукцион_победитель по алюминию:", cnt)


if __name__ == "__main__":
    asyncio.run(main())