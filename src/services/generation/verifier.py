from __future__ import annotations
import re
from typing import List, Optional
from loguru import logger
from src.services.rag.hybrid import HybridSearchResult


class VerificationResult:
    """Result of verifying an LLM response."""

    __slots__ = (
        "passed",
        "score",
        "hallucination_warnings",
        "missing_claims",
        "confidence",
    )

    def __init__(
        self,
        passed: bool,
        score: float,
        hallucination_warnings: Optional[List[str]] = None,
        missing_claims: Optional[List[str]] = None,
        confidence: float = 1.0,
    ) -> None:
        self.passed = passed
        self.score = score
        self.hallucination_warnings = hallucination_warnings or []
        self.missing_claims = missing_claims or []
        self.confidence = confidence

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "score": self.score,
            "hallucination_warnings": self.hallucination_warnings,
            "missing_claims": self.missing_claims,
            "confidence": self.confidence,
        }


class Verifier:
    def __init__(self) -> None:
        pass

    def verify(
        self,
        response: str,
        context_chunks: List[HybridSearchResult],
    ) -> VerificationResult:
        context_text = " ".join(r.chunk for r in context_chunks).lower()

        warnings: List[str] = []
        missing: List[str] = []

        numbers_in_response = self._extract_numbers(response)
        for num in numbers_in_response:
            if num not in context_text and not self._is_round_number(num):
                warnings.append(
                    f"Число '{num}' из ответа не найдено в контексте"
                )

        entities = self._extract_entities(response)
        for entity in entities:
            if entity.lower() not in context_text:
                warnings.append(
                    f"Сущность '{entity}' из ответа не найдена в контексте"
                )

        coverage = self._compute_coverage(response, context_text)

        confidence = self._estimate_confidence(warnings, coverage)

        passed = len(warnings) == 0 and coverage >= 0.4

        return VerificationResult(
            passed=passed,
            score=coverage,
            hallucination_warnings=warnings,
            missing_claims=missing,
            confidence=confidence,
        )

    @staticmethod
    def _extract_numbers(text: str) -> List[str]:
        return re.findall(r"\b\d+(?:[.,]\d+)?", text)

    @staticmethod
    def _is_round_number(num_str: str) -> bool:
        try:
            num = float(num_str.replace(",", "."))
            return num in (100, 1000, 10000, 100000, 1000000)
        except ValueError:
            return False

    @staticmethod
    def _extract_entities(text: str) -> List[str]:
        entities = re.findall(r"\b[А-ЯA-Z][а-яa-z]*(?:\s+[А-ЯA-Z][а-яa-z]*)+", text)
        single = re.findall(r"(?<![.?!]\s)\b[А-ЯA-Z][а-яa-z]{2,}\b", text)
        entities.extend(single)
        return list(set(entities))

    @staticmethod
    def _compute_coverage(response: str, context: str) -> float:
        response_words = set(
            re.findall(r"\b[а-яa-z]{3,}\b", response.lower())
        )
        if not response_words:
            return 1.0
        covered = sum(1 for w in response_words if w in context)
        return covered / len(response_words)

    @staticmethod
    def _estimate_confidence(
        warnings: List[str],
        coverage: float,
    ) -> float:
        base = coverage
        penalty = len(warnings) * 0.15
        return max(0.0, min(1.0, base - penalty))