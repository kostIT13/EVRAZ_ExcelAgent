# Пайплайн загрузки и нормализации Excel

Путь файла от загрузки до витрины `mart`. Параллельные потоки: сырые таблицы
(`files`/`sheets`/`column_metadata`/`cells`) и нормализованные long-факты
(`mart.price_facts` / `mart.metrics`), плюс алиасы поставщиков и сущности.

```mermaid
flowchart TD
    START(["POST /files/upload"]) --> A{Валидация<br/>.xlsx / .xls, ≤50 МБ}
    A -- нет --> ERR(["400 ValidationError"])
    A -- да --> TMP[Запись во временный файл]

    TMP --> Q[["IngestionQueue (async worker)"]]
    Q -->|1| PENDING[create_pending_file: запись File = upload/pending]
    PENDING --> PARSER

    subgraph Parse ["Парсинг (src/core/excel)"]
        PARSER[ExcelParser<br/>unmerge, detect header rows] --> SHEETS[Pydantic ParsedFile: sheets / headers / data / cells]
        SHEETS --> NORM[ExcelNormalizer: normalize_header, infer_column_type]
        SHEETS --> KIND[sheet_kind_detector: prices / matrix / generic]
        SHEETS --> STRUC[TableStructurer: period из имени листа]
        SHEETS --> COMM[comment_extractor: комментарии ячеек]
    end

    NORM --> REPO[SQLAlchemyExcelRepository.save_parsed_file]
    KIND --> REPO
    STRUC --> REPO
    COMM --> REPO

    REPO --> RAW[["RAW: files / sheets / column_metadata / cells / excel_comments"]]
    REPO -->|идемпотентность: удаление старых листов файла| REPO

    RAW --> MART[normalize_file_to_mart]

    subgraph Mart ["Витрина mart (src/services/mart)"]
        MART --> P1{sheet_kind?}
        P1 -- prices --> FACTS[price_facts: item_name, supplier, price_type, value, is_blank]
        P1 -- matrix --> METRICS[metrics: dimension, metric_type, metric, value]
        MART --> ALIAS[supplier_aliases: canonical + alias]
        MART --> TPL[sheet_templates по fingerprint]
    end

    FACTS --> ENT[EntityResolver.index_entities]
    METRICS --> ENT
    ENT --> USAGE[item / supplier / period каталог для агента]

    MART --> DONE(["File status = processed"])
```

## Последовательность инжеста

```mermaid
sequenceDiagram
    actor U as Пользователь
    participant API as FastAPI /files
    participant Q as IngestionQueue
    participant S as ExcelIngestionService
    participant R as Repository
    participant N as Mart Normalizer
    participant DB as PostgreSQL

    U->>API: upload .xlsx
    API->>Q: enqueue(path)
    Q->>S: create_pending_file
    S->>DB: insert files (pending)
    Q->>S: process_file
    S->>R: process_file
    R->>R: parse → save sheets/columns/cells (RAW)
    R-->>DB: insert files/sheets/column_metadata/cells
    S->>N: normalize_file_to_mart
    N->>N: удалить старые факты файла (идемпотентность)
    N-->>DB: insert mart.price_facts / metrics / supplier_aliases
    S->>R: index_entities
    R-->>DB: каталог сущностей (item/supplier/period)
    S-->>Q: status = processed
    Q-->>API: file_id + статус