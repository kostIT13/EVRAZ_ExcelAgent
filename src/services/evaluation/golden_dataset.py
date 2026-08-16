from __future__ import annotations
import json
import re
from typing import Any, Dict, List, Optional
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.db.database import async_session_maker
from src.core.db.models import GoldenDataset
from src.core.logging_settings import logger


class GoldenDatasetService:
    async def add_entry(
        self,
        question: str,
        query_type: str,
        expected_sql: str,
        entities: Optional[List[str]] = None,
        expected_result: Optional[List[Dict[str, Any]]] = None,
        expected_answer: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        session: Optional[AsyncSession] = None,
    ) -> GoldenDataset:
        async with session or async_session_maker() as s:
            entry = GoldenDataset(
                question=question,
                query_type=query_type,
                entities=entities,
                expected_sql=expected_sql,
                expected_result=expected_result,
                expected_answer=expected_answer,
                category=category,
                tags=tags,
            )
            s.add(entry)
            await s.commit()
            await s.refresh(entry)
            logger.info(
                "Golden dataset: added entry #{} ('{}')",
                entry.id,
                question[:60],
            )
            return entry

    async def get_entry(
        self,
        entry_id: int,
        session: Optional[AsyncSession] = None,
    ) -> Optional[GoldenDataset]:
        async with session or async_session_maker() as s:
            result = await s.execute(
                select(GoldenDataset).where(GoldenDataset.id == entry_id)
            )
            return result.scalar_one_or_none()

    async def get_all_entries(
        self,
        category: Optional[str] = None,
        active_only: bool = True,
        session: Optional[AsyncSession] = None,
    ) -> List[GoldenDataset]:
        async with session or async_session_maker() as s:
            query = select(GoldenDataset)
            if active_only:
                query = query.where(GoldenDataset.is_active == True)
            if category:
                query = query.where(GoldenDataset.category == category)
            query = query.order_by(GoldenDataset.id)
            result = await s.execute(query)
            return list(result.scalars().all())

    async def delete_entry(
        self,
        entry_id: int,
        session: Optional[AsyncSession] = None,
    ) -> bool:
        async with session or async_session_maker() as s:
            result = await s.execute(
                select(GoldenDataset).where(GoldenDataset.id == entry_id)
            )
            entry = result.scalar_one_or_none()
            if not entry:
                return False
            await s.delete(entry)
            await s.commit()
            logger.info("Golden dataset: deleted entry #{}", entry_id)
            return True


    async def evaluate(
        self,
        entry_id: int,
        actual_sql: str,
        actual_result: Optional[List[Dict[str, Any]]] = None,
        session: Optional[AsyncSession] = None,
    ) -> Dict[str, Any]:
        entry = await self.get_entry(entry_id, session)
        if not entry:
            return {"error": f"Entry #{entry_id} not found"}

        # Сравниваем SQL (нормализованный)
        sql_match = self._normalize_sql(actual_sql) == self._normalize_sql(entry.expected_sql)

        # Сравниваем результат (если есть)
        result_match = None
        if actual_result is not None and entry.expected_result is not None:
            result_match = self._compare_results(actual_result, entry.expected_result)

        return {
            "entry_id": entry_id,
            "question": entry.question,
            "query_type": entry.query_type,
            "category": entry.category,
            "sql_match": sql_match,
            "result_match": result_match,
            "expected_sql": entry.expected_sql,
            "actual_sql": actual_sql,
            "expected_result": entry.expected_result,
            "actual_result": actual_result,
        }

    async def run_evaluation(
        self,
        category: Optional[str] = None,
        session: Optional[AsyncSession] = None,
    ) -> Dict[str, Any]:
        entries = await self.get_all_entries(category=category, session=session)

        if not entries:
            return {"total": 0, "message": "No entries found"}

        results = []
        for entry in entries:
            results.append({
                "id": entry.id,
                "question": entry.question[:80],
                "query_type": entry.query_type,
                "category": entry.category,
                "expected_sql": entry.expected_sql,
            })

        return {
            "total": len(results),
            "entries": results,
        }

    @staticmethod
    def _normalize_sql(sql: str) -> str:
        if not sql:
            return ""
        sql = sql.strip().lower()
        sql = re.sub(r'\s+', ' ', sql)
        sql = sql.rstrip(';')
        return sql

    @staticmethod
    def _compare_results(
        actual: List[Dict[str, Any]],
        expected: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not actual and not expected:
            return {"match": True, "detail": "both empty"}

        if len(actual) != len(expected):
            return {
                "match": False,
                "detail": f"row count mismatch: actual={len(actual)}, expected={len(expected)}",
            }

        match = True
        for i, (a, e) in enumerate(zip(actual, expected)):
            if a != e:
                match = False
                break

        return {
            "match": match,
            "actual_rows": len(actual),
            "expected_rows": len(expected),
        }


golden_dataset_service: GoldenDatasetService = GoldenDatasetService()