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

    rag_context: str
    rag_chunks: List[Dict[str, Any]]
    rag_error: Optional[str]

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


NODE_RAG = "rag"
NODE_CLASSIFIER = "classifier"
NODE_DISAMBIGUATION = "disambiguation"
NODE_PLANNER = "planner"
NODE_CODEGEN = "codegen"
NODE_EXECUTOR = "executor"
NODE_VERIFIER = "verifier"
NODE_ANSWER = "answer"
NODE_FAILED = "failed"
