"""
LLM client module.

Provides a unified ``LLMClient`` for chat (primary API key → Ollama fallback)
and embeddings (Ollama), plus a ``parse_structured`` helper.
"""

from src.services.llm.llm_client import LLMClient, parse_structured

__all__ = [
    "LLMClient",
    "parse_structured",
]