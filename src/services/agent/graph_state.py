from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Optional, TypedDict


class QueryType(str, Enum):
    LOOKUP = "lookup"
    AGGREGATE = "aggregate"
    CROSS_SHEET = "cross_sheet"
    DELTA = "delta"
    UNKNOWN = "unknown"


class GraphState(TypedDict, total=False):
    question: str
    request_id: str
    top_k: int

    # Entity-resolution (вместо тяжёлого RAG-over-cells).
    # Список top-N кандидатов item/supplier/period, найденных по вопросу.
    entity_candidates: List[Dict[str, Any]]
    entities_for_prompt: Optional[Dict[str, List[str]]]

    query_type: QueryType
    entities: List[str]
    relevant_sheets: List[Dict[str, Any]]

    disambiguation_needed: bool
    disambiguation_info: Dict[str, Any]

    plan: str
    schema: List[Dict[str, Any]]

    sql_query: str
    validation_errors: List[str]

    sql_result: List[Dict[str, Any]]
    sql_error: Optional[str]

    answer: str
    confidence: float
    retry_count: int
    needs_retry: bool
    retry_reason: str

    trace: Dict[str, Any]
    error: Optional[str]


NODE_CLASSIFIER = "classifier"
NODE_DISAMBIGUATION = "disambiguation"
NODE_PLANNER = "planner"
NODE_CODEGEN = "codegen"
NODE_EXECUTOR = "executor"
NODE_VERIFIER = "verifier"
NODE_ANSWER = "answer"
NODE_FAILED = "failed"
