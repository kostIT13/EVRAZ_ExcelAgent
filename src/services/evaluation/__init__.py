"""Evaluation module for regression testing.

Provides:
- GoldenDatasetService — эталонные вопросы с правильными SQL/ответами
"""

from src.services.evaluation.golden_dataset import GoldenDatasetService, golden_dataset_service

__all__ = [
    "GoldenDatasetService",
    "golden_dataset_service",
]