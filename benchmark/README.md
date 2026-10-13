# Бенчмарк запросов

Прогон запросов из [`docs/request_examples.txt`](../docs/request_examples.txt) через
API агента с метрикой точности (pass rate). Сравнение ответов выполняется
**только по числу**: из ответа модели и из эталона извлекается первое число и
сравнивается с относительным допуском (по умолчанию 1%).

## Скрипты

| Скрипт | Что делает |
|---|---|
| [`run_first6.py`](run_first6.py) | Прогон **первых 6** запросов из `docs/request_examples.txt` |
| [`run_all.py`](run_all.py) | Прогон **всех** запросов из `docs/request_examples.txt` |

## Требования

- Запущенный сервер API: `uvicorn src.main:app` (или `docker compose up`).
- Данные загружены в PostgreSQL: `python scripts/load_demo_data.py`.
- Если сервер запущен с `API_KEY`, передайте его через `--api-key` или
  переменную окружения `API_KEY`.

## Запуск

```bash
# первые 6 запросов
python benchmark/run_first6.py

# все запросы
python benchmark/run_all.py

# все запросы с большим top_k и своим JSON-отчётом
python benchmark/run_all.py --top-k 20 --json benchmark/results.json

# только первые 10 запросов
python benchmark/run_all.py --limit 10

# другой адрес сервера
python benchmark/run_first6.py --base-url http://localhost:8000
```

## Как считается метрика

1. Из эталонного ответа извлекается первое число.
2. Из ответа модели извлекается первое число.
3. Ответ считается верным, если относительная разница ≤ допуска
   (`--tolerance`, по умолчанию 1%).
4. Вопросы без числового эталона (например, «В каком месяце…») пропускаются
   и не влияют на pass rate.

В конце выводится сводка:

```
BENCHMARK REPORT
Всего: 25 | Прошло: 18 | Провалено: 5 | Пропущено (нечисловые): 2
PASS RATE (по числовым ответам): 78.3% (18/23)
```

JSON-отчёт по умолчанию сохраняется в `benchmark/results_first6.json` или
`benchmark/results_all.json`.

## Известные особенности

В `docs/request_examples.txt` для части вопросов строка «Ответ:» содержит
первичный ответ модели, а в примечаниях — исправленное значение. Для честной
метрики в [`benchmark_core.py`](benchmark_core.py) задан список
`EXPECTED_OVERRIDES` с исправленными эталонами (вопросы про дельту,
рост/падение цены, сумму баббита и среднюю по проводу).

Самопроверка парсинга:

```bash
python benchmark/benchmark_core.py