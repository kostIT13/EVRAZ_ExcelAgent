"""Проверка entity-resolution для запроса по алюминию."""
import asyncio

from src.services.entity_resolution.entity_resolver import entity_resolver


async def main() -> None:
    for q in ("лом алюминия", "Лом алюминия"):
        print(f"=== query: {q} ===")
        cands = await entity_resolver.resolve_candidates(q, top_n=10)
        if not cands:
            print("  (no candidates)")
        for c in cands:
            print(f"  {c.entity_type} | {c.entity_value} | {round(c.score,3)}")


if __name__ == "__main__":
    asyncio.run(main())