"""Remove vector embedding tables and entity_embeddings

Revision ID: d9f2c3a1e5b7
Revises: b7a4f21e3c91
Create Date: 2026-08-11 08:00:00.000000

Удаляет эмбеддинг-таблицы, унаследованные от старой RAG-over-cells архитектуры:
- entity_embeddings (компактный справочник эмбеддингов сущностей) — заменён на
  прямое чтение сущностей из mart.price_facts + pg_trgm.
- entity_dictionary.embedding колонка (JSON) — больше не используется.
- query_cache переиспользуется как простой кэш «нормализованный вопрос → SQL →
  результат» без векторного сравнения (структура не меняется).

Qdrant/pgvector-таблицы (chunk_embeddings/sheet_embeddings/col_emb) в этой схеме
не существовали, поэтому миграция только зачищает entity_embeddings.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd9f2c3a1e5b7'
down_revision: Union[str, Sequence[str], None] = 'b7a4f21e3c91'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # Drop entity_embeddings (удалена из models.py).
    bind.execute(sa.text("DROP TABLE IF EXISTS entity_embeddings"))

    # Убираем устаревшую колонку embedding из entity_dictionary (JSON, не используется).
    cols = bind.execute(sa.text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='entity_dictionary' AND column_name='embedding'"
    )).fetchall()
    if cols:
        bind.execute(sa.text("ALTER TABLE entity_dictionary DROP COLUMN IF EXISTS embedding"))


def downgrade() -> None:
    bind = op.get_bind()

    op.create_table(
        'entity_embeddings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('entity_type', sa.String(length=20), nullable=False),
        sa.Column('entity_value', sa.Text(), nullable=False),
        sa.Column('embedding', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_entity_embeddings_type_value', 'entity_embeddings', ['entity_type', 'entity_value'])
    op.create_index(op.f('ix_entity_embeddings_id'), 'entity_embeddings', ['id'], unique=False)

    bind.execute(sa.text("ALTER TABLE entity_dictionary ADD COLUMN IF NOT EXISTS embedding JSON"))