# Тесты

Проект использует `pytest`. Тесты разделены на три уровня:

| Уровень | Маркер | Требования | Команда |
|---|---|---|---|
| Юнит | — | нет | `pytest tests/ -m "not golden and not integration"` |
| Интеграционные | `integration` | PostgreSQL + `TEST_POSTGRES_URL` | `pytest tests/integration -m integration` |
| Golden (LLM) | `golden` | LLM-модель + загруженные данные | `pytest -m golden tests/test_golden_dataset.py` |

## Юнит-тесты

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