from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class ClassifierResult(BaseModel):

    query_type: str = Field(description="lookup/aggregate/cross_sheet/delta/sum_by_supplier/find_period/unknown")
    domain: str = Field(default="generic", description="prices/metrics/generic")
    entities: List[str] = Field(default_factory=list, description="Сущности, извлечённые из вопроса")
    relevant_sheet_ids: List[int] = Field(default_factory=list, description="ID релевантных листов")

    # Flash-модели в json_mode иногда возвращают null для массивов, когда они пусты.
    @field_validator("entities", "relevant_sheet_ids", mode="before")
    @classmethod
    def _coerce_null_lists(cls, v):
        return [] if v is None else v


class DisambiguationResult(BaseModel):

    needs_disambiguation: bool = Field(default=False, description="Нужно ли уточнение")
    ambiguity_type: Optional[str] = Field(
        default=None,
        description="price_source/item_type/period/multiple_periods/multiple_items",
    )
    clarifying_question: str = Field(default="", description="Вопрос для уточнения")
    options: List[str] = Field(default_factory=list, description="Варианты для уточнения")
    suggested_resolution: Optional[str] = Field(
        default=None,
        description="Автоматическое разрешение неоднозначности, если возможно",
    )

    # Когда needs_disambiguation=false, модель часто заполняет поля null —
    # строгая валидация str/list на None падает. Приводим None к дефолтам.
    @field_validator("clarifying_question", mode="before")
    @classmethod
    def _coerce_null_str(cls, v):
        return "" if v is None else v

    @field_validator("options", mode="before")
    @classmethod
    def _coerce_null_list(cls, v):
        return [] if v is None else v


class PlannerResult(BaseModel):

    plan: str = Field(description="План действий для генерации SQL-запроса")

    @field_validator("plan", mode="before")
    @classmethod
    def _coerce_null_plan(cls, v):
        return "" if v is None else v


class VerifierResult(BaseModel):

    is_correct: bool = Field(default=True, description="Правильно ли SQL отвечает на вопрос")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="Уверенность 0..1")
    issues: List[str] = Field(default_factory=list, description="Найденные проблемы (если есть)")
    needs_retry: bool = Field(default=False, description="Нужно ли перегенерировать SQL")
    retry_reason: Optional[str] = Field(
        default=None,
        description="Причина retry (wrong_table/wrong_column/wrong_aggregation/...)",
    )

    @field_validator("issues", mode="before")
    @classmethod
    def _coerce_null_issues(cls, v):
        return [] if v is None else v

    @field_validator("retry_reason", mode="before")
    @classmethod
    def _coerce_null_reason(cls, v):
        return "" if v is None else v