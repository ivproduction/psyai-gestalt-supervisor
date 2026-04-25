"""
services/search.py — семантический поиск по Qdrant.
"""

import logging

from google import genai as google_genai
from google.genai import types
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from app.config import (
    EMBEDDING_DIMENSION, EMBEDDING_MODEL, GEMINI_API_KEY,
    QDRANT_HOST, QDRANT_PORT, TOP_K,
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
    collection: str,
    top_k: int = TOP_K,
    source_file: str | None = None,
) -> list[dict]:
    """
    Семантический поиск по коллекции Qdrant.

    Args:
        query:      запрос на любом языке
        collection: имя коллекции Qdrant
        top_k:      количество результатов
        source_file: опциональный фильтр по файлу

    Returns:
        [{score, text, source_file, chunk_index}, ...]
    """
    log.info("search: '%s' → %s top_k=%d", query, collection, top_k)

    query_vector = _embed_query(query)

    query_filter = None
    if source_file:
        query_filter = Filter(
            must=[FieldCondition(key="source_file", match=MatchValue(value=source_file))]
        )

    response = _qdrant.query_points(
        collection_name=collection,
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
            "chunk_index": hit.payload.get("chunk_index"),
        }
        for hit in response.points
    ]

    log.info("search: найдено %d результатов", len(results))
    return results
