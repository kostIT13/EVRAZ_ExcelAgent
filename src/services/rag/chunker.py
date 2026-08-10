from __future__ import annotations
import re
from typing import List, Optional


# Модель multilingual-e5-large (fastembed) имеет контекст 512 токенов.
# 1000 символов русского текста — безопасный лимит без обрезки смысла.
# Безопасный лимит: ~1000 символов (оставляет запас на special tokens),
# совпадает с MAX_EMBED_CHARS в embedder.py — чанкер и эмбеддер не теряют
# символы при передаче друг другу.
MAX_CHARS_SAFE = 1000


def _truncate_to_safe(text: str, max_chars: int = MAX_CHARS_SAFE) -> str:
    """Обрезает текст до безопасного лимита, чтобы не превысить контекст модели эмбеддинга.
    
    Обрезаем по границе последнего абзаца или предложения, чтобы не разорвать смысловой блок.
    """
    if len(text) <= max_chars:
        return text
    # Пробуем обрезать по границе абзаца
    truncated = text[:max_chars]
    last_para = truncated.rfind("\n\n")
    if last_para > max_chars // 2:
        return text[:last_para]
    # Пробуем обрезать по границе предложения
    last_sentence = max(truncated.rfind(". "), truncated.rfind(".\n"))
    if last_sentence > max_chars // 2:
        return text[:last_sentence + 1]
    # Обрезаем по границе слова
    last_space = truncated.rfind(" ")
    if last_space > max_chars // 2:
        return text[:last_space]
    return truncated


def chunk_by_tokens(
    text: str,
    chunk_size: int = 250,
    overlap: int = 30,
    min_chunk_size: int = 50,
) -> List[str]:
    """Разбиение по словам (приблизительным токенам). chunk_size в словах.
    
    Модель имеет 512 токенов контекста. 250 слов русского текста ≈ 500-750 токенов,
    но _truncate_to_safe обрежет до безопасного размера.
    """
    tokens = text.split()
    if len(tokens) <= chunk_size:
        result = text if len(text) >= min_chunk_size else ""
        return [_truncate_to_safe(result)] if result else []

    chunks: List[str] = []
    start = 0
    while start < len(tokens):
        end = start + chunk_size
        chunk_tokens = tokens[start:end]
        chunk_text = " ".join(chunk_tokens)
        chunk_text = _truncate_to_safe(chunk_text)
        if len(chunk_text) >= min_chunk_size:
            chunks.append(chunk_text)
        if end >= len(tokens):
            break
        start += chunk_size - overlap

    return chunks


def chunk_by_sentences(
    text: str,
    max_sentences: int = 6,
    overlap_sentences: int = 1,
    min_chunk_size: int = 50,
) -> List[str]:
    """Разбиение по предложениям."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    sentences = [s.strip() for s in sentences if s.strip()]

    if len(sentences) <= max_sentences:
        result = text if len(text) >= min_chunk_size else ""
        return [_truncate_to_safe(result)] if result else []

    chunks: List[str] = []
    start = 0
    while start < len(sentences):
        end = start + max_sentences
        chunk_text = " ".join(sentences[start:end])
        chunk_text = _truncate_to_safe(chunk_text)
        if len(chunk_text) >= min_chunk_size:
            chunks.append(chunk_text)
        if end >= len(sentences):
            break
        start += max_sentences - overlap_sentences

    return chunks


def chunk_adaptive(
    text: str,
    max_chars: int = 1000,
    overlap_chars: int = 100,
    min_chunk_size: int = 50,
) -> List[str]:
    """Адаптивное разбиение по абзацам."""
    if len(text) <= max_chars:
        result = text if len(text) >= min_chunk_size else ""
        return [_truncate_to_safe(result)] if result else []

    paragraphs = re.split(r"\n\s*\n", text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    chunks: List[str] = []
    buffer = ""

    for para in paragraphs:
        if len(buffer) + len(para) < max_chars:
            buffer = (buffer + "\n\n" + para).strip()
        else:
            if buffer:
                chunks.append(_truncate_to_safe(buffer))
            if len(para) > max_chars:
                sub_chunks = chunk_by_sentences(
                    para,
                    max_sentences=6,
                    min_chunk_size=min_chunk_size,
                )
                chunks.extend(sub_chunks)
                buffer = ""
            else:
                buffer = para

    if buffer:
        chunks.append(_truncate_to_safe(buffer))

    if overlap_chars > 0 and len(chunks) > 1:
        overlapped: List[str] = []
        for i, chunk in enumerate(chunks):
            if i > 0:
                prev_tail = chunks[i - 1][-overlap_chars:]
                chunk = prev_tail + chunk
            chunk = _truncate_to_safe(chunk)
            overlapped.append(chunk)
        chunks = overlapped

    return chunks


def make_chunks(
    text: str,
    strategy: str = "adaptive",
    **kwargs,
) -> List[str]:
    strategy_map = {
        "tokens": chunk_by_tokens,
        "sentences": chunk_by_sentences,
        "adaptive": chunk_adaptive,
    }
    fn = strategy_map.get(strategy)
    if fn is None:
        raise ValueError(f"Unknown chunking strategy: {strategy}. Choose from {list(strategy_map)}")
    return fn(text, **kwargs)