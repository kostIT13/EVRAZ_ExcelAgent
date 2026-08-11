"""Add mart.price_facts, sheet_templates, pg_trgm extension

Revision ID: b7a4f21e3c91
Revises: cee213b86e64
Create Date: 2026-08-11 07:25:00.000000

Добавляет:
- schema ``mart`` и таблицу ``mart.price_facts`` (нормализованная long-таблица).
- таблицу ``mart.sheet_templates`` (кэш подтверждённых LLM-схем листов).
- расширение ``pg_trgm`` и GIN-индексы для fuzzy-поиска по item_name/supplier.
- read-only роль ``app_readonly`` с GRANT SELECT на mart.*.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7a4f21e3c91'
down_revision: Union[str, Sequence[str], None] = 'cee213b86e64'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # Расширение pg_trgm для fuzzy-поиска (similarity() / % оператор).
    bind.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))

    # Схема mart и long-таблица фактов.
    op.execute(sa.text("CREATE SCHEMA IF NOT EXISTS mart"))

    op.create_table(
        'price_facts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('file_id', sa.Integer(), sa.ForeignKey('files.id', ondelete='CASCADE'), nullable=False),
        sa.Column('sheet_id', sa.Integer(), nullable=True),
        sa.Column('source_row_ref', sa.String(length=50), nullable=True),
        sa.Column('sheet_period', sa.String(length=50), nullable=True),
        sa.Column('item_name', sa.Text(), nullable=False),
        sa.Column('supplier', sa.Text(), nullable=True),
        sa.Column('price_type', sa.String(length=100), nullable=True),
        sa.Column('value', sa.Float(), nullable=True),
        sa.Column('currency', sa.String(length=20), nullable=True),
        sa.Column('unit', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        schema='mart',
    )
    op.create_index('ix_mart_price_facts_item_name', 'price_facts', ['item_name'], schema='mart')
    op.create_index('ix_mart_price_facts_supplier', 'price_facts', ['supplier'], schema='mart')
    op.create_index('ix_mart_price_facts_sheet_period', 'price_facts', ['sheet_period'], schema='mart')
    op.create_index('ix_mart_price_facts_file_id', 'price_facts', ['file_id'], schema='mart')
    op.create_index('ix_mart_price_facts_sheet_id', 'price_facts', ['sheet_id'], schema='mart')
    op.create_index('ix_mart_price_facts_price_type', 'price_facts', ['price_type'], schema='mart')

    # GIN-индексы pg_trgm для fuzzy-поиска по item_name/supplier.
    bind.execute(sa.text(
        "CREATE INDEX ix_mart_price_facts_item_name_trgm "
        "ON mart.price_facts USING gin (item_name gin_trgm_ops)"
    ))
    bind.execute(sa.text(
        "CREATE INDEX ix_mart_price_facts_supplier_trgm "
        "ON mart.price_facts USING gin (supplier gin_trgm_ops)"
    ))

    # Компактный справочник эмбеддингов сущностей удалён из архитектуры:
    # список сущностей для pg_trgm-сопоставления берётся напрямую из mart.price_facts.

    # Кэш подтверждённых LLM-схем листов (schema inference / template fingerprint).
    op.create_table(
        'sheet_templates',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('fingerprint', sa.String(length=64), nullable=False),
        sa.Column('schema_json', sa.JSON(), nullable=True),
        sa.Column('sheet_name_pattern', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('confirmed_by', sa.String(length=100), nullable=True),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('fingerprint'),
        schema='mart',
    )
    op.create_index('ix_mart_sheet_templates_status', 'sheet_templates', ['status'], schema='mart')
    op.create_index('ix_mart_sheet_templates_fingerprint', 'sheet_templates', ['fingerprint'], schema='mart')
    op.create_index(op.f('ix_mart_sheet_templates_id'), 'sheet_templates', ['id'], unique=False, schema='mart')

    # Read-only роль для Executor-узла: доступ только на чтение mart.*.
    bind.execute(sa.text(
        "DO $$ BEGIN "
        " IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_readonly') THEN "
        "   CREATE ROLE app_readonly NOLOGIN; "
        " END IF; "
        "END $$;"
    ))
    bind.execute(sa.text("GRANT USAGE ON SCHEMA mart TO app_readonly"))
    bind.execute(sa.text("GRANT SELECT ON ALL TABLES IN SCHEMA mart TO app_readonly"))
    bind.execute(sa.text("ALTER DEFAULT PRIVILEGES IN SCHEMA mart GRANT SELECT ON TABLES TO app_readonly"))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DROP INDEX IF EXISTS ix_mart_price_facts_item_name_trgm"))
    bind.execute(sa.text("DROP INDEX IF EXISTS ix_mart_price_facts_supplier_trgm"))
    op.drop_table('sheet_templates', schema='mart')
    op.drop_table('price_facts', schema='mart')
    op.execute(sa.text("DROP SCHEMA IF EXISTS mart"))
    bind.execute(sa.text("DROP ROLE IF EXISTS app_readonly"))