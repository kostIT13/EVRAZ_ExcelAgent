"""
Generation module: agent-based answer generation pipeline.

RAG-over-cells и векторные эмбеддинги удалены из архитектуры. Здесь
остался только пайплайн ``run_agent`` (запуск агента с Self-Correction
и логированием в БД).
"""

from src.services.generation.pipeline import GenerationPipeline, pipeline

__all__ = [
    "GenerationPipeline",
    "pipeline",
]