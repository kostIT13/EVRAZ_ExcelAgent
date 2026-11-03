from datetime import datetime
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field, field_validator


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
    period: Optional[str] = None
    sheet_kind: Optional[str] = None
    sheet_kind_auto: Optional[bool] = None
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
    role: Optional[str] = None

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



class ConversationTurn(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$", description="Роль: user или assistant")
    content: str = Field(..., description="Текст сообщения")


class AskRequest(BaseModel):

    question: str = Field(..., min_length=1, max_length=2000, description="Вопрос пользователя")
    top_k: int = Field(default=10, ge=1, le=50, description="Количество чанков для поиска")
    mode: str = Field(
        default="auto",
        pattern="^(auto|rag|agent)$",
        description="Режим: auto (автоопределение), rag (только RAG), agent (только агент)",
    )
    response_mode: str = Field(
        default="detailed",
        pattern="^(detailed|concise)$",
        description="Формат ответа: detailed (полный), concise (только число или слово)",
    )
    conversation_history: List[ConversationTurn] = Field(
        default_factory=list,
        description="История предыдущих попыток для self-correction",
    )
    conversation_id: Optional[str] = Field(
        default=None,
        description="ID диалога для сохранения памяти между вопросами",
    )


class WaitForInputInfo(BaseModel):

    question: str = Field(default="", description="Уточняющий вопрос от агента")
    options: List[str] = Field(default_factory=list, description="Варианты ответа для уточнения")


class AskResumeRequest(BaseModel):

    thread_id: str = Field(..., min_length=1, description="ID прерванного диалога (thread_id из /ask)")
    user_answer: str = Field(..., min_length=1, max_length=2000, description="Ответ пользователя на уточняющий вопрос")
    response_mode: str = Field(
        default="detailed",
        pattern="^(detailed|concise)$",
        description="Формат ответа: detailed/concise",
    )


class SourceInfo(BaseModel):

    chunk: str = Field(..., description="Текст чанка")
    score: float = Field(..., description="Релевантность")
    source_type: str = Field(default="unknown", description="Тип источника: sheet / column")
    source_id: int = Field(default=0, description="ID источника в БД")
    rank: int = Field(default=0, description="Позиция в результатах")


class AskResponse(BaseModel):

    answer: str = Field(..., description="Сгенерированный ответ")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Уверенность в ответе (0-1)")
    sources: List[SourceInfo] = Field(default_factory=list, description="Источники, использованные для ответа")
    request_id: str = Field(..., description="Уникальный ID запроса")
    latency_ms: int = Field(..., description="Время выполнения в миллисекундах")
    mode_used: str = Field(default="rag", description="Какой режим использовался: rag/agent")
    response_mode: str = Field(default="detailed", description="Формат ответа: detailed/concise")
    query_type: str = Field(default="", description="Тип запроса (только для agent): lookup/aggregate/cross_sheet/delta")
    sql_query: str = Field(default="", description="Сгенерированный SQL (только для agent)")
    sql_result_preview: List[Any] = Field(default_factory=list, description="Первые строки результата (только для agent)")
    retry_count: int = Field(default=0, description="Количество retry (только для agent)")
    status: str = Field(default="success", description="Статус: success/low_confidence/failed/waiting_for_input")
    self_corrected: bool = Field(default=False, description="Был ли применён self-correction")
    from_cache: bool = Field(
        default=False,
        description="Ответ взят из кэша запросов (SQL не перевыполнялся, LLM не вызывался)",
    )
    thread_id: Optional[str] = Field(
        default=None,
        description="Идентификатор диалога (thread_id) для продолжения через /ask/resume",
    )
    waiting_question: Optional[WaitForInputInfo] = Field(
        default=None,
        description="Уточняющий вопрос, когда status=waiting_for_input",
    )
    chart_available: bool = Field(
        default=False,
        description="Доступна ли кнопка «Сделай график»",
    )
    chart_data: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Данные графика [{period, value}, ...], если ответ уже временной ряд",
    )
    chart_type: Optional[str] = Field(
        default=None,
        pattern="^(line|bar)$",
        description="Тип графика из запроса пользователя: line (линейный) / bar (столбчатая)",
    )


class ChartRequest(BaseModel):
    thread_id: str = Field(..., min_length=1, description="ID диалога (thread_id из /ask)")


class ChartResponse(BaseModel):
    thread_id: str = Field(..., description="ID диалога")
    chart_available: bool = Field(default=False, description="Удалось построить график")
    chart_data: List[Dict[str, Any]] = Field(default_factory=list, description="Точки ряда [{period, value}]")
    message: str = Field(default="", description="Сообщение об ошибке, если график не построен")


