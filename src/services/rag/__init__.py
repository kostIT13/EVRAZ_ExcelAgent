"""
RAG (Retrieval-Augmented Generation) module.

Provides hybrid retrieval combining:
- **Sparse** (BM25-подобные sparse-вектора через Qdrant)
- **Dense** (векторный поиск через Qdrant + fastembed embeddings)

Components
----------
- ``sparse`` — генерация sparse-векторов (BM25/SPLADE)
- ``embedder`` — Dense embedding via fastembed (локально)
- ``retrieval`` — Qdrant-based dense retrieval
- ``hybrid`` — Hybrid retriever (dense + sparse fusion через Qdrant)
- ``reranker`` — Реранкинг результатов (flashrank)
- ``chunker`` — Text chunking strategies
- ``rag_service`` — High-level orchestrator
- ``entity_resolver`` — Entity resolution service
- ``query_cache`` — Query cache service
"""

from src.services.rag.chunker import make_chunks, chunk_by_tokens, chunk_by_sentences, chunk_adaptive
from src.services.rag.embedder import Embedder, cosine_similarity
from src.services.rag.hybrid import HybridRetriever, HybridSearchResult
from src.services.rag.rag_service import RagService, rag_service
from src.services.rag.retrieval import DenseRetriever, DenseSearchResult
from src.services.rag.sparse import SparseEmbedder, sparse_embedder
from src.services.rag.reranker import Reranker, reranker
from src.services.rag.entity_resolver import EntityResolver, entity_resolver
from src.services.rag.query_cache import QueryCacheService, query_cache_service

__all__ = [
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
    "SparseEmbedder",
    "sparse_embedder",
    "Reranker",
    "reranker",
    "EntityResolver",
    "entity_resolver",
    "QueryCacheService",
    "query_cache_service",
]