"""
vector_store.py — чанкинг, эмбеддинг, загрузка и удаление в Qdrant.
"""

import time
import uuid
from typing import List

from google import genai as google_genai
from google.genai import types
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.config import (
    EMBEDDING_DIMENSION, EMBEDDING_MODEL, GEMINI_API_KEY, QDRANT_HOST, QDRANT_PORT,
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
            config=types.EmbedContentConfig(
                task_type="retrieval_document",
                output_dimensionality=EMBEDDING_DIMENSION
            ),
        )
        all_embeddings.extend([e.values for e in result.embeddings])
        if i + EMBED_BATCH < len(texts):
            time.sleep(0.5)
    return all_embeddings


def ingest_to_qdrant(
    text: str,
    source_file: str,
    collection: str,
) -> int:
    """
    Текст → чанки → эмбеддинги → Qdrant.
    Коллекция задаётся явно. Возвращает количество загруженных чанков.
    """
    md_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")],
        strip_headers=False,
    )
    char_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )

    sections = md_splitter.split_text(text)
    raw_chunks = []
    for section in sections:
        section_text = section.page_content.strip()
        if not section_text:
            continue
        if len(section_text) > CHUNK_SIZE:
            raw_chunks.extend(char_splitter.split_text(section_text))
        else:
            raw_chunks.append(section_text)

    chunks = [c for c in raw_chunks if len(c.strip()) >= 50]
    if not chunks:
        return 0

    embeddings = embed_texts(chunks)

    client = get_client()
    ensure_collection(client, collection)

    points = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector=emb,
            payload={
                "text": chunk,
                "source_file": source_file,
                "chunk_index": i,
            },
        )
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings))
    ]

    client.upsert(collection_name=collection, points=points)
    return len(chunks)


def delete_collection(collection: str) -> None:
    """Удаляет коллекцию из Qdrant. Молча игнорирует если не существует."""
    client = get_client()
    existing = {c.name for c in client.get_collections().collections}
    if collection in existing:
        client.delete_collection(collection)
