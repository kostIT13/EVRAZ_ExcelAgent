"""
Generation module: RAG-powered answer generation pipeline.

Components
----------
- ``rag_prompt`` — Prompt templates and context formatting
- ``verifier`` — Response verification (hallucination detection)
- ``pipeline`` — End-to-end generation pipeline (retrieve → generate → verify)
"""

from src.services.generation.rag_prompt import build_rag_prompt, format_context, SYSTEM_PROMPT
from src.services.generation.verifier import Verifier, VerificationResult
from src.services.generation.pipeline import GenerationPipeline, GenerationResult, pipeline

__all__ = [
    "build_rag_prompt",
    "format_context",
    "SYSTEM_PROMPT",
    "Verifier",
    "VerificationResult",
    "GenerationPipeline",
    "GenerationResult",
    "pipeline",
]