from __future__ import annotations
import re
from typing import List, Optional


def chunk_by_tokens(
    text: str,
    chunk_size: int = 512,
    overlap: int = 64,
    min_chunk_size: int = 50,
) -> List[str]:
    tokens = text.split()
    if len(tokens) <= chunk_size:
        return [text] if len(text) >= min_chunk_size else []

    chunks: List[str] = []
    start = 0
    while start < len(tokens):
        end = start + chunk_size
        chunk_tokens = tokens[start:end]
        chunk_text = " ".join(chunk_tokens)
        if len(chunk_text) >= min_chunk_size:
            chunks.append(chunk_text)
        if end >= len(tokens):
            break
        start += chunk_size - overlap

    return chunks


def chunk_by_sentences(
    text: str,
    max_sentences: int = 8,
    overlap_sentences: int = 1,
    min_chunk_size: int = 50,
) -> List[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    sentences = [s.strip() for s in sentences if s.strip()]

    if len(sentences) <= max_sentences:
        return [text] if len(text) >= min_chunk_size else []

    chunks: List[str] = []
    start = 0
    while start < len(sentences):
        end = start + max_sentences
        chunk_text = " ".join(sentences[start:end])
        if len(chunk_text) >= min_chunk_size:
            chunks.append(chunk_text)
        if end >= len(sentences):
            break
        start += max_sentences - overlap_sentences

    return chunks


def chunk_adaptive(
    text: str,
    max_chars: int = 1500,
    overlap_chars: int = 150,
    min_chunk_size: int = 100,
) -> List[str]:
    if len(text) <= max_chars:
        return [text] if len(text) >= min_chunk_size else []

    paragraphs = re.split(r"\n\s*\n", text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    chunks: List[str] = []
    buffer = ""

    for para in paragraphs:
        if len(buffer) + len(para) < max_chars:
            buffer = (buffer + "\n\n" + para).strip()
        else:
            if buffer:
                chunks.append(buffer)
            if len(para) > max_chars:
                sub_chunks = chunk_by_sentences(
                    para,
                    max_sentences=10,
                    min_chunk_size=min_chunk_size,
                )
                chunks.extend(sub_chunks)
                buffer = ""
            else:
                buffer = para

    if buffer:
        chunks.append(buffer)

    if overlap_chars > 0 and len(chunks) > 1:
        overlapped: List[str] = []
        for i, chunk in enumerate(chunks):
            if i > 0:
                prev_tail = chunks[i - 1][-overlap_chars:]
                chunk = prev_tail + chunk
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