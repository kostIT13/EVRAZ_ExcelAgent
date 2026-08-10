"""
LLM client module.

Provides a unified ``LLMClient`` for chat (primary API key → Ollama fallback),
plus a ``parse_structured`` helper. Эмбеддинги вынесены в fastembed (см.
``src.services.rag.embedder``).
"""

from src.services.llm.llm_client import LLMClient, parse_structured

__all__ = [
    "LLMClient",
    "parse_structured",
]