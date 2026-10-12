# Диаграммы проекта (Mermaid)

Диаграммы в формате [Mermaid](https://mermaid.js.org/). Рендерятся в VS Code
(расширение «Mermaid»/«Markdown Preview Mermaid Support»), на GitHub и в MkDocs.

## Файлы `.mmd` (чистый Mermaid-код)

| Файл | Тип | Что показывает |
|---|---|---|
| [`architecture.mmd`](architecture.mmd) | flowchart | Общая архитектура системы (frontend/backend/БД/LLM/мониторинг) |
| [`excel_ingestion.mmd`](excel_ingestion.mmd) | flowchart | Пайплайн парсинга/нормализации Excel (RAW + mart) |
| [`excel_ingestion_sequence.mmd`](excel_ingestion_sequence.mmd) | sequence | Последовательность инжеста файла |
| [`agent_pipeline.mmd`](agent_pipeline.mmd) | flowchart | Граф LLM-агента на LangGraph (узлы, ретраи) |
| [`agent_status.mmd`](agent_status.mmd) | flowchart | Статусы результата по `confidence` |
| [`database_schema.mmd`](database_schema.mmd) | erDiagram | ER-диаграмма схем `public` и `mart` |
| [`ci_cd.mmd`](ci_cd.mmd) | flowchart | GitHub Actions: unit / integration / golden |
| [`ci_cd_sequence.mmd`](ci_cd_sequence.mmd) | sequence | Выполнение CI-джоб во времени |
| [`deployment.mmd`](deployment.mmd) | flowchart | Топология Docker Compose |

## Файлы `.md` (диаграмма + пояснения)

Те же диаграммы с контекстом и таблицами:

- [`architecture.md`](architecture.md)
- [`excel_ingestion.md`](excel_ingestion.md)
- [`agent_pipeline.md`](agent_pipeline.md)
- [`database_schema.md`](database_schema.md)
- [`ci_cd.md`](ci_cd.md)
- [`deployment.md`](deployment.md)

## Рендер

```bash
# mermaid-cli
npx -y @mermaid-js/mermaid-cli -i diagrams/architecture.mmd -o diagrams/architecture.svg