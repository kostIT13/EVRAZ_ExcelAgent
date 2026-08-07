from __future__ import annotations
import asyncio
import hashlib
from typing import List, Optional
import numpy as np
from src.core.config import settings
from src.core.logging_settings import logger
from src.services.rag.embedding_cache import EmbeddingCache, InMemoryEmbeddingCache


# Модель intfloat/multilingual-e5-large имеет контекст 512 токенов.
# Токенизатор XLM-RoBERTa даёт для русского текста примерно 1 токен
# на 1.5-2 символа. 512 токенов ≈ 770-1020 символов.
# Обрезаем до 1000 символов (безопасный запас). Для длинных чанков лучше,
# чтобы основная смысловая нагрузка была в начале текста.
MAX_EMBED_CHARS = 1000


def _truncate_text_for_embed(text: str, max_chars: int = MAX_EMBED_CHARS) -> str:
    """Обрезает текст до безопасного лимита для модели эмбеддинга.

    Модель intfloat/multilingual-e5-large имеет контекст 512 токенов.
    Обрезаем по границе абзаца или предложения, чтобы сохранить смысл.
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
    """Генератор dense-эмбеддингов на базе fastembed (локальный CPU-инференс).

    В отличие от прежней реализации (которая ходила по HTTP к Ollama),
    fastembed загружает модель локально и инференсит прямо на хосте.
    Это радикально ускоряет индексацию (pload file): нет сетевых round-trip'ов
    и последовательных запросов — батч считается одним проходом.

    Embedder знает только про fastembed и абстрактный кэш.
    Он НЕ знает про конкретное хранилище (Postgres/Qdrant/Redis) —
    кэш прокидывается через интерфейс EmbeddingCache.
    """

    def __init__(
        self,
        cache: Optional[EmbeddingCache] = None,
        model_name: Optional[str] = None,
    ) -> None:
        self._cache: EmbeddingCache = cache or InMemoryEmbeddingCache()
        self._model_name: str = model_name or settings.EMBED_MODEL
        self._model = None  # ленивая инициализация fastembed.TextEmbedding
        # fastembed загружает модель при первом embed(); при первом вызове
        # будет скачивание модели, поэтому логируем явно.
        self._dim: int = settings.EMBED_DIMENSION
        # Максимум текстов в одном батче для одного прохода fastembed.
        self.EMBED_BATCH_SIZE = settings.EMBED_BATCH_SIZE

    def _get_model(self):
        """Лениво инициализирует fastembed.TextEmbedding (модель грузится один раз)."""
        if self._model is None:
            from fastembed import TextEmbedding

            logger.info("Loading fastembed TextEmbedding '{}' (first call, may download model)", self._model_name)
            self._model = TextEmbedding(model_name=self._model_name)
            # У fastembed 0.8.x у TextEmbedding нет публичного атрибута dimension;
            # размерность берём из конфига (EMBED_DIMENSION, согласован с моделью).
            logger.info(
                "fastembed TextEmbedding '{}' loaded, dimension={}",
                self._model_name,
                self._dim,
            )
        return self._model

    async def embed(self, text: str) -> List[float]:
        # Обрезаем текст до безопасного лимита модели
        safe_text = _truncate_text_for_embed(text)

        cached = await self._load_from_cache(safe_text)
        if cached is not None:
            return cached

        vector = await self._embed_texts([safe_text])
        result = vector[0]

        await self._save_to_cache(safe_text, result)

        return result

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Эмбеддит список текстов батчами через локальный fastembed-инференс.

        В отличие от прежней реализации (HTTP к Ollama), здесь не требуется
        группировать в отдельные запросы ради round-trip'ов — fastembed сам
        инференсит порции. Тем не менее батчим для контроля памяти.
        """
        if not texts:
            return []

        safe_texts = [_truncate_text_for_embed(t) for t in texts]

        # Сначала вытаскиваем всё, что есть в кэше
        results: List[Optional[List[float]]] = [None] * len(safe_texts)
        hashes: List[str] = []
        to_embed_indices: List[int] = []
        for idx, safe in enumerate(safe_texts):
            h = self._hash_query(safe)
            hashes.append(h)
            cached = await self._load_from_cache(safe)
            if cached is not None:
                results[idx] = cached
            else:
                to_embed_indices.append(idx)

        # Батчим только незакэшированные тексты
        for chunk_start in range(0, len(to_embed_indices), self.EMBED_BATCH_SIZE):
            batch_indices = to_embed_indices[chunk_start : chunk_start + self.EMBED_BATCH_SIZE]
            batch_texts = [safe_texts[i] for i in batch_indices]

            vectors = await self._embed_texts(batch_texts)

            for batch_pos, orig_idx in enumerate(batch_indices):
                vector = vectors[batch_pos]
                results[orig_idx] = vector
                await self._save_to_cache(safe_texts[orig_idx], vector)

        # Гарантируем возврат в исходном порядке
        return [v for v in results if v is not None]

    async def _embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Синхронный fastembed-инференс, выполненный в отдельном потоке.

        fastembed.embed() возвращает генератор numpy-векторов. Чтобы не блокировать
        asyncio event loop, выполняем в потоке через asyncio.to_thread.
        """
        model = self._get_model()

        def _run() -> List[List[float]]:
            vectors = list(model.embed(texts))
            return [v.tolist() for v in vectors]

        return await asyncio.to_thread(_run)

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