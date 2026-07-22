"""
RAG (Retrieval-Augmented Generation) module.

Provides hybrid retrieval combining:
- **BM25** (sparse keyword search via ``rank_bm25``)
- **Dense** (vector search via pgvector + Ollama embeddings)

Components
----------
- ``bm25`` — BM25 index and search
- ``embedder`` — Dense embedding via Ollama
- ``retrieval`` — pgvector-based dense retrieval
- ``hybrid`` — Hybrid retriever (BM25 + Dense fusion)
- ``chunker`` — Text chunking strategies
- ``rag_service`` — High-level orchestrator
"""

from src.services.rag.bm25 import BM25Index
from src.services.rag.chunker import make_chunks, chunk_by_tokens, chunk_by_sentences, chunk_adaptive
from src.services.rag.embedder import Embedder, cosine_similarity
from src.services.rag.hybrid import HybridRetriever, HybridSearchResult
from src.services.rag.rag_service import RagService, rag_service
from src.services.rag.retrieval import DenseRetriever, DenseSearchResult

__all__ = [
    "BM25Index",
    "make_chunks",
    "chunk_by_tokens",
    "chunk_by_sentences",
    "chunk_adaptive",
    "Embedder",
    "cosine_similarity",
    "HybridRetriever",
    "HybridSearchResult",
    "RagService",
    "rag_service",
    "DenseRetriever",
    "DenseSearchResult",
]