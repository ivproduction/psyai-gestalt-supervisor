"""
api/admin.py — Admin API.
Swagger UI: http://localhost:8000/swagger
Префикс: /api/admin
"""

import asyncio
import json
import logging
import shutil
import traceback
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient

from app.config import (
    ADMIN_API_KEY, DOCS_DIR, QDRANT_HOST, QDRANT_PORT,
    RATE_LIMIT_DAYS, RATE_LIMIT_REQUESTS, RATE_LIMIT_WHITELIST,
)
from app.ragas import evaluate_rag
from app.ragas.questions import QUESTIONS as _DEFAULT_QUESTIONS
from app.services.search import search as qdrant_search
from app.vector_store import delete_collection, ingest_to_qdrant

log = logging.getLogger(__name__)

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)


async def require_api_key(key: str = Security(_api_key_header)):
    if key != ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")


router = APIRouter(prefix="/api/admin", tags=["admin"])


# ── Загрузка и ingest текстового файла ────────────────────────

@router.post("/files/ingest", summary="Загрузить .txt/.md и сразу ingest в Qdrant")
async def ingest_file(file: UploadFile = File(...)):
    """
    Принимает .txt или .md файл.
    Коллекция = имя файла без расширения (например polster.txt → коллекция polster).
    Сохраняет в data/docs/{collection}/, сразу загружает в Qdrant.
    """
    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".txt", ".md"):
        raise HTTPException(status_code=400, detail="Только .txt и .md файлы")

    collection = Path(file.filename).stem
    dest_dir = DOCS_DIR / collection
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / file.filename

    content_bytes = await file.read()
    dest_path.write_bytes(content_bytes)

    text = content_bytes.decode("utf-8", errors="replace")
    log.info("=== INGEST [%s] %s ===", collection, file.filename)

    try:
        chunks = ingest_to_qdrant(text, file.filename, collection)
    except Exception as e:
        log.exception("Ошибка ingest %s: %s", file.filename, e)
        raise HTTPException(status_code=500, detail=f"Ошибка ingest: {e}")

    log.info("=== INGEST готово: %d чанков → %s ===", chunks, collection)
    return {
        "filename": file.filename,
        "collection": collection,
        "path": str(dest_path),
        "chunks": chunks,
    }


# ── Список файлов ──────────────────────────────────────────────

@router.get("/files/list", summary="Список файлов в data/docs/ с количеством чанков")
def list_files():
    """
    Все файлы из data/docs/{collection}/ с количеством чанков в Qdrant.
    """
    if not DOCS_DIR.exists():
        return []

    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    existing_collections = {c.name for c in client.get_collections().collections}

    result = []
    for coll_dir in sorted(DOCS_DIR.iterdir()):
        if not coll_dir.is_dir():
            continue
        coll_name = coll_dir.name
        chunks = 0
        if coll_name in existing_collections:
            try:
                chunks = client.get_collection(coll_name).points_count or 0
            except Exception:
                pass
        for f in sorted(coll_dir.glob("*.txt")) + sorted(coll_dir.glob("*.md")):
            result.append({
                "collection": coll_name,
                "filename": f.name,
                "size_kb": round(f.stat().st_size / 1024, 1),
                "chunks": chunks,
            })
    return result


# ── Удаление коллекции ────────────────────────────────────────

@router.delete("/collections/{name}", summary="Удалить коллекцию из Qdrant и файлы с диска")
def delete_collection_endpoint(name: str):
    """
    Удаляет коллекцию из Qdrant и директорию data/docs/{name}/.
    """
    delete_collection(name)
    dir_path = DOCS_DIR / name
    if dir_path.exists():
        shutil.rmtree(dir_path)
    log.info("Удалена коллекция '%s' и директория '%s'", name, dir_path)
    return {"collection": name, "deleted": True}


# ── Поиск (дебаг) ─────────────────────────────────────────────

