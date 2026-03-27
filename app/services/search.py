"""
services/search.py — семантический поиск по Qdrant.

Используется в:
  - api/admin.py  (/admin/search — дебаг)
  - services/rag.py (контекст для генерации)
"""

import logging
from typing import Literal

from google import genai as google_genai
from google.genai import types
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from app.config import (
    EMBEDDING_DIMENSION, EMBEDDING_MODEL, GEMINI_API_KEY,
    QDRANT_HOST, QDRANT_PORT, TOP_K, collection_name,
)

log = logging.getLogger(__name__)

_genai = google_genai.Client(api_key=GEMINI_API_KEY)
_qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)


def _embed_query(text: str) -> list[float]:
    result = _genai.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=[text],
        config=types.EmbedContentConfig(
            task_type="retrieval_query",
            output_dimensionality=EMBEDDING_DIMENSION,
        ),
    )
    return result.embeddings[0].values


def search(
    query: str,
    source_type: str = "session_guides",
    mode: Literal["standard", "smart"] = "smart",
    top_k: int = TOP_K,
    source_file: str | None = None,
) -> list[dict]:
    """
    Семантический поиск по коллекции {source_type}_{mode}.

    Args:
        query:       запрос на любом языке
        source_type: тип источника (session_guides, therapist_finder, ...)
        mode:        standard или smart
        top_k:       количество результатов
        source_file: фильтр по конкретному файлу

    Returns:
        [{score, text, source_file, source_type, chunk_index}, ...]
    """
    coll = collection_name(source_type, mode)
    log.info("search: '%s' → %s top_k=%d source_file=%s", query, coll, top_k, source_file)

    query_vector = _embed_query(query)

    query_filter = None
    if source_file:
        query_filter = Filter(
            must=[FieldCondition(key="source_file", match=MatchValue(value=source_file))]
        )

    response = _qdrant.query_points(
        collection_name=coll,
        query=query_vector,
        limit=top_k,
        query_filter=query_filter,
        with_payload=True,
    )

    results = [
        {
            "score": round(hit.score, 4),
            "text": hit.payload.get("text", ""),
            "source_file": hit.payload.get("source_file"),
            "source_type": hit.payload.get("source_type"),
            "chunk_index": hit.payload.get("chunk_index"),
        }
        for hit in response.points
    ]

    log.info("search: найдено %d результатов", len(results))
    return results
