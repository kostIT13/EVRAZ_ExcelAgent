from __future__ import annotations
import hashlib
from typing import List, Optional

import numpy as np

from src.core.config import settings
from src.core.logging_settings import logger
from src.services.llm.llm_client import LLMClient
from src.services.rag.embedding_cache import EmbeddingCache, InMemoryEmbeddingCache


# Верхний предел символов для эмбеддинга одного текста. Модель nomic-embed-text
# имеет контекст 8192 токенов, поэтому 1000 символов русского текста — безопасный
# запас, не требующий агрессивной обрезки смысла.
MAX_EMBED_CHARS = 1000

# nomic-embed-text рекомендует явные префиксы для разделения поисковых запросов
# и документов: это повышает качество ретрива. Префикс добавляется до обрезки,
# поэтому суммарная длина не превысит MAX_EMBED_CHARS.
NOMIC_QUERY_PREFIX = "search_query: "
NOMIC_DOCUMENT_PREFIX = "search_document: "


def _truncate_text_for_embed(text: str, max_chars: int = MAX_EMBED_CHARS) -> str:
    """Обрезает текст до безопасного лимита для модели эмбеддинга.

    Модель nomic-embed-text имеет контекст 8192 токенов. Обрезаем по границе
    абзаца или предложения, чтобы сохранить смысл.
    """
    if len(text) <= max_chars:
        return text
    # Пробуем обрезать по границе абзаца
    truncated = text[:max_chars]
    last_para = truncated.rfind("\n\n")
    if last_para > max_chars // 2:
        result = text[:last_para]
        logger.warning("Text truncated for embedding from {} to {} chars (by paragraph)", len(text), len(result))
        return result
    # Пробуем обрезать по границе предложения
    last_sentence = max(truncated.rfind(". "), truncated.rfind(".\n"))
    if last_sentence > max_chars // 2:
        result = text[:last_sentence + 1]
        logger.warning("Text truncated for embedding from {} to {} chars (by sentence)", len(text), len(result))
        return result
    # Обрезаем по границе слова
    last_space = truncated.rfind(" ")
    if last_space > max_chars // 2:
        result = text[:last_space]
        logger.warning("Text truncated for embedding from {} to {} chars (by word)", len(text), len(result))
        return result
    logger.warning("Text truncated for embedding from {} to {} chars (hard cut)", len(text), len(truncated))
    return truncated


class Embedder:
    """Генератор dense-эмбеддингов через Ollama (HTTP, OpenAI-совместимый /v1/embeddings).

    Модель nomic-embed-text (768 dim) запускается локально в контейнере Ollama.
    В отличие от fastembed (который качал большие веса с HuggingFace Hub и
    мог недоступен/зависать), Ollama уже работает в docker и не зависит от HF.

    Embedder знает только про LLMClient (HTTP к Ollama) и абстрактный кэш.
    Он НЕ знает про конкретное хранилище (Postgres/Qdrant/Redis) —
    кэш прокидывается через интерфейс EmbeddingCache.
    """

    def __init__(
        self,
        cache: Optional[EmbeddingCache] = None,
        llm: Optional[LLMClient] = None,
        model_name: Optional[str] = None,
    ) -> None:
        self._cache: EmbeddingCache = cache or InMemoryEmbeddingCache()
        self._llm: LLMClient = llm or LLMClient()
        self._model_name: str = model_name or settings.OLLAMA_EMBED_MODEL
        self._dim: int = settings.EMBED_DIMENSION

    async def embed(self, text: str, is_query: bool = False) -> List[float]:
        """Эмбеддит один текст через Ollama. Для nomic-embed-text добавляет префикс.

        is_query=True -> префикс "search_query: " (поисковый запрос);
        is_query=False -> префикс "search_document: " (документ/чанк).
        """
        prefix = NOMIC_QUERY_PREFIX if is_query else NOMIC_DOCUMENT_PREFIX
        # Префикс добавляем до обрезки, чтобы суммарно не превысить лимит
        safe_text = _truncate_text_for_embed(prefix + text)

        cached = await self._load_from_cache(safe_text)
        if cached is not None:
            return cached

        result = await self._llm.embed(safe_text)

        await self._save_to_cache(safe_text, result)

        return result

    async def embed_batch(self, texts: List[str], is_query: bool = False) -> List[List[float]]:
        """Эмбеддит список текстов батчами через Ollama (один HTTP-запрос).

        is_query=True -> префикс "search_query: " (запросы), иначе "search_document: ".
        """
        if not texts:
            return []

        prefix = NOMIC_QUERY_PREFIX if is_query else NOMIC_DOCUMENT_PREFIX
        safe_texts = [_truncate_text_for_embed(prefix + t) for t in texts]

        # Сначала вытаскиваем всё, что есть в кэше
        results: List[Optional[List[float]]] = [None] * len(safe_texts)
        to_embed_indices: List[int] = []
        for idx, safe in enumerate(safe_texts):
            cached = await self._load_from_cache(safe)
            if cached is not None:
                results[idx] = cached
            else:
                to_embed_indices.append(idx)

        if to_embed_indices:
            batch_texts = [safe_texts[i] for i in to_embed_indices]
            vectors = await self._llm.embed_batch(batch_texts)
            for batch_pos, orig_idx in enumerate(to_embed_indices):
                vector = vectors[batch_pos]
                results[orig_idx] = vector
                await self._save_to_cache(safe_texts[orig_idx], vector)

        # Гарантируем возврат в исходном порядке
        return [v for v in results if v is not None]

    @staticmethod
    def _hash_query(query: str) -> str:
        return hashlib.sha256(query.encode("utf-8")).hexdigest()

    async def _load_from_cache(self, text: str) -> Optional[List[float]]:
        query_hash = self._hash_query(text)
        try:
            cached = await self._cache.get(query_hash)
            if cached is not None:
                logger.debug("Embedding cache hit for hash={}", query_hash[:12])
                return cached
        except Exception as exc:
            logger.warning("Embedding cache read failed: {}", exc)
        return None

    async def _save_to_cache(self, text: str, vector: List[float]) -> None:
        query_hash = self._hash_query(text)
        try:
            await self._cache.set(
                query_hash,
                text,
                vector,
                self._model_name,
            )
            logger.debug("Embedding cached for hash={}", query_hash[:12])
        except Exception as exc:
            logger.warning("Embedding cache write failed: {}", exc)

    @property
    def dimension(self) -> int:
        return self._dim


def cosine_similarity(a: List[float], b: List[float]) -> float:
    arr_a = np.array(a, dtype=np.float32)
    arr_b = np.array(b, dtype=np.float32)
    norm_a = np.linalg.norm(arr_a)
    norm_b = np.linalg.norm(arr_b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(arr_a, arr_b) / (norm_a * norm_b))