@router.get("/search", summary="Семантический поиск (дебаг)")
def search(
    query: str,
    collection: str,
    top_k: int = 5,
    source_file: str | None = None,
):
    """
    Проверка качества после ingest.

    - **collection** — имя коллекции Qdrant
    - **source_file** — фильтр по файлу (необязательно)
    """
    try:
        results = qdrant_search(
            query=query,
            collection=collection,
            top_k=top_k,
            source_file=source_file,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"query": query, "collection": collection, "results": results}


# ── RAGAS оценка качества ─────────────────────────────────────

class RagasRequest(BaseModel):
    collection: str = "session_guides"
    questions: list[str] = Field(
        default_factory=lambda: list(_DEFAULT_QUESTIONS),
        description="Вопросы для оценки.",
    )


async def _ragas_background(questions, collection):
    from app.config import RAGAS_DIR
    try:
        await evaluate_rag(questions=questions, collection=collection)
    except Exception as e:
        log.error("RAGAS фоновая ошибка: %s", e, exc_info=True)
        RAGAS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        err_path = RAGAS_DIR / f"{collection}_{ts}.json"
        err_path.write_text(json.dumps({
            "timestamp": datetime.now().isoformat(),
            "collection": collection,
            "questions_evaluated": len(questions) if questions else 0,
            "scores": {"faithfulness": None, "answer_relevancy": None, "context_precision": None},
            "details": [],
            "error": str(e),
            "traceback": traceback.format_exc(),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        log.error("RAGAS отчёт об ошибке сохранён: %s", err_path)


@router.post("/ragas", summary="Запустить RAGAS оценку (фоново)")
async def ragas_evaluate(body: RagasRequest = RagasRequest()):
    """
    Запускает RAGAS оценку в фоне. Результат в data/ragas/.
    Занимает 3-5 минут.
    """
    asyncio.create_task(_ragas_background(
        questions=body.questions or None,
        collection=body.collection,
    ))
    return {
        "status": "started",
        "collection": body.collection,
        "questions": len(body.questions),
        "check_results": "GET /admin/ragas/results",
    }


@router.get("/ragas/results", summary="История результатов RAGAS")
def ragas_results(last: int = 1):
    """Возвращает последние N результатов из data/ragas/."""
    from app.config import RAGAS_DIR
    files = sorted(RAGAS_DIR.glob("*.json"), reverse=True)[:last]
    if not files:
        return []
    return [json.loads(f.read_text(encoding="utf-8")) for f in files]


# ── Кэш ──────────────────────────────────────────────────────

@router.delete("/cache", summary="Очистить кэш ответов")
async def flush_cache():
    """Удаляет все закэшированные ответы из Redis (ключи cache:*)."""
    from app.services.cache import get_redis
    r = get_redis()
    keys = await r.keys("cache:*")
    if keys:
        await r.delete(*keys)
    log.info("Кэш очищен: удалено %d ключей", len(keys))
    return {"deleted_keys": len(keys)}


# ── Rate limit ────────────────────────────────────────────────

@router.get("/ratelimit", summary="Все пользователи и использование rate limit")
async def ratelimit_list():
    """Список всех активных счётчиков: user_id, использовано, осталось, TTL."""
    from app.services.cache import get_all_rate_limits
    entries = await get_all_rate_limits()
    for e in entries:
        e["whitelisted"] = e["user_id"] in RATE_LIMIT_WHITELIST
    return {"limit": RATE_LIMIT_REQUESTS, "window_days": RATE_LIMIT_DAYS, "users": entries}


@router.delete("/ratelimit/{user_id}", summary="Сбросить rate limit пользователя")
async def ratelimit_reset(user_id: int):
    """Удаляет счётчик запросов для указанного user_id."""
    from app.services.cache import reset_rate_limit
    existed = await reset_rate_limit(user_id)
    if not existed:
        raise HTTPException(status_code=404, detail=f"user_id={user_id} не найден")
    return {"user_id": user_id, "reset": True}


# ── Статус коллекций ──────────────────────────────────────────

@router.get("/collections", summary="Статус всех коллекций Qdrant")
def collections_status():
    """Количество точек во всех коллекциях."""
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    return {
        c.name: client.get_collection(c.name).points_count
        for c in client.get_collections().collections
    }
