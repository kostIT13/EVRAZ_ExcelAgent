"""Add mart.metrics, supplier_aliases, sheet_kind, column role, is_blank

Revision ID: c2d3e4f5a6b7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-13 16:35:00.000000

Добавляет (см. plan.md, этапы 1-2):
- ``mart.metrics`` — универсальная long-таблица для числовых таблиц формата
  ``matrix`` (шихта/план/факт/отклонение/проценты).
- ``mart.supplier_aliases`` — маппинг канонических имён поставщиков и алиасов.
- ``sheets.sheet_kind`` / ``sheets.sheet_kind_auto`` — типизация листов
  (prices / matrix / generic) + признак авто-детекции.
- ``column_metadata.role`` — семантическая роль колонки
  (item / price / supplier / percent / metric_type / other).
- ``mart.price_facts.is_blank`` — признак пустой ячейки (NULL не превращается в 0).
- ``mart.metrics.is_blank`` — то же для metrics.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c2d3e4f5a6b7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # Схема mart уже существует (создана в b7a4f21e3c91).
    bind.execute(sa.text("CREATE SCHEMA IF NOT EXISTS mart"))

    # --- sheets.sheet_kind + sheet_kind_auto ---
    op.add_column('sheets', sa.Column('sheet_kind', sa.String(length=30), nullable=False, server_default='generic'))
    op.add_column('sheets', sa.Column('sheet_kind_auto', sa.Integer(), nullable=False, server_default='1'))
    op.create_index('ix_sheets_sheet_kind', 'sheets', ['sheet_kind'])

    # --- column_metadata.role ---
    op.add_column('column_metadata', sa.Column('role', sa.String(length=50), nullable=True))
    op.create_index('ix_column_metadata_role', 'column_metadata', ['role'])

    # --- mart.price_facts.is_blank ---
    op.add_column('price_facts', sa.Column('is_blank', sa.Integer(), nullable=False, server_default='0'), schema='mart')
    op.create_index('ix_mart_price_facts_is_blank', 'price_facts', ['is_blank'], schema='mart')

    # --- mart.metrics ---
    op.create_table(
        'metrics',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('file_id', sa.Integer(), sa.ForeignKey('files.id', ondelete='CASCADE'), nullable=False),
        sa.Column('sheet_id', sa.Integer(), nullable=True),
        sa.Column('source_row_ref', sa.String(length=50), nullable=True),
        sa.Column('dimension_type', sa.String(length=100), nullable=True),
        sa.Column('dimension', sa.Text(), nullable=True),
        sa.Column('period', sa.String(length=50), nullable=True),
        sa.Column('metric_type', sa.String(length=100), nullable=True),
        sa.Column('metric', sa.Text(), nullable=True),
        sa.Column('value', sa.Float(), nullable=True),
        sa.Column('unit', sa.String(length=50), nullable=True),
        sa.Column('is_blank', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        schema='mart',
    )
    op.create_index('ix_mart_metrics_dimension', 'metrics', ['dimension'], schema='mart')
    op.create_index('ix_mart_metrics_metric_type', 'metrics', ['metric_type'], schema='mart')
    op.create_index('ix_mart_metrics_period', 'metrics', ['period'], schema='mart')
    op.create_index('ix_mart_metrics_file_id', 'metrics', ['file_id'], schema='mart')
    op.create_index('ix_mart_metrics_sheet_id', 'metrics', ['sheet_id'], schema='mart')
    op.create_index('ix_mart_metrics_metric', 'metrics', ['metric'], schema='mart')
    op.create_index('ix_mart_metrics_is_blank', 'metrics', ['is_blank'], schema='mart')

    # --- mart.supplier_aliases ---
    op.create_table(
        'supplier_aliases',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('canonical_name', sa.String(length=255), nullable=False),
        sa.Column('alias', sa.String(length=255), nullable=False),
        sa.Column('source_sheet_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('alias'),
        schema='mart',
    )
    op.create_index('ix_mart_supplier_aliases_canonical_name', 'supplier_aliases', ['canonical_name'], schema='mart')
    op.create_index('ix_mart_supplier_aliases_alias', 'supplier_aliases', ['alias'], schema='mart')
    op.create_index('ix_mart_supplier_aliases_source_sheet_id', 'supplier_aliases', ['source_sheet_id'], schema='mart')

    # GIN-индекс pg_trgm по metric/dimension для fuzzy-поиска.
    bind.execute(sa.text(
        "CREATE INDEX ix_mart_metrics_dimension_trgm "
        "ON mart.metrics USING gin (dimension gin_trgm_ops)"
    ))
    bind.execute(sa.text(
        "CREATE INDEX ix_mart_metrics_metric_trgm "
        "ON mart.metrics USING gin (metric gin_trgm_ops)"
    ))


def downgrade() -> None:
    bind = op.get_bind()

    bind.execute(sa.text("DROP INDEX IF EXISTS ix_mart_metrics_metric_trgm"))
    bind.execute(sa.text("DROP INDEX IF EXISTS ix_mart_metrics_dimension_trgm"))

    op.drop_table('supplier_aliases', schema='mart')
    op.drop_table('metrics', schema='mart')

    op.drop_index('ix_mart_price_facts_is_blank', table_name='price_facts', schema='mart')
    op.drop_column('price_facts', 'is_blank', schema='mart')

    op.drop_index('ix_column_metadata_role', table_name='column_metadata')
    op.drop_column('column_metadata', 'role')

    op.drop_index('ix_sheets_sheet_kind', table_name='sheets')
    op.drop_column('sheets', 'sheet_kind_auto')
    op.drop_column('sheets', 'sheet_kind')