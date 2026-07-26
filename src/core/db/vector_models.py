from __future__ import annotations

from datetime import datetime
from typing import List, Optional, TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.db.base import Base

if TYPE_CHECKING:
    from src.core.db.models import ColumnMetadata, Sheet


class SheetEmbedding(Base):
    """Эмбеддинг для целого листа (общее текстовое представление)."""

    __tablename__ = "sheet_embeddings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    sheet_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sheets.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Vector] = mapped_column(Vector(1024), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    sheet = relationship("Sheet", back_populates="embedding")


class ChunkEmbedding(Base):
    """Эмбеддинг для отдельного чанка (строки данных) внутри листа.

    Позволяет dense-поиску находить конкретные строки с продуктами,
    а не только целые листы.
    """

    __tablename__ = "chunk_embeddings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    sheet_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sheets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Vector] = mapped_column(Vector(1024), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    sheet = relationship("Sheet", back_populates="chunk_embeddings")

    __table_args__ = (
        Index("ix_chunk_embeddings_sheet_id", "sheet_id"),
    )


class ColumnEmbedding(Base):
    __tablename__ = "column_embeddings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    column_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("column_metadata.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Vector] = mapped_column(Vector(1024), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    column = relationship("ColumnMetadata", back_populates="embedding")


class QueryEmbeddingCache(Base):
    __tablename__ = "query_embedding_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    query_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Vector] = mapped_column(Vector(1024), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_query_embedding_cache_hash", "query_hash"),
    )