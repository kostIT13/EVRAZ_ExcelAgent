from __future__ import annotations

from datetime import datetime
from typing import List, Optional, TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.db.base import Base

if TYPE_CHECKING:
    from src.core.db.vector_models import ChunkEmbedding, ColumnEmbedding, QueryEmbeddingCache, SheetEmbedding


class File(Base):
    __tablename__ = "files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    total_sheets: Mapped[int] = mapped_column(Integer, default=0)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    total_cells: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="uploaded")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    sheets: Mapped[List["Sheet"]] = relationship("Sheet", back_populates="file", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_files_status", "status"),
        Index("ix_files_uploaded_at", "uploaded_at"),
    )


class Sheet(Base):
    __tablename__ = "sheets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    file_id: Mapped[int] = mapped_column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)
    sheet_index: Mapped[int] = mapped_column(Integer, nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    col_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    file: Mapped["File"] = relationship("File", back_populates="sheets")
    columns: Mapped[List["ColumnMetadata"]] = relationship("ColumnMetadata", back_populates="sheet", cascade="all, delete-orphan")
    cells: Mapped[List["Cell"]] = relationship("Cell", back_populates="sheet", cascade="all, delete-orphan")
    embedding: Mapped[Optional["SheetEmbedding"]] = relationship(
        "SheetEmbedding",
        back_populates="sheet",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="raise",
    )
    chunk_embeddings: Mapped[List["ChunkEmbedding"]] = relationship(
        "ChunkEmbedding",
        back_populates="sheet",
        cascade="all, delete-orphan",
        lazy="raise",
    )

    __table_args__ = (
        Index("ix_sheets_file_id", "file_id"),
        Index("ix_sheets_normalized_name", "normalized_name"),
        Index("ix_sheets_original_name", "original_name"),
    )


class ColumnMetadata(Base):
    __tablename__ = "column_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    sheet_id: Mapped[int] = mapped_column(Integer, ForeignKey("sheets.id", ondelete="CASCADE"), nullable=False, index=True)
    col_index: Mapped[int] = mapped_column(Integer, nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    data_type: Mapped[str] = mapped_column(String(50), nullable=False, default="text")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sample_values: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # 👇 Эти строки должны быть ВНУТРИ класса
    sheet: Mapped["Sheet"] = relationship("Sheet", back_populates="columns")
    embedding: Mapped[Optional["ColumnEmbedding"]] = relationship(
        "ColumnEmbedding", 
        back_populates="column", 
        uselist=False, 
        cascade="all, delete-orphan", 
        lazy="raise"
    )

    __table_args__ = (
        Index("ix_column_metadata_sheet_id", "sheet_id"),
        Index("ix_column_metadata_normalized_name", "normalized_name"),
        Index("ix_column_metadata_data_type", "data_type"),
    )


class Cell(Base):
    __tablename__ = "cells"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    sheet_id: Mapped[int] = mapped_column(Integer, ForeignKey("sheets.id", ondelete="CASCADE"), nullable=False, index=True)
    row_num: Mapped[int] = mapped_column(Integer, nullable=False)
    col_index: Mapped[int] = mapped_column(Integer, nullable=False)
    value_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    value_number: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    value_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_error: Mapped[bool] = mapped_column(Integer, default=False)
    error_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    original_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    sheet: Mapped["Sheet"] = relationship("Sheet", back_populates="cells")

    __table_args__ = (
        Index("ix_cells_sheet_id", "sheet_id"),
        Index("ix_cells_value_number", "value_number"),
    )


class QueryLog(Base):
    __tablename__ = "query_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    plan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sql_query: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    trace: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default="success")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_query_logs_request_id", "request_id"),
        Index("ix_query_logs_created_at", "created_at"),
        Index("ix_query_logs_user_id", "user_id"),
        Index("ix_query_logs_status", "status"),
    )