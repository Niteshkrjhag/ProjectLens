"""Embedding and chunking helpers for retrieval.

ProjectLens uses Gemini embeddings when explicitly enabled and configured. The
offline path uses a stable hashing vector so the same corpus can exercise the
retrieval contract without a live key, quota, or network connection.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass

from .config import Settings

DEFAULT_DIMENSIONS = 1536


@dataclass(frozen=True, slots=True)
class Embedding:
    values: list[float]
    provider: str


def chunk_text(text: str, *, size: int = 1600, overlap: int = 160) -> list[str]:
    """Split source text into stable, overlapping retrieval chunks."""
    clean = text.strip()
    if not clean:
        return []
    if size <= overlap:
        raise ValueError("chunk size must be larger than overlap")
    chunks: list[str] = []
    start = 0
    while start < len(clean):
        end = min(len(clean), start + size)
        if end < len(clean):
            boundary = clean.rfind("\n", start, end)
            if boundary > start + size // 2:
                end = boundary
        chunks.append(clean[start:end].strip())
        if end >= len(clean):
            break
        start = max(end - overlap, start + 1)
    return [chunk for chunk in chunks if chunk]


def _hash_vector(text: str, dimensions: int = DEFAULT_DIMENSIONS) -> list[float]:
    """Create a deterministic signed bag-of-words vector for offline search."""
    values = [0.0] * dimensions
    tokens = re.findall(r"[a-z0-9]{2,}", text.casefold())
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] & 1 else -1.0
        values[index] += sign
    norm = math.sqrt(sum(value * value for value in values))
    return [value / norm for value in values] if norm else values


def _fit_dimensions(values: list[float], dimensions: int = DEFAULT_DIMENSIONS) -> list[float]:
    """Keep provider output compatible with the configured pgvector column."""
    fitted = values[:dimensions] + [0.0] * max(0, dimensions - len(values))
    norm = math.sqrt(sum(value * value for value in fitted))
    return [value / norm for value in fitted] if norm else fitted


def embed_text(text: str, settings: Settings | None = None) -> Embedding:
    """Embed text using Gemini when enabled, otherwise use the offline vector."""
    settings = settings or Settings(database_url="")
    key = settings.gemini_api_key.get_secret_value() if settings.gemini_api_key else ""
    if settings.projectlens_llm_mode.casefold() == "live" and key:
        try:
            from google import genai
            from google.genai import types as genai_types

            response = genai.Client(api_key=key).models.embed_content(
                model=settings.gemini_embedding_model,
                contents=text,
                config=genai_types.EmbedContentConfig(output_dimensionality=DEFAULT_DIMENSIONS),
            )
            embeddings = getattr(response, "embeddings", None) or []
            values = getattr(embeddings[0], "values", None) if embeddings else None
            if values:
                return Embedding(_fit_dimensions(list(values)), "gemini")
        except Exception:  # noqa: BLE001 - retrieval must retain the offline fallback
            return Embedding(_hash_vector(text), "local_hash")
    return Embedding(_hash_vector(text), "local_hash")
