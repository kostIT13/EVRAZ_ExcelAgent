from __future__ import annotations
import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.db.database import async_session_maker
from src.core.db.models import QueryCache
from src.core.logging_settings import logger


def _normalize_question(question: str) -> str:
    q = question.lower().strip()
    q = re.sub(r'[^\w\sа-яё]', ' ', q)
    q = re.sub(r'\s+', ' ', q)
    q = q.strip()
    return q


def _hash_question(question: str) -> str:
    normalized = _normalize_question(question)
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


class QueryCacheService:

    async def lookup(
        self,
        question: str,
        session: Optional[AsyncSession] = None,
    ) -> Optional[Dict[str, Any]]:
        question_hash = _hash_question(question)

        async with session or async_session_maker() as s:
            result = await s.execute(
                select(QueryCache).where(QueryCache.question_hash == question_hash)
            )
            record = result.scalar_one_or_none()

            if record is not None:
                # Обновляем счётчик и время последнего использования
                record.hit_count = (record.hit_count or 0) + 1
                await s.commit()

                logger.info(
                    "Query cache HIT: '{}' (hit_count={})",
                    question[:60],
                    record.hit_count,
                )
                return {
                    "sql_query": record.sql_query,
                    "result": record.result,
                    "query_type": record.query_type,
                    "entities": record.entities,
                }

        logger.debug("Query cache MISS: '{}'", question[:60])
        return None

    async def store(
        self,
        question: str,
        sql_query: str,
        result: Optional[List[Dict[str, Any]]] = None,
        query_type: Optional[str] = None,
        entities: Optional[List[str]] = None,
        session: Optional[AsyncSession] = None,
    ) -> None:
        question_hash = _hash_question(question)
        normalized = _normalize_question(question)

        async with session or async_session_maker() as s:
            # Проверяем, не существует ли уже
            existing = await s.execute(
                select(QueryCache).where(QueryCache.question_hash == question_hash)
            )
            existing_record = existing.scalar_one_or_none()
            if existing_record is not None:
                # Обновляем существующую запись
                existing_record.sql_query = sql_query
                existing_record.result = result
                existing_record.query_type = query_type or "unknown"
                existing_record.entities = entities
                existing_record.hit_count = (existing_record.hit_count or 0) + 1
                await s.commit()
                logger.debug("Query cache UPDATED: '{}'", question[:60])
                return

            record = QueryCache(
                question_hash=question_hash,
                question=question,
                normalized_question=normalized,
                sql_query=sql_query,
                result=result,
                query_type=query_type or "unknown",
                entities=entities,
            )
            s.add(record)
            await s.commit()
            logger.debug("Query cache STORED: '{}'", question[:60])

    async def find_similar(
        self,
        question: str,
        threshold: float = 0.8,
        session: Optional[AsyncSession] = None,
    ) -> List[Dict[str, Any]]:
        normalized = _normalize_question(question)
        words = set(normalized.split())

        async with session or async_session_maker() as s:
            result = await s.execute(
                select(QueryCache).order_by(QueryCache.hit_count.desc()).limit(100)
            )
            records = result.scalars().all()

        similar = []
        for record in records:
            record_words = set(record.normalized_question.split())
            if not words or not record_words:
                continue
            intersection = words & record_words
            union = words | record_words
            jaccard = len(intersection) / len(union) if union else 0

            if jaccard >= threshold:
                similar.append({
                    "question": record.question,
                    "sql_query": record.sql_query,
                    "query_type": record.query_type,
                    "entities": record.entities,
                    "similarity": jaccard,
                    "hit_count": record.hit_count,
                })

        similar.sort(key=lambda x: x["similarity"], reverse=True)
        return similar[:5]

    async def get_stats(
        self,
        session: Optional[AsyncSession] = None,
    ) -> Dict[str, Any]:
        async with session or async_session_maker() as s:
            total = await s.execute(select(func.count(QueryCache.id)))
            total_count = total.scalar() or 0

            top = await s.execute(
                select(QueryCache)
                .order_by(QueryCache.hit_count.desc())
                .limit(10)
            )
            top_queries = [
                {
                    "question": r.question[:100],
                    "hit_count": r.hit_count,
                    "query_type": r.query_type,
                }
                for r in top.scalars().all()
            ]

        return {
            "total_cached": total_count,
            "top_queries": top_queries,
        }


query_cache_service: QueryCacheService = QueryCacheService()