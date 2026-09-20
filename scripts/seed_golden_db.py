"""
Загрузка tests/golden_questions.json в таблицу golden_dataset.

Полезно, когда нужно хранить эталонные вопросы в БД (для оценки через API
или отчётов админа) — сервис GoldenDatasetService уже существует, а вот
наполнителя таблицы в репозитории не было.

Использование:
    python scripts/seed_golden_db.py            # дозапись вопросов
    python scripts/seed_golden_db.py --drop     # очистить таблицу перед загрузкой
    python scripts/seed_golden_db.py --dry-run  # показать, что будет загружено

Требования:
  - PostgreSQL запущена, применены миграции (alembic upgrade head),
    таблица golden_dataset существует;
  - POSTGRES_* / POSTGRES_URL настроены в .env.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GOLDEN_PATH = ROOT / "tests" / "golden_questions.json"


def _run_async(coro):
    """asyncio.run() с совместимым event loop для Windows (psycopg)."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(coro)


def load_golden() -> List[Dict[str, Any]]:
    with open(GOLDEN_PATH, encoding="utf-8") as fh:
        return json.load(fh)


async def main(args: argparse.Namespace) -> int:
    from src.services.evaluation.golden_dataset import golden_dataset_service

    items = load_golden()
    print(f"Датасет: {len(items)} вопросов из {GOLDEN_PATH.name}")

    if args.dry_run:
        for it in items:
            print(f"  {it['id']:<5} [{it.get('domain','?'):<7}] {it['question'][:70]}")
        print("DRY-RUN: запись в БД не выполнялась.")
        return 0

    if args.drop:
        existing = await golden_dataset_service.get_all_entries(active_only=False)
        for entry in existing:
            await golden_dataset_service.delete_entry(entry.id)
        print(f"Удалено существующих записей: {len(existing)}")

    added = 0
    for it in items:
        await golden_dataset_service.add_entry(
            question=it["question"],
            query_type=it["query_type"],
            expected_sql=it.get("expected_sql_hint", ""),
            expected_result={"result_type": it.get("expected_result_type")}
            if it.get("expected_result_type") else None,
            category=it.get("domain"),
            tags=[it["id"]],
        )
        added += 1

    print(f"Загружено записей: {added}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Загрузка golden-датасета в таблицу golden_dataset")
    parser.add_argument("--drop", action="store_true", help="Очистить таблицу перед загрузкой")
    parser.add_argument("--dry-run", action="store_true", help="Показать вопросы без записи в БД")
    return parser


if __name__ == "__main__":
    sys.exit(_run_async(main(build_parser().parse_args())))