"""
vector_store.py — чанкинг, эмбеддинг, загрузка и удаление в Qdrant.
"""

import time
import uuid
from typing import List

from google import genai as google_genai
from google.genai import types
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams
)

from app.config import (
    EMBEDDING_DIMENSION, EMBEDDING_MODEL, GEMINI_API_KEY, QDRANT_HOST, QDRANT_PORT,
    collection_name,
)

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
EMBED_BATCH = 10

_genai = google_genai.Client(api_key=GEMINI_API_KEY)


def get_client() -> QdrantClient:
    return QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)


def ensure_collection(client: QdrantClient, name: str) -> None:
    existing = {c.name for c in client.get_collections().collections}
    if name not in existing:
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=EMBEDDING_DIMENSION, distance=Distance.COSINE),
        )


def embed_texts(texts: List[str]) -> List[List[float]]:
    all_embeddings: List[List[float]] = []
    for i in range(0, len(texts), EMBED_BATCH):
        batch = texts[i: i + EMBED_BATCH]
        result = _genai.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=batch,
            config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIMENSION),
        )
        all_embeddings.extend([e.values for e in result.embeddings])
        if i + EMBED_BATCH < len(texts):
            time.sleep(0.5)
    return all_embeddings


def ingest_to_qdrant(
    text: str,
    source_file: str,
    source_type: str,
    mode: str,
) -> int:
    """
    Полный пайплайн: текст → чанки → эмбеддинги → Qdrant.
    Коллекция: {source_type}_{mode}
    Возвращает количество загруженных чанков.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )
    chunks = [c for c in splitter.split_text(text) if len(c.strip()) >= 50]
    if not chunks:
        return 0

    embeddings = embed_texts(chunks)
    coll = collection_name(source_type, mode)

    client = get_client()
    ensure_collection(client, coll)

    points = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector=emb,
            payload={
                "text": chunk,
                "source_file": source_file,
                "source_type": source_type,
                "mode": mode,
                "chunk_index": i,
            },
        )
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings))
    ]

    client.upsert(collection_name=coll, points=points)
    return len(chunks)


def delete_file_chunks(source_file: str, source_type: str, mode: str) -> int:
    """
    Удаляет все чанки файла из коллекции.
    Возвращает количество удалённых точек.
    """
    coll = collection_name(source_type, mode)
    client = get_client()

    existing = {c.name for c in client.get_collections().collections}
    if coll not in existing:
        return 0

    before = client.get_collection(coll).points_count
    client.delete(
        collection_name=coll,
        points_selector=Filter(
            must=[FieldCondition(key="source_file", match=MatchValue(value=source_file))]
        ),
    )
    after = client.get_collection(coll).points_count
    return before - after
