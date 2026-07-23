# """Что делает Orchestrator:

# Создаёт AgentState с вопросом пользователя
# Запускает цикл: вызывает шаги по очереди согласно state.current_step
# Обрабатывает retry (Verifier → CodeGen)
# Обрабатывает ошибки на каждом шаге
# Возвращает финальный результат
# """

# """Orchestrator — state machine, управляющая всеми шагами агента.

# Цепочка: Classifier → Planner → CodeGen → Validator → Executor → Verifier → Done
#                               ↑                                    |
#                               └────────── retry (max 3) ───────────┘
# """

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.core.logging_settings import logger
from src.services.agent.state import AgentState, AgentStep
from src.services.agent.classifier import classifier_step
from src.services.agent.planner import planner_step
from src.services.agent.codegen import codegen_step
from src.services.agent.executor import executor_step
from src.services.agent.verifier import verifier_step
from src.services.llm.llm_client import LLMClient


@dataclass
class AgentResult:
    """Результат работы агента"""
    
    answer: str
    confidence: float
    request_id: str
    latency_ms: int
    trace: Dict[str, Any]
    query_type: str
    sql_query: str
    sql_result: List[Dict[str, Any]]
    retry_count: int
    status: str  # "success", "low_confidence", "failed"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "answer": self.answer,
            "confidence": self.confidence,
            "request_id": self.request_id,
            "latency_ms": self.latency_ms,
            "trace": self.trace,
            "query_type": self.query_type,
            "sql_query": self.sql_query,
            "sql_result": self.sql_result[:5],  # только первые 5 строк
            "retry_count": self.retry_count,
            "status": self.status,
        }
        
        
class AgentOrchestrator:
    """Оркестратор агента - state machine
    
    Управляет последовательностью шагов и retry-циклом
    """
    
    def __init__(self, llm: Optional[LLMClient] = None) -> None:
        self._llm = llm or LLMClient()
        
    async def run(self, question: str) -> AgentResult:
        """Запустить агента для ответа на вопрос
        
        Args:
            question: Вопрос пользователя.

        Returns:
            AgentResult с ответом и полным trace.
        """
        request_id = str(uuid.uuid4())
        start_time = time.monotonic()
        
        logger.info(
            "Agent [{}]: starting pipeline for '{}'",
            request_id[:8],
            question[:80],
        )
        
        # 1. Создаем начальное состояние
        state = AgentState(
            question=question,
            request_id=request_id
        )
        
        # 2. Запускаем state machine
        max_iterations = 20
        iteration = 0
        
        while state.current_step != AgentStep.DONE and state.current_step != AgentStep.FAILED:
            iteration += 1
            if iteration > max_iterations:
                logger.error(
                    "Agent [{}]: max iterations reached ({})",
                    request_id[:8],
                    max_iterations,
                )
                state.current_step = AgentStep.FAILED
                break
            
            step_name = state.current_step.value
            logger.info(
                "Agent [{}]: step {}/{} → {}",
                request_id[:8],
                iteration,
                max_iterations,
                step_name,
            )
            
            try:
                if state.current_step == AgentStep.CLASSIFIER:
                    state = await classifier_step(state, self._llm)

                elif state.current_step == AgentStep.PLANNER:
                    state = await planner_step(state, self._llm)

                elif state.current_step == AgentStep.CODEGEN:
                    state = await codegen_step(state, self._llm)

                elif state.current_step == AgentStep.EXECUTOR:
                    state = await executor_step(state)

                elif state.current_step == AgentStep.VERIFIER:
                    state = await verifier_step(state, self._llm)

                else:
                    logger.warning(
                        "Agent [{}]: unknown step '{}'",
                        request_id[:8],
                        state.current_step,
                    )
                    state.current_step = AgentStep.FAILED
                    break
                
            except Exception as exc:
                logger.error(
                    "Agent [{}]: step '{}' failed: {}",
                    request_id[:8],
                    step_name,
                    exc,
                )
                state.trace[step_name] = {
                    "error": str(exc),
                    "step_failed": True,
                }
                state.current_step = AgentStep.FAILED
                break
            
        # 3. Формируем наш результат
        latency_ms = int((time.monotonic() - start_time) * 1000)
        
        # Определяем наш статус
        if state.current_step == AgentStep.DONE:
            if state.confidence >= 0.7:
                status = "success"
            elif state.confidence >= 0.3:
                status = "low_confidence"
            else:
                status = "low_confidence"
        else:
            status = "failed"
            
        # Если ответ пустой - формируем fallback
        if not state.answer:
            if state.sql_result:
                state.answer = (
                    "Получены данные, но не удалосб сформировать ответ. "
                    "Пожалуйста, уточните вопрос."
                )
            else:
                state.answer = (
                    "Не удалосб найти ответ на ваш вопрос. "
                    "Попробуйте переформулировать запрос"
                )
        result = AgentResult(
            answer=state.answer,
            confidence=state.confidence,
            request_id=request_id,
            latency_ms=latency_ms,
            trace=state.trace,
            query_type=state.query_type.value,
            sql_query=state.sql_query,
            sql_result=state.sql_result,
            retry_count=state.retry_count,
            status=status,
        )

        logger.info(
            "Agent [{}]: finished with status={}, confidence={:.2f}, latency={}ms",
            request_id[:8],
            status,
            state.confidence,
            latency_ms,
        )
        
        return result
    
    
agent_orchestrator: AgentOrchestrator = AgentOrchestrator()