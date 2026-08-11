"""Schema Inference — LLM-распознавание структуры разнородных таблиц.

Проблема: жёсткие эвристики normalize.py не покрывают сдвинутые шапки,
вложенные заголовки, слитые ячейки и "мусорные" числовые артефакты. Этот модуль
передаёт сырую сетку ячеек листа (координаты + значения, первые ~30 строк) LLM
и получает структурированную схему с Pydantic-валидацией.

Схема применяется только после подтверждения пользователем (status=confirmed в
mart.sheet_templates), либо используется как fallback-подсказка для агента.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from src.core.logging_settings import logger
from src.services.llm.llm_client import LLMClient


class ColumnInference(BaseModel):
    col_index: int = Field(..., description="Индекс колонки (0-based)")
    name: str = Field(..., description="Короткое имя колонки")
    path: List[str] = Field(default_factory=list, description="Путь вложенных заголовков (для многострочной шапки)")


class SheetSchema(BaseModel):
    header_rows: List[int] = Field(default_factory=list, description="Номера строк заголовка (1-based)")
    data_start_row: int = Field(..., description="Строка, с которой начинаются данные")
    columns: List[ColumnInference] = Field(default_factory=list, description="Распознанные колонки")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="Уверенность распознавания 0-1")
    notes: str = Field("", description="Заметки о структуре")


def serialize_cells_grid(cells: Dict[str, Any], max_rows: int = 30) -> str:
    """Сериализует сырую сетку ячеек для LLM (координата → значение)."""
    lines = []
    for coord in sorted(cells.keys()):
        row_num = _row_index(coord)
        if row_num <= max_rows:
            lines.append(f"{coord}: {cells[coord]}")
    return "\n".join(lines)


def _row_index(coord: str) -> int:
    digits = "".join(ch for ch in coord if ch.isdigit())
    try:
        return int(digits)
    except ValueError:
        return 0


class SchemaInferenceService:
    """Вызывает LLM для распознавания структуры листа."""

    SYSTEM_PROMPT = """Ты — эксперт по распознаванию структуры Excel-таблиц.
Получаешь сырую сетку ячеек (координата: значение). Определи:
- какие строки — заголовки (могут быть многострочными/вложенными),
- с какой строки начинаются данные,
- какие колонки есть и как они называются (включая путь вложенных заголовков),
- насколько уверен в распознавании (0-1).

Не выдумывай значения. Возвращай строго JSON по схеме.
"""

    def __init__(self, llm: Optional[LLMClient] = None) -> None:
        self._llm = llm or LLMClient()

    async def infer(
        self,
        cells_grid: str,
        sheet_name: str,
    ) -> SheetSchema:
        user_prompt = (
            f"Лист: {sheet_name}\n"
            f"Сырые ячейки (первые строки):\n{cells_grid}\n\n"
            "Распознай схему листа и верни JSON."
        )
        try:
            # parse_structured — модульная функция из llm_client, а не метод LLMClient.
            from src.services.llm.llm_client import parse_structured

            schema = await parse_structured(
                self._llm,
                user_prompt,
                SheetSchema,
                system_prompt=self.SYSTEM_PROMPT,
                temperature=0.0,
            )
            return schema
        except Exception as exc:
            logger.error("SchemaInference failed: {}", exc)
            return SheetSchema(
                data_start_row=1,
                columns=[],
                confidence=0.0,
                notes=f"Ошибка распознавания: {exc}",
            )


# Singleton
schema_inference_service = SchemaInferenceService()