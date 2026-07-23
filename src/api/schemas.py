from datetime import datetime
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


class FileResponse(BaseModel):
    id: int
    filename: str
    file_hash: str
    total_sheets: int
    total_rows: int
    total_cells: int
    uploaded_at: datetime
    processed_at: Optional[datetime] = None
    status: str
    error_message: Optional[str] = None

    model_config = {"from_attributes": True}


class FileListResponse(BaseModel):
    files: List[FileResponse]
    total: int



class SheetResponse(BaseModel):
    id: int
    file_id: int
    sheet_index: int
    original_name: str
    normalized_name: str
    description: Optional[str] = None
    row_count: int
    col_count: int
    created_at: datetime

    model_config = {"from_attributes": True}



class ColumnResponse(BaseModel):
    id: int
    sheet_id: int
    col_index: int
    original_name: str
    normalized_name: str
    data_type: str
    description: Optional[str] = None
    sample_values: Optional[List[Any]] = None

    model_config = {"from_attributes": True}


class CellResponse(BaseModel):
    id: int
    sheet_id: int
    row_num: int
    col_index: int
    value_text: Optional[str] = None
    value_number: Optional[float] = None
    value_date: Optional[datetime] = None
    original_value: Optional[str] = None

    model_config = {"from_attributes": True}



class FileDetailResponse(FileResponse):
    sheets: List[SheetResponse] = Field(default_factory=list)


class SheetDetailResponse(SheetResponse):
    columns: List[ColumnResponse] = Field(default_factory=list)



class UploadResponse(BaseModel):
    message: str
    file: FileResponse


class ErrorResponse(BaseModel):
    detail: str
    error_code: Optional[str] = None


# ---------------------------------------------------------------------------
# RAG / Ask schemas
# ---------------------------------------------------------------------------


class AskRequest(BaseModel):
    """Request body for the RAG question-answering endpoint."""

    question: str = Field(..., min_length=1, max_length=2000, description="Вопрос пользователя")
    top_k: int = Field(default=10, ge=1, le=50, description="Количество чанков для поиска")
    mode: str = Field(
        default="auto",
        pattern="^(auto|rag|agent)$",
        description="Режим: auto (автоопределение), rag (только RAG), agent (только агент)",
    )


class SourceInfo(BaseModel):
    """Single retrieved source chunk."""

    chunk: str = Field(..., description="Текст чанка")
    score: float = Field(..., description="Релевантность")
    source_type: str = Field(default="unknown", description="Тип источника: sheet / column")
    source_id: int = Field(default=0, description="ID источника в БД")
    rank: int = Field(default=0, description="Позиция в результатах")


class AskResponse(BaseModel):
    """Response from the pipeline."""

    answer: str = Field(..., description="Сгенерированный ответ")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Уверенность в ответе (0-1)")
    sources: List[SourceInfo] = Field(default_factory=list, description="Источники, использованные для ответа")
    request_id: str = Field(..., description="Уникальный ID запроса")
    latency_ms: int = Field(..., description="Время выполнения в миллисекундах")
    # Поля агента (опциональные)
    mode_used: str = Field(default="rag", description="Какой режим использовался: rag/agent")
    query_type: str = Field(default="", description="Тип запроса (только для agent): lookup/aggregate/cross_sheet/delta")
    sql_query: str = Field(default="", description="Сгенерированный SQL (только для agent)")
    sql_result_preview: List[Any] = Field(default_factory=list, description="Первые строки результата (только для agent)")
    retry_count: int = Field(default=0, description="Количество retry (только для agent)")
    status: str = Field(default="success", description="Статус: success/low_confidence/failed")


# След

class TraceStepInfo(BaseModel):
    """Информация об одном шаге traceability."""
    step: str = Field(..., description="Название шага")
    data: Any = Field(default=None, description="Данные шага")


class TraceResponse(BaseModel):
    """Response from the traceability endpoint."""
    request_id: str = Field(..., description="Уникальный ID запроса")
    question: str = Field(default="", description="Вопрос пользователя")
    answer: str = Field(default="", description="Ответ")
    status: str = Field(default="", description="Статус выполнения")
    latency_ms: int = Field(default=0, description="Время выполнения")
    trace: Dict[str, Any] = Field(default_factory=dict, description="Полный trace всех шагов")
    steps: List[TraceStepInfo] = Field(default_factory=list, description="Шаги для отображения")
