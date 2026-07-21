from src.core.db.base import Base 
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Integer, func, String, DateTime, Index, Text, ForeignKey, text
from pgvector.sqlalchemy import Vector
from datetime import datetime


class SheetEmbedding(Base):
    __tablename__ = "sheet_embeddings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    sheet_id: Mapped[int] = mapped_column(Integer, ForeignKey("sheets.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    source_text: Mapped[text] = mapped_column(Text, nullable=False)  
    embedding: Mapped[Vector] = mapped_column(Vector(768), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)  
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    sheet = relationship("Sheet", back_populates="embedding")


class ColumnEmbedding(Base):
    __tablename__ = "column_embeddings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    column_id: Mapped[int] = mapped_column(Integer, ForeignKey("column_metadata.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    source_text: Mapped[text] = mapped_column(Text, nullable=False)
    embedding: Mapped[Vector] = mapped_column(Vector(768), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    column = relationship("ColumnMetadata", back_populates="embedding")


class QueryEmbeddingCache(Base):
    __tablename__ = "query_embedding_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    query_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    query_text: Mapped[text] = mapped_column(Text, nullable=False)
    embedding: Mapped[Vector] = mapped_column(Vector(768), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_query_embedding_cache_hash", "query_hash"),
    )