from __future__ import annotations
from typing import Any, List
from src.core.logging_settings import logger
from src.services.agent.graph_state import GraphState
from src.services.entity_resolution.entity_resolver import (
    EntityCandidate,
    entity_resolver,
)


async def entity_resolution_node(
    state: GraphState,
    **kwargs: Any,
) -> GraphState:
    request_id = state.get("request_id", "?")[:8]
    question = state.get("question", "")
    top_n = min(state.get("top_k", 10), 10)

    logger.info(
        "EntityResolution Node [{}]: resolving entities (pg_trgm) for '{}' (top_n={})",
        request_id,
        question[:80],
        top_n,
    )

    try:
        candidates: List[EntityCandidate] = await entity_resolver.resolve_candidates(
            query=question,
            top_n=top_n,
        )
        state["entity_candidates"] = [c.to_dict() for c in candidates]
        logger.info(
            "EntityResolution Node [{}]: found {} candidates",
            request_id,
            len(candidates),
        )
    except Exception as exc:
        logger.error(
            "EntityResolution Node [{}]: entity resolution failed: {}",
            request_id,
            exc,
        )
        state["entity_candidates"] = []

    # Fallback: список сущностей для промпта, если pg_trgm пуст.
    state["entities_for_prompt"] = entity_resolver.entities_for_prompt()

    state["trace"] = state.get("trace", {})
    state["trace"]["entity_resolution"] = {
        "candidate_count": len(state.get("entity_candidates", [])),
        "candidates": state.get("entity_candidates", [])[:5],
    }

    return state