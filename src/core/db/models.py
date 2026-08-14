from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.db.base import Base


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
    period: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    # Типизация листа: prices (цены лома) / matrix (план-факт-отклонение) / generic.
    sheet_kind: Mapped[str] = mapped_column(String(30), nullable=False, default="generic", index=True)
    # Признак, что тип определён автоматическим детектором (а не вручную).
    sheet_kind_auto: Mapped[bool] = mapped_column(Integer, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    file: Mapped["File"] = relationship("File", back_populates="sheets")
    columns: Mapped[List["ColumnMetadata"]] = relationship("ColumnMetadata", back_populates="sheet", cascade="all, delete-orphan")
    cells: Mapped[List["Cell"]] = relationship("Cell", back_populates="sheet", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_sheets_file_id", "file_id"),
        Index("ix_sheets_normalized_name", "normalized_name"),
        Index("ix_sheets_original_name", "original_name"),
        Index("ix_sheets_period", "period"),
        Index("ix_sheets_sheet_kind", "sheet_kind"),
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
    # Семантическая роль колонки: item / price / supplier / percent / metric_type / other.
    role: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)

    sheet: Mapped["Sheet"] = relationship("Sheet", back_populates="columns")

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


class EntityDictionary(Base):
    __tablename__ = "entity_dictionary"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    aliases: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embedding: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, onupdate=func.now())

    __table_args__ = (
        Index("ix_entity_dictionary_canonical_name", "canonical_name"),
        Index("ix_entity_dictionary_category", "category"),
    )


class ExcelComment(Base):
    __tablename__ = "excel_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    sheet_id: Mapped[int] = mapped_column(Integer, ForeignKey("sheets.id", ondelete="CASCADE"), nullable=False, index=True)
    cell_ref: Mapped[str] = mapped_column(String(20), nullable=False)
    row_num: Mapped[int] = mapped_column(Integer, nullable=False)
    col_index: Mapped[int] = mapped_column(Integer, nullable=False)
    author: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    text: Mapped[Text] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    sheet: Mapped["Sheet"] = relationship("Sheet")

    __table_args__ = (
        Index("ix_excel_comments_sheet_id", "sheet_id"),
        Index("ix_excel_comments_cell_ref", "cell_ref"),
    )


class QueryCache(Base):
    __tablename__ = "query_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    question_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_question: Mapped[str] = mapped_column(Text, nullable=False)
    sql_query: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    query_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entities: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    hit_count: Mapped[int] = mapped_column(Integer, default=1)
    last_used: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_query_cache_question_hash", "question_hash"),
        Index("ix_query_cache_query_type", "query_type"),
    )


class GoldenDataset(Base):
    __tablename__ = "golden_dataset"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    query_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entities: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    expected_sql: Mapped[str] = mapped_column(Text, nullable=False)
    expected_result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    expected_answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Integer, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_golden_dataset_category", "category"),
        Index("ix_golden_dataset_is_active", "is_active"),
    )


class QueryLog(Base):
    __tablename__ = "query_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True, server_default=text("gen_random_uuid()::text"))
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


class PriceFact(Base):
    """mart.price_facts — нормализованная long-таблица фактов цен.

    На ней строятся все SQL-запросы агента (вместо EAV cells). Появляется из
    raw.cells на этапе нормализации (итеративно, идемпотентно).
    """

    __tablename__ = "price_facts"
    __table_args__ = {"schema": "mart"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    file_id: Mapped[int] = mapped_column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)
    sheet_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    source_row_ref: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="ссылка на исходную строку raw-таблицы")
    sheet_period: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    item_name: Mapped[str] = mapped_column(Text, nullable=False)
    supplier: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    price_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, default="RUB")
    unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # Признак, что в исходной ячейке не было значения (пусто). Позволяет SQL-агенту
    # корректно считать средние — делить на заполненные, а не на все.
    is_blank: Mapped[bool] = mapped_column(Integer, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_mart_price_facts_item_name", "item_name"),
        Index("ix_mart_price_facts_supplier", "supplier"),
        Index("ix_mart_price_facts_sheet_period", "sheet_period"),
        Index("ix_mart_price_facts_file_id", "file_id"),
        Index("ix_mart_price_facts_sheet_id", "sheet_id"),
        Index("ix_mart_price_facts_is_blank", "is_blank"),
        {"schema": "mart"},
    )


class SheetTemplate(Base):
    """mart.sheet_templates — кэш подтверждённых LLM-схем листов.

    Хранит отпечаток структуры листа (fingerprint) и распознанную LLM-схему.
    При повторной загрузке файла того же формата схема применяется без вызова LLM.
    Статус: pending_confirmation → confirmed (после ручного подтверждения в UI).
    """

    __tablename__ = "sheet_templates"
    __table_args__ = {"schema": "mart"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    schema_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    sheet_name_pattern: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending_confirmation", index=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confirmed_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_mart_sheet_templates_status", "status"),
        Index("ix_mart_sheet_templates_fingerprint", "fingerprint"),
        {"schema": "mart"},
    )


class Metric(Base):
    """mart.metrics — универсальная long-таблица для любых числовых таблиц.

    Покрывает формат 'matrix' (шихта/план/факт/отклонение/проценты), который
    mart.price_facts не может описать. Колонки:
    - dimension_type/dimension: семантическое измерение (например, 'item'/'медь')
    - metric_type: тип метрики ('план' / 'факт' / 'отклонение' / 'percent' / ...)
    - metric: наименование метрики (например, 'состав шихты')
    """

    __tablename__ = "metrics"
    __table_args__ = {"schema": "mart"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    file_id: Mapped[int] = mapped_column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)
    sheet_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    source_row_ref: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    dimension_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    dimension: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    period: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    metric_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    metric: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_blank: Mapped[bool] = mapped_column(Integer, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_mart_metrics_dimension", "dimension"),
        Index("ix_mart_metrics_metric_type", "metric_type"),
        Index("ix_mart_metrics_period", "period"),
        Index("ix_mart_metrics_file_id", "file_id"),
        Index("ix_mart_metrics_sheet_id", "sheet_id"),
        Index("ix_mart_metrics_metric", "metric"),
        {"schema": "mart"},
    )


class SupplierAlias(Base):
    """mart.supplier_aliases — маппинг поставщиков (канонические имена и алиасы).

    Один поставщик может появляться в шапке по-разному:
    'северо-запад ВторМет * (921)341-19-36 (Алла)' vs 'Северо-запад' vs 'ЦветМет'.
    canonical_name — каноническое имя, alias — синоним (добавляется из шапки).
    """

    __tablename__ = "supplier_aliases"
    __table_args__ = {"schema": "mart"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    alias: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    source_sheet_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_mart_supplier_aliases_canonical_name", "canonical_name"),
        Index("ix_mart_supplier_aliases_alias", "alias"),
        Index("ix_mart_supplier_aliases_source_sheet_id", "source_sheet_id"),
        {"schema": "mart"},
    )