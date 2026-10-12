# Схема базы данных

Две схемы: **public** (сырые данные и служебные таблицы) и **mart** (нормализованная
витрина для SQL-агента). Булевы поля (`is_blank`, `sheet_kind_auto`, `is_active`)
хранятся как `INTEGER (0/1)`.

```mermaid
erDiagram
    FILES ||--o{ SHEETS : "file_id"
    FILES ||--o{ CELLS : "via sheets"
    SHEETS ||--o{ COLUMN_METADATA : "sheet_id"
    SHEETS ||--o{ CELLS : "sheet_id"
    SHEETS ||--o{ EXCEL_COMMENTS : "sheet_id"
    FILES ||--o{ MART_PRICE_FACTS : "file_id"
    FILES ||--o{ MART_METRICS : "file_id"

    FILES {
        int id PK
        varchar filename
        varchar file_hash UK
        int total_sheets
        int total_rows
        int total_cells
        varchar status
        text error_message
        json meta
        timestamp uploaded_at
    }

    SHEETS {
        int id PK
        int file_id FK
        int sheet_index
        varchar original_name
        varchar normalized_name
        varchar period
        varchar sheet_kind "prices|matrix|generic"
        int row_count
        int col_count
    }

    COLUMN_METADATA {
        int id PK
        int sheet_id FK
        int col_index
        varchar original_name
        varchar normalized_name
        varchar data_type "text|number|price|date|id"
        varchar role "item|price|supplier|metric_type"
        json sample_values
    }

    CELLS {
        int id PK
        int sheet_id FK
        int row_num
        int col_index
        text value_text
        float value_number
        timestamp value_date
        text original_value
    }

    ENTITY_DICTIONARY {
        int id PK
        varchar canonical_name UK
        json aliases
        varchar category
        json embedding
    }

    EXCEL_COMMENTS {
        int id PK
        int sheet_id FK
        varchar cell_ref
        int row_num
        int col_index
        varchar author
        text text
    }

    QUERY_CACHE {
        int id PK
        varchar question_hash UK
        text question
        text sql_query
        json result
        varchar query_type
    }

    GOLDEN_DATASET {
        int id PK
        text question
        text expected_sql
        json expected_result
        varchar category
        int is_active
    }

    QUERY_LOGS {
        int id PK
        varchar request_id
        text question
        text plan
        text sql_query
        json result
        json trace
        int latency_ms
        varchar status
    }

    MART_PRICE_FACTS {
        int id PK
        int file_id FK
        int sheet_id
        varchar sheet_period
        text item_name
        text supplier
        varchar price_type "среднерыночная|аукцион_старт|аукцион_победитель|поставщик"
        float value
        varchar currency
        varchar unit
        int is_blank "0|1"
    }

    MART_METRICS {
        int id PK
        int file_id FK
        int sheet_id
        varchar dimension_type
        text dimension
        varchar period
        varchar metric_type
        text metric
        float value
        varchar unit
        int is_blank
    }

    MART_SUPPLIER_ALIASES {
        int id PK
        varchar canonical_name
        varchar alias UK
        int source_sheet_id
    }

    MART_SHEET_TEMPLATES {
        int id PK
        varchar fingerprint UK
        json schema_json
        varchar sheet_name_pattern
        varchar status "confirmed|pending_confirmation"
        float confidence
    }
```

## Ключевые связи

- `files` → `sheets` (каскадное удаление), `sheets` → `column_metadata` / `cells` / `excel_comments`.
- `files` → `mart.price_facts` / `mart.metrics` по `file_id` (`ON DELETE CASCADE`).
- Агент напрямую читает только `mart.price_facts` и `mart.metrics` (whitelist в `sql_compiler`).
- `entity_dictionary` и `bm25_index.pkl` / `rapidfuzz` используются для разрешения сущностей до генерации SQL.