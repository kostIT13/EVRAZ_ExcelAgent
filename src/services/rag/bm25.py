from __future__ import annotations
import re
import pickle
from pathlib import Path
from typing import List, Optional

from loguru import logger
from src.core.config import settings
from rank_bm25 import BM25Okapi

def _tokenize(text: str) -> List[str]:
    text = text.lower()
    tokens = re.findall(r'\w+', text, re.UNICODE)
    return [t for t in tokens if len(t) > 1]


class BM25Index:
    def __init__(self, chunks: Optional[List[str]] = None):
        self._chunks: List[str] = chunks or []
        self._metadata: List[dict] = []  # one dict per chunk: {"source_type": ..., "source_id": ...}
        self._tokenized_corpus: List[List[str]] = []
        self._model: Optional["BM25Okapi"] = None
        self._built: bool = False

    def build(self) -> None:
        """Build BM25 index from the corpus."""
        if not self._chunks:
            logger.warning("BM25 corpus is empty, skipping build")
            self._model = None
            self._built = False
            return

        from rank_bm25 import BM25Okapi

        self._tokenized_corpus = [_tokenize(chunk) for chunk in self._chunks]
        self._model = BM25Okapi(self._tokenized_corpus)
        self._built = True
        logger.info("BM25 index built over {} chunks", len(self._chunks))

    def save(self, path: Path) -> None:
        if not self._built:
            logger.warning("BM25 index not built, saving empty index")
        data = {
            "chunks": self._chunks,
            "metadata": self._metadata,
            "tokenized_corpus": self._tokenized_corpus,
        }
        with open(path, "wb") as f:
            pickle.dump(data, f)
        logger.info("BM25 index saved to {}", path)

    def load(self, path: Path) -> None:
        from rank_bm25 import BM25Okapi

        with open(path, "rb") as f:
            data = pickle.load(f)
        self._chunks = data["chunks"]
        self._metadata = data.get("metadata", [{} for _ in self._chunks])
        self._tokenized_corpus = data["tokenized_corpus"]
        self._model = BM25Okapi(self._tokenized_corpus)
        self._built = True
        logger.info("BM25 index loaded from {} ({} chunks)", path, len(self._chunks))

    def search(self, query: str, top_k: int = 10) -> List[dict]:
        if not self._built or self._model is None:
            raise RuntimeError("BM25 index not built. Call build() first.")

        tokenized_query = _tokenize(query)
        scores = self._model.get_scores(tokenized_query)

        scored = [(i, scores[i]) for i in range(len(scores))]
        scored.sort(key=lambda x: x[1], reverse=True)

        results = []
        for rank, (idx, score) in enumerate(scored[:top_k]):
            meta = self._metadata[idx] if idx < len(self._metadata) else {}
            results.append(
                {
                    "chunk": self._chunks[idx],
                    "score": float(score),
                    "rank": rank + 1,
                    "source_type": meta.get("source_type", "unknown"),
                    "source_id": meta.get("source_id", 0),
                }
            )
        return results

    def add_chunks(self, new_chunks: List[str], metadata: Optional[List[dict]] = None) -> None:
        """Add chunks to the corpus. Call build() to rebuild index."""
        self._chunks.extend(new_chunks)
        if metadata:
            self._metadata.extend(metadata)
        else:
            self._metadata.extend([{} for _ in new_chunks])
        self._built = False
        logger.debug("Added {} chunks, total: {}", len(new_chunks), len(self._chunks))

    @property
    def size(self) -> int:
        return len(self._chunks)

    @property
    def is_built(self) -> bool:
        return self._built