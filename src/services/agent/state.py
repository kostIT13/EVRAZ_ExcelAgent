#"""Agent State - единый dataclass, проходящий через все шаги state machine"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

class QueryType(str, Enum):
    """Тип запроса, определяемый Classifier"""
    LOOKUP = "lookup"
    """Простой поиск значения ('какая цена на медь в январ')"""
    
    AGGREGATE = "aggregate"
    """Агрегатный запрос (сумма, среднее, минимум)"""
    
    CROSS_SHEET = "cross_sheet"
    """Сравнение между разными листами/месяцами"""
    
    DELTA = "delta"
    """Разница между значениями во времени"""
    
    UNKNOWN = "unknown"
    """Classifier не смог определить тип"""
    
class AgentStep(str, Enum):
    """Текущий шаг агента (state machine)"""
    CLASSIFIER = "classifier"
    PLANNER = "planner"
    CODEGEN = "codegen"
    VALIDATOR = "validator"
    EXECUTOR = "executor"
    VERIFIER = "verifier"
    DONE = "done"
    FAILED = "failed"
    
@dataclass
class AgentState:
    """Состояние агента, которое проходит через все шаги
    Каждый шаг читает поля из входа и пишет в соответствующие поля выхода
    """
    # Вход
    question: str
    """Исходный вопрос пользователя"""
    
    # Classifier output
    query_type: QueryType = QueryType.UNKNOWN
    """Тип запроса, определенный Classifier"""
    
    entities: List[str] = field(default_factory=list)
    """Сущности, извлеченные из вопроса (например, ['медь', 'январь 2025'])"""
    
    relevant_sheets: List[Dict[str, Any]] = field(default_factory=list)
    """Список релевантных листов: [{'id': 1, 'name': 'январь', 'description': '...'}, ...]."""
    
    plan: str = ""
    """Текстовый план действий, сгенерированный Planner"""
    
    sql_query: str = ""
    """SQL-запрос, сгенерированный CodeGen"""
    
    validation_errors: List[str] = field(default_factory=list)
    """Ошибки валидации SQL (пустой список = валидация пройдена)"""
    
    sql_result: List[Dict[str, Any]] = field(default_factory=list)
    """Результат выполнения SQL-запроса"""
    
    sql_error: Optional[str] = None
    """Ошибка выполнения SQL"""
    
    answer: str = ""
    """Финальный ответ пользователю"""
    
    confidence: float = 0.0
    """Уверенность в ответе (от 0 до 1)"""
    
    retry_count: int = 0
    """Счетчик retry (Verifier -> CodeGen)"""
    
    trace: Dict[str, Any] = field(default_factory=dict)
    """Полный след каждого шага для endpoint /trace/{request_id}."""
    
    current_step: AgentStep = AgentStep.CLASSIFIER
    """Текущий шаг в state machine."""
    
    request_id: str = ""
    """UUID запрос"""
    
    def to_dict(self) -> Dict[str, Any]:
        """Сериализация в dict для логирования и traceability"""
        return {
            "question": self.question,
            "query_type": self.query_type.value,
            "entities": self.entities,
            "relevant_sheets": self.relevant_sheets,
            "plan": self.plan,
            "sql_query": self.sql_query,
            "validation_errors": self.validation_errors,
            "sql_result": self.sql_result,
            "sql_error": self.sql_error,
            "answer": self.answer,
            "confidence": self.confidence,
            "retry_count": self.retry_count,
            "current_step": self.current_step.value,
            "request_id": self.request_id
        }
    
    