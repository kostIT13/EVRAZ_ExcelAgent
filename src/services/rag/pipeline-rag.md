# RAG Pipeline — полное описание

**RAG (Retrieval-Augmented Generation)** — пайплайн, который находит релевантные данные из Excel-файлов по вопросу пользователя и генерирует ответ на основе этих данных.

---

## Содержание

- [Общая схема](#общая-схема)
- [1. Ingestion — загрузка и индексация](#1-ingestion--загрузка-и-индексация)
  - [1.1 Парсинг Excel](#11-парсинг-excel)
  - [1.2 Нормализация](#12-нормализация)
  - [1.3 Сохранение в БД](#13-сохранение-в-бд)
  - [1.4 Векторная индексация](#14-векторная-индексация)
- [2. Retrieval — поиск](#2-retrieval--поиск)
  - [2.1 Chunking (разбивка на чанки)](#21-chunking-разбивка-на-чанки)
  - [2.2 Dense retrieval (плотный поиск)](#22-dense-retrieval-плотный-поиск)
  - [2.3 Sparse retrieval (BM25)](#23-sparse-retrieval-bm25)
  - [2.4 Гибридная фузия](#24-гибридная-фузия)
- [3. Generation — генерация ответа](#3-generation--генерация-ответа)
  - [3.1 Форматирование контекста](#31-форматирование-контекста)
  - [3.2 Промпт для LLM](#32-промпт-для-llm)
  - [3.3 Self-Correction](#33-self-correction)
- [4. Verification — верификация](#4-verification--верификация)
- [5. Полный цикл запроса](#5-полный-цикл-запроса)
- [Ключевые файлы](#ключевые-файлы)

---

## Общая схема

```
┌─────────────────────────────────────────────────────────────────────┐
│                         INGESTION (однократно)                       │
│                                                                     │
│  Excel ──▶ ExcelParser ──▶ ExcelNormalizer ──▶ ExcelRepository      │
│  .xlsx       (openpyxl)     (типы, очистка)      (SQLAlchemy)       │
│                                                    │                │
│                                                    ▼                │
│  ┌──────────────────────────────────────────────────────┐           │
│  │                  PostgreSQL (pgvector)                │           │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐           │           │
│  │  │  files   │  │  sheets  │  │ columns  │           │           │
│  │  ├──────────┤  ├──────────┤  ├──────────┤           │           │
│  │  │  cells   │  │chunk_emb │  │col_emb   │           │           │
│  │  └──────────┘  └──────────┘  └──────────┘           │           │
│  └──────────────────────────────────────────────────────┘           │
│                              │                                      │
│                              ▼                                      │
│  ┌──────────────────────────────────────────────────────┐           │
│  │              RagService.build_index_for_file()        │           │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │           │
│  │  │  Chunker     │  │  Embedder    │  │  BM25Index │ │           │
│  │  │  (adaptive)  │  │  (fastembed) │  │  (disk)    │ │           │
│  │  └──────────────┘  └──────────────┘  └────────────┘ │           │
│  └──────────────────────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                        RETRIEVAL (на каждый запрос)                  │
│                                                                     │
│  Вопрос ──▶ Embedder ──▶ DenseRetriever ──┐                        │
│       │                                   │                         │
│       └──▶ BM25Index ──▶ BM25 search ─────┤                         │
│                                            ▼                        │
│                                     HybridRetriever                 │
│                                     (RRF / Linear fusion)           │
│                                            │                        │
│                                            ▼                        │
│                                     List[HybridSearchResult]        │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                       GENERATION (на каждый запрос)                  │
│                                                                     │
│  Результаты ──▶ format_context() ──▶ build_rag_prompt()             │
│                                           │                         │
│                                           ▼                         │
│                                     LLM.chat()                      │
│                                           │                         │
│                                           ▼                         │
│                                     Verifier.verify()               │
│                                           │                         │
│                                     Ответ + Confidence              │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 1. Ingestion — загрузка и индексация

### 1.1 Парсинг Excel

**Файл:** [`src/core/excel/parser.py`](src/core/excel/parser.py) — класс `ExcelParser`

Процесс парсинга:

1. **Загрузка книги** через `openpyxl.load_workbook()` в режиме `data_only=True` (формулы → значения)
2. **Разделение объединённых ячеек** — метод [`_unmerge_cells()`](src/core/excel/parser.py:76):
   - Сохраняет значение верхней левой ячейки
   - Разъединяет диапазон
   - Заполняет все ячейки диапазона сохранённым значением
3. **Определение строк-заголовков** — метод [`_detect_header_rows()`](src/core/excel/parser.py:99):
   - Ищет первую строку с числовыми значениями в первой колонке
   - Если не находит — проверяет заполненность первых 5 колонок
   - Fallback: 3 строки заголовков
4. **Парсинг заголовков** — метод [`_parse_headers()`](src/core/excel/parser.py:152):
   - Собирает многоуровневые заголовки (если несколько строк)
   - Склеивает уровни через ` > ` (например, `"Цены > Медь > Руб/тн"`)
   - Очищает от телефонов, имён, спецсимволов через [`_clean_header_name()`](src/core/excel/parser.py:187)
   - Нормализует имя колонки: нижний регистр, пробелы → `_`, удаление спецсимволов
5. **Фильтрация пустых колонок** — метод [`_filter_empty_columns()`](src/core/excel/parser.py:119):
   - Удаляет колонки, где все значения (кроме заголовков) — `None`
6. **Сбор данных** — метод [`_parse_data()`](src/core/excel/parser.py:203):
   - Каждая строка → `Dict[col_name, value]`
   - Числа сохраняются как числа, остальное как строки
   - Пустые строки пропускаются
7. **Сбор ячеек** — метод [`_collect_cells()`](src/core/excel/parser.py:230):
   - Каждая непустая ячейка → `ParsedCell(row, col, value, col_name, sheet_name)`
8. **Хеш файла** — SHA256 первых 16 символов для дедупликации

**Результат:** [`ParsedFile`](src/core/excel/schemas.py:38) — Pydantic-модель со списком листов, данными и ячейками.

### 1.2 Нормализация

**Файл:** [`src/core/excel/normalize.py`](src/core/excel/normalize.py) — класс `ExcelNormalizer`

**Определение типа колонки** — метод [`infer_column_type()`](src/core/excel/normalize.py:51):

| Тип | Паттерны в имени | Пример |
|-----|-----------------|--------|
| `id` | `№`, `номер`, `id`, `код`, `артикул` | `№ п/п` |
| `price` | `цена`, `стоим`, `руб`, `usd`, `сумма` | `Цена руб/тн` |
| `date` | `дата`, `период`, `месяц`, `год` | `Дата поставки` |
| `number` | Все значения — числа | `10.5`, `42` |
| `text` | Всё остальное | `Наименование` |

**Нормализация значений** — метод [`normalize_value()`](src/core/excel/normalize.py:29):
- Для `number`/`price`: очищает пробелы, заменяет `,` на `.`, конвертирует в `float`
- Для `date`: пробует форматы `%Y-%m-%d`, `%d.%m.%Y`, `%d/%m/%Y`, `%Y/%m/%d`

**Подготовка для БД** — метод [`prepare_cell_for_db()`](src/core/excel/normalize.py:102):
- Разделяет значение на три поля: `value_text`, `value_number`, `value_date`
- Сохраняет оригинальное значение в `original_value`

### 1.3 Сохранение в БД

**Файл:** [`src/services/excel/repository.py`](src/services/excel/repository.py)

ORM-модели ([`src/core/db/models.py`](src/core/db/models.py)):

```
File (1) ──▶ Sheet (N) ──▶ ColumnMetadata (N)
                │
                └──▶ Cell (N)
```

- **File**: `id`, `filename`, `file_hash` (unique), `total_sheets`, `total_rows`, `total_cells`, `status`
- **Sheet**: `id`, `file_id` (FK), `sheet_index`, `original_name`, `normalized_name`, `description`, `row_count`, `col_count`
- **ColumnMetadata**: `id`, `sheet_id` (FK), `col_index`, `original_name`, `normalized_name`, `data_type`, `sample_values` (JSON)
- **Cell**: `id`, `sheet_id` (FK), `row_num`, `col_index`, `value_text`, `value_number`, `value_date`, `original_value`

### 1.4 Векторная индексация

**Файл:** [`src/services/rag/rag_service.py`](src/services/rag/rag_service.py) — метод [`build_index_for_file()`](src/services/rag/rag_service.py:148)

После сохранения данных в БД запускается индексация:

1. **Для каждого листа:**
   - Строится текстовая репрезентация: название, описание, список колонок, все строки данных
   - Текст разбивается на чанки (адаптивная стратегия)
   - Каждый чанк эмбеддится → сохраняется в `ChunkEmbedding`
   - Общий эмбеддинг листа → сохраняется в `SheetEmbedding`
   - Чанки добавляются в BM25-индекс

2. **Для каждой колонки:**
   - Строится текст: `"Колонка: {name}, тип: {type}, примеры: {samples}"`
   - Эмбеддится → сохраняется в `ColumnEmbedding`

3. **BM25-индекс** сохраняется на диск (`data/bm25_index.pkl`) при завершении сервера

Векторные модели ([`src/core/db/vector_models.py`](src/core/db/vector_models.py)):
- **ChunkEmbedding**: `sheet_id`, `chunk_index`, `source_text`, `embedding` (pgvector), `model_name`
- **SheetEmbedding**: `sheet_id`, `source_text`, `embedding`, `model_name`
- **ColumnEmbedding**: `column_id`, `source_text`, `embedding`, `model_name`
- **QueryEmbeddingCache**: `query_hash`, `query_text`, `embedding`, `model_name`

---

## 2. Retrieval — поиск

### 2.1 Chunking (разбивка на чанки)

**Файл:** [`src/services/rag/chunker.py`](src/services/rag/chunker.py)

Три стратегии:

| Стратегия | Функция | Параметры | Описание |
|-----------|---------|-----------|----------|
| `tokens` | [`chunk_by_tokens()`](src/services/rag/chunker.py:6) | `chunk_size=512`, `overlap=64` | Разбивка по словам с перекрытием |
| `sentences` | [`chunk_by_sentences()`](src/services/rag/chunker.py:31) | `max_sentences=8`, `overlap=1` | Разбивка по предложениям |
| `adaptive` | [`chunk_adaptive()`](src/services/rag/chunker.py:57) | `max_chars=1500`, `overlap=150` | Адаптивная: по абзацам |

**Адаптивная стратегия (по умолчанию):**
1. Разбивает текст по двойным переносам строк (абзацы)
2. Группирует абзацы, пока не превышен `max_chars`
3. Если абзац длиннее `max_chars` — разбивает его по предложениям
4. Добавляет перекрытие (overlap) между соседними чанками

### 2.2 Dense retrieval (плотный поиск)

**Файл:** [`src/services/rag/retrieval.py`](src/services/rag/retrieval.py) — класс `DenseRetriever`

**Процесс:**
1. Вопрос пользователя эмбеддится через [`Embedder.embed()`](src/services/rag/embedder.py:19)
2. Поиск по трём источникам с косинусной близостью (pgvector `<=>`):
   - **ChunkEmbedding** — наиболее точный (по строкам данных)
   - **SheetEmbedding** — общий контекст листа (fallback)
   - **ColumnEmbedding** — метаданные колонок
3. Дедупликация по `(source_type, source_id)` — остаётся запись с макс. score
4. Сортировка по убыванию score

**Embedder** ([`src/services/rag/embedder.py`](src/services/rag/embedder.py)):
- Использует fastembed (`intfloat/multilingual-e5-large`) локально на ONNX Runtime
- Кэширует эмбеддинги запросов в таблице `QueryEmbeddingCache` (по SHA256 хешу)
- Размерность: 1024 (настраивается через `EMBED_DIMENSION`)

### 2.3 Sparse retrieval (BM25)

**Файл:** [`src/services/rag/bm25.py`](src/services/rag/bm25.py) — класс `BM25Index`

**Реализация:** `rank_bm25.BM25Okapi`

**Токенизация:** [`_tokenize()`](src/services/rag/bm25.py:11):
- Нижний регистр
- Извлечение слов (`\w+`)
- Фильтр: длина > 1 символа

**Индекс:**
- Строится лениво при первом поиске
- Сохраняется на диск через `pickle`
- Поддерживает добавление новых чанков через [`add_chunks()`](src/services/rag/bm25.py:88) (с последующей перестройкой)

**Поиск:** [`search()`](src/services/rag/bm25.py:64):
- Токенизирует запрос
- Вычисляет BM25-оценки для всех документов
- Возвращает top_k с метаданными (`source_type`, `source_id`)

### 2.4 Гибридная фузия

**Файл:** [`src/services/rag/hybrid.py`](src/services/rag/hybrid.py) — класс `HybridRetriever`

Объединяет результаты dense и sparse поиска двумя методами:

#### RRF (Reciprocal Rank Fusion) — по умолчанию

```python
score = 1 / (k + rank)  # k = 60
```

- Каждому результату присваивается RRF-оценка на основе его позиции в ранжированном списке
- Оценки из BM25 и Dense суммируются для одинаковых документов
- Дедупликация по `(source_type, source_id)`

#### Linear fusion

```python
score = α * BM25_norm + (1 - α) * Dense_norm  # α = 0.3
```

- Оценки нормализуются через min-max нормализацию
- Взвешенная сумма с коэффициентом α

**Результат:** [`HybridSearchResult`](src/services/rag/hybrid.py:8):
```python
@dataclass
class HybridSearchResult:
    chunk: str          # Текст чанка
    score: float        # Итоговая оценка
    bm25_score: float   # Оценка BM25
    dense_score: float  # Оценка Dense
    rank: int           # Позиция в результатах
    source_type: str    # "chunk" / "sheet" / "column"
    source_id: int      # ID в БД
```

---

## 3. Generation — генерация ответа

**Файл:** [`src/services/generation/pipeline.py`](src/services/generation/pipeline.py) — класс `GenerationPipeline`

### 3.1 Форматирование контекста

**Файл:** [`src/services/generation/rag_prompt.py`](src/services/generation/rag_prompt.py) — функция [`format_context()`](src/services/generation/rag_prompt.py:29)

```python
def format_context(results: List[HybridSearchResult], max_chars: int = 48000) -> str:
```

Форматирует результаты поиска в текст для LLM:
```
[Источник 1] (релевантность: 0.892) | тип: chunk, id: 5
Лист: цвломна_дек25
строк: 150, колонок: 12
колонки: наименование_лома, среднерыночная_цена_рубтн, ...
данные (все колонки):
  строка 1: наименование_лома: Медь | среднерыночная_цена_рубтн: 8500
  ...
```

Ограничение: 48 000 символов (предотвращает превышение контекстного окна).

### 3.2 Промпт для LLM

**Файл:** [`src/services/generation/rag_prompt.py`](src/services/generation/rag_prompt.py) — функция [`build_rag_prompt()`](src/services/generation/rag_prompt.py:48)

**System prompt:**
```
Ты — ассистент по анализу Excel-данных ЕВРАЗ. Твоя задача — отвечать на вопросы
пользователя, используя ТОЛЬКО предоставленный контекст из базы данных Excel-файлов.

Правила:
1. Отвечай на русском языке, чётко и по делу.
2. Если контекста недостаточно для ответа — скажи об этом, не выдумывай.
3. Если вопрос требует расчёта — сделай расчёт на основе данных из контекста.
4. Ссылайся на конкретные листы, колонки и значения из контекста.
5. Не используй внешние знания — только то, что в контексте.
6. Если в контексте есть табличные данные — представь ответ в структурированном виде.
```

**User message:**
```
Вопрос пользователя:
{question}

Контекст из базы данных Excel:
{context}

Дай ответ на основе контекста.
```

### 3.3 Self-Correction

При повторном запросе (если в `conversation_history` есть предыдущие попытки) добавляется инструкция:

```
Дополнительная информация: это повторная попытка ответить на вопрос.
Предыдущая попытка не дала удовлетворительного результата.
Вот история предыдущих попыток:
{history}

Пожалуйста, проанализируй, почему предыдущий ответ мог быть неудовлетворительным,
и попробуй другой подход к ответу.
```

---

## 4. Verification — верификация

**Файл:** [`src/services/generation/verifier.py`](src/services/generation/verifier.py) — класс `Verifier`

Метод [`verify()`](src/services/generation/verifier.py:47) проверяет ответ LLM на галлюцинации:

### Проверка чисел
```python
numbers_in_response = re.findall(r"\b\d+(?:[.,]\d+)?", response)
for num in numbers_in_response:
    if num not in context_text and not _is_round_number(num):
        warnings.append(f"Число '{num}' из ответа не найдено в контексте")
```
Круглые числа (100, 1000, 10000, 100000, 1000000) не считаются галлюцинациями.

### Проверка сущностей
```python
entities = re.findall(r"\b[А-ЯA-Z][а-яa-z]*(?:\s+[А-ЯA-Z][а-яa-z]*)+", response)
for entity in entities:
    if entity.lower() not in context_text:
        warnings.append(f"Сущность '{entity}' из ответа не найдена в контексте")
```

### Покрытие (coverage)
```python
response_words = set(re.findall(r"\b[а-яa-z]{3,}\b", response.lower()))
covered = sum(1 for w in response_words if w in context)
coverage = covered / len(response_words)
```

### Уверенность (confidence)
```python
confidence = coverage - len(warnings) * 0.15
```

### Итог
```python
passed = len(warnings) == 0 and coverage >= 0.4
```

**Результат:** [`VerificationResult`](src/services/generation/verifier.py:8):
```python
@dataclass
class VerificationResult:
    passed: bool                    # Прошёл ли проверку
    score: float                    # Покрытие (0..1)
    hallucination_warnings: list    # Предупреждения о галлюцинациях
    missing_claims: list            # Отсутствующие утверждения
    confidence: float               # Итоговая уверенность
```

---

## 5. Полный цикл запроса

```python
# 1. Гибридный поиск
retrieved = await rag_service.hybrid_search(query=question, top_k=10)

# 2. Форматирование контекста
context = format_context(retrieved)

# 3. Построение промпта
messages = build_rag_prompt(question, context)

# 4. Вызов LLM
answer = await llm.chat(messages=messages)

# 5. Верификация
verification = verifier.verify(answer, retrieved)

# 6. Логирование в БД
await log_to_db(request_id, question, answer, retrieved, verification, latency_ms)
```

---

## Ключевые файлы

| Файл | Назначение |
|------|-----------|
| [`src/core/excel/parser.py`](src/core/excel/parser.py) | Парсинг Excel-файлов |
| [`src/core/excel/normalize.py`](src/core/excel/normalize.py) | Нормализация данных и определение типов |
| [`src/core/excel/schemas.py`](src/core/excel/schemas.py) | Pydantic-схемы для парсинга |
| [`src/core/db/models.py`](src/core/db/models.py) | ORM-модели (File, Sheet, ColumnMetadata, Cell) |
| [`src/core/db/vector_models.py`](src/core/db/vector_models.py) | Векторные модели (ChunkEmbedding, SheetEmbedding, ...) |
| [`src/services/excel/ingestion_service.py`](src/services/excel/ingestion_service.py) | Оркестратор загрузки файлов |
| [`src/services/excel/repository.py`](src/services/excel/repository.py) | Сохранение в БД |
| [`src/services/rag/rag_service.py`](src/services/rag/rag_service.py) | Оркестратор RAG |
| [`src/services/rag/chunker.py`](src/services/rag/chunker.py) | Разбивка на чанки |
| [`src/services/rag/embedder.py`](src/services/rag/embedder.py) | Эмбеддинги с кэшированием |
| [`src/services/rag/bm25.py`](src/services/rag/bm25.py) | BM25-индекс |
| [`src/services/rag/retrieval.py`](src/services/rag/retrieval.py) | Dense retrieval (pgvector) |
| [`src/services/rag/hybrid.py`](src/services/rag/hybrid.py) | Гибридный поиск (RRF / Linear) |
| [`src/services/generation/pipeline.py`](src/services/generation/pipeline.py) | GenerationPipeline |
| [`src/services/generation/rag_prompt.py`](src/services/generation/rag_prompt.py) | Промпты для RAG |
| [`src/services/generation/verifier.py`](src/services/generation/verifier.py) | Верификация ответов |
| [`src/services/llm/llm_client.py`](src/services/llm/llm_client.py) | OpenAI-совместимый LLM-клиент |