
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field


class ClassifierResult(BaseModel):

    query_type: str = Field(description="lookup/aggregate/cross_sheet/delta/sum_by_supplier/find_period/unknown")
    domain: str = Field(default="generic", description="prices/metrics/generic")
    entities: List[str] = Field(default_factory=list, description="Сущности, извлечённые из вопроса")
    relevant_sheet_ids: List[int] = Field(default_factory=list, description="ID релевантных листов")


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


class PlannerResult(BaseModel):

    plan: str = Field(description="План действий для генерации SQL-запроса")