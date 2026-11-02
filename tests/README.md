# Тесты

Проект использует `pytest`. Тесты разделены на три уровня:

| Уровень | Маркер | Требования | Команда |
|---|---|---|---|
| Юнит | — | нет | `pytest tests/ -m "not golden and not integration"` |
| Интеграционные | `integration` | PostgreSQL + `TEST_POSTGRES_URL` | `pytest tests/integration -m integration` |
| Golden (LLM) | `golden` | LLM-модель + загруженные данные | `pytest -m golden tests/test_golden_dataset.py` |

## Юнит-тесты

### Пайплайн первой таблицы

Покрывают пайплайн обработки первой таблицы
([`data/data_proportional_prices.xlsx`](../data/data_proportional_prices.xlsx)):

- [`test_price_sheet_parser.py`](test_price_sheet_parser.py) — парсинг: листы,
  шапка, колонки, строки данных, период, тип листа;
- [`test_price_sheet_structurer.py`](test_price_sheet_structurer.py) — извлечение
  фактов цен (среднерыночная / аукцион / поставщики);
- [`test_price_sheet_normalize.py`](test_price_sheet_normalize.py) — нормализация
  значений и типов колонок;
- [`test_sheet_kind_detector_domain.py`](test_sheet_kind_detector_domain.py) —
  детектор типа листа (prices / matrix / generic).

### Backend: API, агент, конфигурация

- [`test_api_schemas.py`](test_api_schemas.py) — Pydantic-схемы запросов/ответов API;
- [`test_api_security.py`](test_api_security.py) — API-key auth и rate limiting;
- [`test_config.py`](test_config.py) — конфигурация (`Settings`, `.env`);
- [`test_sql_compiler.py`](test_sql_compiler.py) / [`test_sql_compiler_extra.py`](test_sql_compiler_extra.py) —
  безопасный компилятор SQL;
- [`test_codegen_helpers.py`](test_codegen_helpers.py) — детерминированные правки SQL в codegen;
- [`test_structured_schemas.py`](test_structured_schemas.py) — схемы структурированного вывода LLM;
- [`test_agent_helpers.py`](test_agent_helpers.py) — вспомогательные функции агента
  (графики, извлечение фильтров);
- [`test_chart_intent.py`](test_chart_intent.py) — детект запроса графика и SQL для timeseries;
- [`test_classifier_domain.py`](test_classifier_domain.py) — классификатор доменов;
- [`test_entity_resolver_helpers.py`](test_entity_resolver_helpers.py) — утилиты
  fuzzy-резолвера сущностей;
- [`test_query_cache.py`](test_query_cache.py) — кэш запросов;
- [`test_material_synonyms.py`](test_material_synonyms.py) — синонимы материалов;
- [`test_normalizer_dimension.py`](test_normalizer_dimension.py) — нормализация измерений;
- [`test_parser_header_detection.py`](test_parser_header_detection.py) — определение шапки Excel;
- [`test_benchmark_extract.py`](test_benchmark_extract.py) — извлечение чисел для метрики бенчмарка;
- [`test_infra_helpers.py`](test_infra_helpers.py) — инфраструктурные утилиты (checkpointer и др.).

Запуск:

```bash
pytest tests/ -m "not golden and not integration" -v
```

## Интеграционные тесты

Проверяют полный путь инжеста первой таблицы в реальную PostgreSQL:
`ExcelParser → SQLAlchemyExcelRepository (files/sheets/columns/cells) →
normalize_file_to_mart (mart.price_facts / supplier_aliases) → индексация сущностей`.

Для запуска нужна переменная окружения `TEST_POSTGRES_URL` (отдельная тестовая БД —
фикстура создаёт схему `mart` и все таблицы, а в конце удаляет их):

```bash
# пример для локального docker-compose postgres
TEST_POSTGRES_URL=postgresql+asyncpg://evraz:evraz_secret@localhost:5432/evraz_test \
  pytest tests/integration -m integration -v
```

Без `TEST_POSTGRES_URL` интеграционные тесты пропускаются на этапе сбора.

## Golden-тесты

Требуют живую LLM-модель и загруженные данные. В CI не запускаются — только локально.

## CI

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) — юнит-тесты и
интеграционные тесты с service-контейнером PostgreSQL (без LLM).