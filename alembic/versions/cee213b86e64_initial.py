"""initial

Revision ID: cee213b86e64
Revises: 
Create Date: 2026-07-26 06:52:34.567682

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cee213b86e64'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Векторные данные (dense + sparse) хранятся в Qdrant,
    поэтому pgvector-таблицы (chunk_embeddings, sheet_embeddings,
    column_embeddings, query_embedding_cache) здесь не создаются.
    """
    op.create_table('entity_dictionary',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('canonical_name', sa.String(length=255), nullable=False),
    sa.Column('aliases', sa.JSON(), nullable=True),
    sa.Column('category', sa.String(length=100), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('embedding', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_entity_dictionary_canonical_name', 'entity_dictionary', ['canonical_name'], unique=False)
    op.create_index('ix_entity_dictionary_category', 'entity_dictionary', ['category'], unique=False)
    op.create_index(op.f('ix_entity_dictionary_id'), 'entity_dictionary', ['id'], unique=False)
    op.create_table('files',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('file_hash', sa.String(length=64), nullable=False),
    sa.Column('total_sheets', sa.Integer(), nullable=False),
    sa.Column('total_rows', sa.Integer(), nullable=False),
    sa.Column('total_cells', sa.Integer(), nullable=False),
    sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('meta', sa.JSON(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_files_file_hash'), 'files', ['file_hash'], unique=True)
    op.create_index(op.f('ix_files_id'), 'files', ['id'], unique=False)
    op.create_index('ix_files_status', 'files', ['status'], unique=False)
    op.create_index('ix_files_uploaded_at', 'files', ['uploaded_at'], unique=False)
    op.create_table('golden_dataset',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('question', sa.Text(), nullable=False),
    sa.Column('query_type', sa.String(length=50), nullable=False),
    sa.Column('entities', sa.JSON(), nullable=True),
    sa.Column('expected_sql', sa.Text(), nullable=False),
    sa.Column('expected_result', sa.JSON(), nullable=True),
    sa.Column('expected_answer', sa.Text(), nullable=True),
    sa.Column('category', sa.String(length=100), nullable=True),
    sa.Column('tags', sa.JSON(), nullable=True),
    sa.Column('is_active', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_golden_dataset_category', 'golden_dataset', ['category'], unique=False)
    op.create_index(op.f('ix_golden_dataset_id'), 'golden_dataset', ['id'], unique=False)
    op.create_index('ix_golden_dataset_is_active', 'golden_dataset', ['is_active'], unique=False)
    op.create_table('query_cache',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('question_hash', sa.String(length=64), nullable=False),
    sa.Column('question', sa.Text(), nullable=False),
    sa.Column('normalized_question', sa.Text(), nullable=False),
    sa.Column('sql_query', sa.Text(), nullable=False),
    sa.Column('result', sa.JSON(), nullable=True),
    sa.Column('query_type', sa.String(length=50), nullable=False),
    sa.Column('entities', sa.JSON(), nullable=True),
    sa.Column('hit_count', sa.Integer(), nullable=False),
    sa.Column('last_used', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_query_cache_id'), 'query_cache', ['id'], unique=False)
    op.create_index('ix_query_cache_query_type', 'query_cache', ['query_type'], unique=False)
    op.create_index(op.f('ix_query_cache_question_hash'), 'query_cache', ['question_hash'], unique=True)
    op.create_table('query_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('request_id', sa.String(length=36), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('user_id', sa.String(length=100), nullable=True),
    sa.Column('question', sa.Text(), nullable=False),
    sa.Column('plan', sa.Text(), nullable=True),
    sa.Column('sql_query', sa.Text(), nullable=True),
    sa.Column('result', sa.JSON(), nullable=True),
    sa.Column('trace', sa.JSON(), nullable=True),
    sa.Column('latency_ms', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_query_logs_created_at', 'query_logs', ['created_at'], unique=False)
    op.create_index(op.f('ix_query_logs_id'), 'query_logs', ['id'], unique=False)
    op.create_index('ix_query_logs_request_id', 'query_logs', ['request_id'], unique=False)
    op.create_index('ix_query_logs_status', 'query_logs', ['status'], unique=False)
    op.create_index(op.f('ix_query_logs_user_id'), 'query_logs', ['user_id'], unique=False)
    op.create_table('sheets',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('file_id', sa.Integer(), nullable=False),
    sa.Column('sheet_index', sa.Integer(), nullable=False),
    sa.Column('original_name', sa.String(length=255), nullable=False),
    sa.Column('normalized_name', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('row_count', sa.Integer(), nullable=False),
    sa.Column('col_count', sa.Integer(), nullable=False),
    sa.Column('period', sa.String(length=50), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['file_id'], ['files.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sheets_file_id'), 'sheets', ['file_id'], unique=False)
    op.create_index(op.f('ix_sheets_id'), 'sheets', ['id'], unique=False)
    op.create_index(op.f('ix_sheets_normalized_name'), 'sheets', ['normalized_name'], unique=False)
    op.create_index('ix_sheets_original_name', 'sheets', ['original_name'], unique=False)
    op.create_index('ix_sheets_period', 'sheets', ['period'], unique=False)
    op.create_table('cells',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('sheet_id', sa.Integer(), nullable=False),
    sa.Column('row_num', sa.Integer(), nullable=False),
    sa.Column('col_index', sa.Integer(), nullable=False),
    sa.Column('value_text', sa.Text(), nullable=True),
    sa.Column('value_number', sa.Float(), nullable=True),
    sa.Column('value_date', sa.DateTime(), nullable=True),
    sa.Column('is_error', sa.Integer(), nullable=False),
    sa.Column('error_type', sa.String(length=50), nullable=True),
    sa.Column('original_value', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['sheet_id'], ['sheets.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_cells_id'), 'cells', ['id'], unique=False)
    op.create_index(op.f('ix_cells_sheet_id'), 'cells', ['sheet_id'], unique=False)
    op.create_index('ix_cells_value_number', 'cells', ['value_number'], unique=False)
    op.create_table('column_metadata',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('sheet_id', sa.Integer(), nullable=False),
    sa.Column('col_index', sa.Integer(), nullable=False),
    sa.Column('original_name', sa.String(length=255), nullable=False),
    sa.Column('normalized_name', sa.String(length=255), nullable=False),
    sa.Column('data_type', sa.String(length=50), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('sample_values', sa.JSON(), nullable=True),
    sa.ForeignKeyConstraint(['sheet_id'], ['sheets.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_column_metadata_data_type', 'column_metadata', ['data_type'], unique=False)
    op.create_index(op.f('ix_column_metadata_id'), 'column_metadata', ['id'], unique=False)
    op.create_index('ix_column_metadata_normalized_name', 'column_metadata', ['normalized_name'], unique=False)
    op.create_index(op.f('ix_column_metadata_sheet_id'), 'column_metadata', ['sheet_id'], unique=False)
    op.create_table('excel_comments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('sheet_id', sa.Integer(), nullable=False),
    sa.Column('cell_ref', sa.String(length=20), nullable=False),
    sa.Column('row_num', sa.Integer(), nullable=False),
    sa.Column('col_index', sa.Integer(), nullable=False),
    sa.Column('author', sa.String(length=255), nullable=True),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['sheet_id'], ['sheets.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_excel_comments_cell_ref', 'excel_comments', ['cell_ref'], unique=False)
    op.create_index(op.f('ix_excel_comments_id'), 'excel_comments', ['id'], unique=False)
    op.create_index('ix_excel_comments_sheet_id', 'excel_comments', ['sheet_id'], unique=False)
    op.create_table('fact_prices',
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
    sa.PrimaryKeyConstraint('id')
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


def downgrade() -> None:
    """Downgrade schema."""
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
    op.drop_index('ix_excel_comments_sheet_id', table_name='excel_comments')
    op.drop_index(op.f('ix_excel_comments_id'), table_name='excel_comments')
    op.drop_index('ix_excel_comments_cell_ref', table_name='excel_comments')
    op.drop_table('excel_comments')
    op.drop_index(op.f('ix_column_metadata_sheet_id'), table_name='column_metadata')
    op.drop_index('ix_column_metadata_normalized_name', table_name='column_metadata')
    op.drop_index(op.f('ix_column_metadata_id'), table_name='column_metadata')
    op.drop_index('ix_column_metadata_data_type', table_name='column_metadata')
    op.drop_table('column_metadata')
    op.drop_index('ix_cells_value_number', table_name='cells')
    op.drop_index(op.f('ix_cells_sheet_id'), table_name='cells')
    op.drop_index(op.f('ix_cells_id'), table_name='cells')
    op.drop_table('cells')
    op.drop_index('ix_sheets_period', table_name='sheets')
    op.drop_index('ix_sheets_original_name', table_name='sheets')
    op.drop_index(op.f('ix_sheets_normalized_name'), table_name='sheets')
    op.drop_index(op.f('ix_sheets_id'), table_name='sheets')
    op.drop_index(op.f('ix_sheets_file_id'), table_name='sheets')
    op.drop_table('sheets')
    op.drop_index(op.f('ix_query_logs_user_id'), table_name='query_logs')
    op.drop_index('ix_query_logs_status', table_name='query_logs')
    op.drop_index('ix_query_logs_request_id', table_name='query_logs')
    op.drop_index(op.f('ix_query_logs_id'), table_name='query_logs')
    op.drop_index('ix_query_logs_created_at', table_name='query_logs')
    op.drop_table('query_logs')
    op.drop_index(op.f('ix_query_cache_question_hash'), table_name='query_cache')
    op.drop_index('ix_query_cache_query_type', table_name='query_cache')
    op.drop_index(op.f('ix_query_cache_id'), table_name='query_cache')
    op.drop_table('query_cache')
    op.drop_index('ix_golden_dataset_is_active', table_name='golden_dataset')
    op.drop_index(op.f('ix_golden_dataset_id'), table_name='golden_dataset')
    op.drop_index('ix_golden_dataset_category', table_name='golden_dataset')
    op.drop_table('golden_dataset')
    op.drop_index('ix_files_uploaded_at', table_name='files')
    op.drop_index('ix_files_status', table_name='files')
    op.drop_index(op.f('ix_files_id'), table_name='files')
    op.drop_index(op.f('ix_files_file_hash'), table_name='files')
    op.drop_table('files')
    op.drop_index(op.f('ix_entity_dictionary_id'), table_name='entity_dictionary')
    op.drop_index('ix_entity_dictionary_category', table_name='entity_dictionary')
    op.drop_index('ix_entity_dictionary_canonical_name', table_name='entity_dictionary')
    op.drop_table('entity_dictionary')