class TraceStepInfo(BaseModel):
    step: str = Field(..., description="Название шага")
    data: Any = Field(default=None, description="Данные шага")


class TraceResponse(BaseModel):
    request_id: str = Field(..., description="Уникальный ID запроса")
    question: str = Field(default="", description="Вопрос пользователя")
    answer: str = Field(default="", description="Ответ")
    status: str = Field(default="", description="Статус выполнения")
    latency_ms: int = Field(default=0, description="Время выполнения")
    trace: Dict[str, Any] = Field(default_factory=dict, description="Полный trace всех шагов")
    steps: List[TraceStepInfo] = Field(default_factory=list, description="Шаги для отображения")
    confidence: float = Field(default=0.0, description="Уверенность ответа 0-1")
    confidence_source: str = Field(
        default="unknown",
        description="Откуда взята уверенность: result / verifier / unknown",
    )
    sql_query: str = Field(default="", description="Выполненный SQL")
    query_type: str = Field(default="", description="Тип запроса: lookup/aggregate/delta/…")
    retry_count: int = Field(default=0, description="Число повторов генерации/проверки")
    error_message: str = Field(default="", description="Текст ошибки, если запрос упал")
    from_cache: bool = Field(default=False, description="Ответ взят из кэша")
    created_at: Optional[str] = Field(default=None, description="Время запроса (ISO)")


class TraceListResponse(BaseModel):
    items: List[Dict[str, Any]] = Field(default_factory=list, description="Страница трейсов")
    total: int = Field(default=0, description="Всего записей под фильтры")
    limit: int = Field(default=20, description="Размер страницы")
    offset: int = Field(default=0, description="Смещение страницы")


class LLMConfigResponse(BaseModel):
    """Текущая конфигурация LLM, которую использует бэкенд."""
    model: str = Field(..., description="Имя основной LLM-модели (LLM_MODEL_PRIMARY)")
    base_url: str = Field(..., description="Базовый URL LLM-провайдера")
    temperature: float = Field(..., description="Температура по умолчанию (LLM_TEMPERATURE)")
    max_tokens: int = Field(..., description="Лимит токенов на ответ (LLM_MAX_TOKENS)")
    request_timeout_s: int = Field(..., description="Таймаут запроса к LLM, сек")
    llm_max_retries: int = Field(
        ..., description="HTTP-retry на уровне клиента LLM (MAX_RETRIES)"
    )
    graph_max_retry_count: int = Field(
        ...,
        description="Максимум graph-level retry кодогенерации/проверки (MAX_RETRY_COUNT)",
    )
    max_codegen_attempts: int = Field(
        ...,
        description="Максимум попыток генерации SQL внутри codegen-ноды",
    )


class LLMModelsResponse(BaseModel):
    """Модели, отданные LLM-прокси, плюс текущая модель и значение из .env."""

    models: List[str] = Field(default_factory=list, description="Идентификаторы моделей на прокси")
    current: str = Field(..., description="Модель, которой сервис отвечает прямо сейчас")
    default: str = Field(..., description="LLM_MODEL_PRIMARY из .env — куда возвращает сброс")
    listed: bool = Field(
        default=True, description="Прокси отдал список; false — только ручной ввод имени"
    )
    error: str = Field(default="", description="Почему список моделей недоступен")


class LLMModelSwitchRequest(BaseModel):
    model: str = Field(
        ..., min_length=1, max_length=200, description="Идентификатор целевой модели"
    )
    verify: bool = Field(
        default=True,
        description="Сначала получить ответ модели-кандидата; при ошибке модель не меняется",
    )

    @field_validator("model")
    @classmethod
    def _clean_model(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("model must not be blank")
        if any(ord(c) < 32 for c in cleaned):
            raise ValueError("model must not contain control characters")
        return cleaned


class LLMModelSwitchResponse(BaseModel):
    previous: str = Field(..., description="Модель до переключения")
    current: str = Field(..., description="Модель после переключения")
    default: str = Field(..., description="LLM_MODEL_PRIMARY из .env")
    changed: bool = Field(..., description="Значение действительно сменилось")
    verified: bool = Field(
        default=False, description="Модель ответила на проверочный вызов до переключения"
    )
    probe_ms: int = Field(default=0, description="Длительность проверочного вызова, мс")
    note: str = Field(default="", description="Как долго действует переключение")
