"""
LLM client module.

Provides a unified ``LLMClient`` for chat (primary → cheap model fallback),
plus a ``parse_structured`` helper. Векторные эмбеддинги удалены из архитектуры.
"""

from src.services.llm.llm_client import LLMClient, parse_structured

__all__ = [
    "LLMClient",
    "parse_structured",
]