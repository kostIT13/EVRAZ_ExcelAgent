"""Drop legacy fact_prices table

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-08-13 15:05:00.000000

Удаляет устаревшую таблицу ``fact_prices`` (модель ``FactPrice`` в схеме ``public``),
которая была промежуточным источником для нормализации. Все факты теперь пишутся
напрямую в ``mart.price_facts`` (модель ``PriceFact``), а сущности для pg_trgm
собираются напрямую из ``mart.price_facts``.

- Таблица ``fact_prices`` и её индексы удаляются.
- Связанные данные переносить не нужно: нормализация выполняется идемпотентно
  из raw.cells в mart.price_facts.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop legacy fact_prices table and its indexes."""
    op.drop_index('ix_fact_prices_sheet_item', table_name='fact_prices')
    op.drop_index(op.f('ix_fact_prices_sheet_id'), table_name='fact_prices')
    op.drop_index('ix_fact_prices_price_source', table_name='fact_prices')
    op.drop_index('ix_fact_prices_period_source', table_name='fact_prices')
    op.drop_index(op.f('ix_fact_prices_period'), table_name='fact_prices')
    op.drop_index(op.f('ix_fact_prices_item_name_normalized'), table_name='fact_prices')
    op.drop_index('ix_fact_prices_item_name', table_name='fact_prices')
    op.drop_index(op.f('ix_fact_prices_item_id'), table_name='fact_prices')
    op.drop_index(op.f('ix_fact_prices_id'), table_name='fact_prices')
    op.drop_table('fact_prices')


def downgrade() -> None:
    """Recreate legacy fact_prices table (empty)."""
    op.create_table(
        'fact_prices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sheet_id', sa.Integer(), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=True),
        sa.Column('period', sa.String(length=50), nullable=False),
        sa.Column('item_name_raw', sa.Text(), nullable=False),
        sa.Column('item_name_normalized', sa.Text(), nullable=False),
        sa.Column('price_source', sa.String(length=100), nullable=False),
        sa.Column('price_value', sa.Float(), nullable=True),
        sa.Column('row_num', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['item_id'], ['entity_dictionary.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['sheet_id'], ['sheets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_fact_prices_id'), 'fact_prices', ['id'], unique=False)
    op.create_index(op.f('ix_fact_prices_item_id'), 'fact_prices', ['item_id'], unique=False)
    op.create_index('ix_fact_prices_item_name', 'fact_prices', ['item_name_normalized'], unique=False)
    op.create_index(op.f('ix_fact_prices_item_name_normalized'), 'fact_prices', ['item_name_normalized'], unique=False)
    op.create_index(op.f('ix_fact_prices_period'), 'fact_prices', ['period'], unique=False)
    op.create_index('ix_fact_prices_period_source', 'fact_prices', ['period', 'price_source'], unique=False)
    op.create_index('ix_fact_prices_price_source', 'fact_prices', ['price_source'], unique=False)
    op.create_index(op.f('ix_fact_prices_sheet_id'), 'fact_prices', ['sheet_id'], unique=False)
    op.create_index('ix_fact_prices_sheet_item', 'fact_prices', ['sheet_id', 'item_name_normalized'], unique=False)