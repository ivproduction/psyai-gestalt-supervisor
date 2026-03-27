"""
api/admin.py — Admin API.
Swagger UI: http://localhost:8000/swagger
Префикс: /api/admin
"""

import asyncio
import json
import logging
import traceback
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, UploadFile, File, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue, Range

from app.config import ADMIN_API_KEY, DOCS_DIR, QDRANT_HOST, QDRANT_PORT, RAW_DIR, collection_name
from app.ingest import convert_file
from app.ragas import evaluate_rag
from app.ragas.questions import QUESTIONS as _DEFAULT_QUESTIONS
from app.services.search import search as qdrant_search
from app.vector_store import delete_file_chunks, ingest_to_qdrant

log = logging.getLogger(__name__)

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)


async def require_api_key(key: str = Security(_api_key_header)):
    if key != ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")


router = APIRouter(prefix="/api/admin", tags=["admin"])


# ── 1. Загрузка файла ──────────────────────────────────────────

@router.post("/files/upload", summary="Загрузить PDF в data/raw/")
async def upload_file(file: UploadFile = File(...)):
    """Загружает PDF. Поддерживает русские имена и пробелы."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Только PDF файлы")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    dest = RAW_DIR / file.filename
    dest.write_bytes(await file.read())

    size_mb = round(dest.stat().st_size / 1024 / 1024, 2)
    log.info("Загружен файл: %s (%.2f MB)", file.filename, size_mb)
    return {"filename": file.filename, "size_mb": size_mb, "path": str(dest)}


# ── 2. Список файлов со статусом ──────────────────────────────

@router.get("/files/status", summary="PDF файлы: статус конвертации и эмбеддингов")
def list_raw_files():
    """
    Все PDF из data/raw/ с полным статусом:
    - размер и дата загрузки
    - конвертирован ли в текст (standard/smart)
    - загружен ли в Qdrant (коллекция, кол-во чанков, превью)
    """
    pdf_files = sorted(RAW_DIR.glob("*.pdf"))
    if not pdf_files:
        return []

    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    existing_collections = {c.name for c in client.get_collections().collections}

    result = []
    for pdf_path in pdf_files:
        stat = pdf_path.stat()
        entry = {
            "filename": pdf_path.name,
            "size_mb": round(stat.st_size / 1024 / 1024, 2),
            "uploaded_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "converted": {},
            "embeddings": {},
        }

        for mode in ("standard", "smart"):
            safe_stem = pdf_path.stem.replace(" ", "_")
            meta_path = DOCS_DIR[mode] / f"{safe_stem}.meta.json"
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                entry["converted"][mode] = {
                    "chars": meta.get("char_count"),
                    "source_type": meta.get("source_type"),
                }

        file_filter = Filter(
            must=[FieldCondition(key="source_file", match=MatchValue(value=pdf_path.name))]
        )
        for coll_name in existing_collections:
            try:
                count_result = client.count(
                    collection_name=coll_name,
                    count_filter=file_filter,
                    exact=True,
                )
                if count_result.count > 0:
                    first3_filter = Filter(must=[
                        FieldCondition(key="source_file", match=MatchValue(value=pdf_path.name)),
                        FieldCondition(key="chunk_index", range=Range(gte=0, lte=2)),
                    ])
                    points, _ = client.scroll(
                        collection_name=coll_name,
                        scroll_filter=first3_filter,
                        limit=3,
                        with_payload=True,
                        with_vectors=False,
                    )
                    points = sorted(points, key=lambda p: p.payload.get("chunk_index", 0))
                    payload = points[0].payload if points else {}
                    coll_info = client.get_collection(coll_name)
                    entry["embeddings"][coll_name] = {
                        "collection": coll_name,
                        "chunks": count_result.count,
                        "source_type": payload.get("source_type"),
                        "mode": payload.get("mode"),
                        "vector_size": coll_info.config.params.vectors.size,
                        "distance": coll_info.config.params.vectors.distance.name,
                        "samples": [
                            {
                                "chunk_index": p.payload.get("chunk_index"),
                                "text_preview": p.payload.get("text", "")[:200],
                            }
                            for p in points
                        ],
                    }
            except Exception as e:
                log.warning("Ошибка при проверке коллекции %s: %s", coll_name, e)

        result.append(entry)

    return result


# ── 3b. Конвертация PDF → Semantic Markdown ───────────────────

@router.post("/files/convert", summary="PDF → Semantic Markdown (data/docs/)")
def convert_file_endpoint(
    filename: str,
    mode: Literal["standard", "smart"] = "smart",
    source_type: str = "session_guides",
):
    """
    Шаг 1: конвертирует PDF в текст и сохраняет в data/docs/{mode}/.

    - **filename** — имя PDF из data/raw/ (см. GET /admin/files/raw)
    - **mode** — `smart` (Gemini Vision, медленно, качественно) или `standard` (быстро)
    - **source_type** — метка источника: `session_guides`, `therapist_finder`, ...

    После успеха используй POST /admin/files/ingest для загрузки в Qdrant.
    """
    pdf_path = RAW_DIR / filename
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail=f"Файл не найден в data/raw/: {filename}")

    log.info("=== CONVERT [%s / %s] %s ===", source_type, mode, filename)
    try:
        result = convert_file(pdf_path, mode, source_type)
    except Exception as e:
        log.exception("Ошибка конвертации %s: %s", filename, e)
        raise HTTPException(status_code=500, detail=f"Ошибка конвертации: {e}")

    log.info("=== CONVERT готово: %d символов ===", result["chars"])
    return {
        "filename": filename,
        "mode": mode,
        "source_type": source_type,
        "output": result["output"],
        "chars": result["chars"],
    }


# ── 3c. Список файлов для инжеста ────────────────────────────

@router.get("/files/docs", summary="Список текстов для инжеста (data/docs/)")
def list_doc_files():
    """
    Возвращает имена файлов в data/docs/ с префиксом режима.

    Формат: `smart:filename.txt` или `standard:filename.txt`
    """
    return _list_doc_files()


# ── 3d. Инжест текста → Qdrant ────────────────────────────────

def _list_doc_files() -> list[str]:
    result = []
    for mode in ("smart", "standard"):
        for f in sorted(DOCS_DIR[mode].glob("*.txt")):
            result.append(f"{mode}:{f.name}")
    return result


@router.post("/files/ingest", summary="Semantic Markdown → Qdrant (эмбеддинги)")
def ingest_file(
    filename: str,
    source_type: str = "session_guides",
):
    """
    Шаг 2: загружает текст из data/docs/ в Qdrant.

    - **filename** — файл с префиксом режима. Доступные варианты:
    """
    available = _list_doc_files()

    # парсим mode из префикса: "smart:file.txt" → mode=smart, name=file.txt
    if ":" not in filename:
        raise HTTPException(
            status_code=400,
            detail=f"Укажи режим через префикс: smart:file.txt или standard:file.txt. Доступно: {available}"
        )
    mode, name = filename.split(":", 1)
    if mode not in ("smart", "standard"):
        raise HTTPException(status_code=400, detail=f"Режим должен быть smart или standard, получено: {mode}")

    txt_path = DOCS_DIR[mode] / name
    if not txt_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Файл не найден в data/docs/{mode}/: {name}. Доступно: {available}"
        )

    text = txt_path.read_text(encoding="utf-8")
    source_file = name.removesuffix(".txt") + ".pdf"

    log.info("=== INGEST [%s / %s] %s ===", source_type, mode, name)
    try:
        chunks = ingest_to_qdrant(text, source_file, source_type, mode)
    except Exception as e:
        log.exception("Ошибка эмбеддинга %s: %s", name, e)
        raise HTTPException(status_code=500, detail=f"Ошибка эмбеддинга: {e}")

    coll = collection_name(source_type, mode)
    log.info("=== INGEST готово: %d чанков → %s ===", chunks, coll)
    return {
        "filename": name,
        "mode": mode,
        "source_type": source_type,
        "collection": coll,
        "chunks": chunks,
        "available": available,
    }


# ── 4. Удаление RAG данных файла ──────────────────────────────

@router.delete("/files/ingest", summary="Удалить эмбеддинги файла из Qdrant")
def delete_ingest(
    filename: str,
    source_type: str = "session_guides",
    mode: Literal["standard", "smart"] = "smart",
):
    """
    Удаляет все чанки файла из указанной коллекции.
    Исходный PDF и .txt файл не удаляются.
    """
    deleted = delete_file_chunks(filename, source_type, mode)
    coll = collection_name(source_type, mode)
    log.info("Удалено %d чанков файла '%s' из '%s'", deleted, filename, coll)
    return {"filename": filename, "collection": coll, "deleted_chunks": deleted}


# ── Поиск (дебаг) ─────────────────────────────────────────────

@router.get("/search", summary="Семантический поиск (дебаг)")
def search(
    query: str,
    source_type: str = "session_guides",
    mode: Literal["standard", "smart"] = "smart",
    top_k: int = 5,
    source_file: str | None = None,
):
    """
    Проверка качества после ingest.

    - **source_type** — тип источника (session_guides, ...)
    - **mode** — коллекция: smart или standard
    - **source_file** — фильтр по файлу (необязательно)
    """
    try:
        results = qdrant_search(
            query=query, source_type=source_type, mode=mode,
            top_k=top_k, source_file=source_file,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"query": query, "collection": collection_name(source_type, mode), "results": results}


# ── RAGAS оценка качества ─────────────────────────────────────

class RagasRequest(BaseModel):
    source_type: str = "session_guides"
    mode: Literal["standard", "smart"] = "smart"
    questions: list[str] = Field(
        default_factory=lambda: list(_DEFAULT_QUESTIONS),
        description="Вопросы для оценки. Каждый вопрос — строка на русском из предметной области.",
    )


async def _ragas_background(questions, source_type, mode):
    from app.config import RAGAS_DIR
    try:
        await evaluate_rag(questions=questions, source_type=source_type, mode=mode)
    except Exception as e:
        log.error("RAGAS фоновая ошибка: %s", e, exc_info=True)
        RAGAS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        err_path = RAGAS_DIR / f"{source_type}_{mode}_{ts}.json"
        err_path.write_text(json.dumps({
            "timestamp": datetime.now().isoformat(),
            "collection": f"{source_type}_{mode}",
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
    Запускает RAGAS оценку в фоне и сразу возвращает ответ.
    Результат сохраняется в `data/ragas/`.

    Метрики:
    - **faithfulness** — ответ основан на контексте (нет галлюцинаций)
    - **answer_relevancy** — ответ релевантен вопросу
    - **context_precision** — retrieved чанки действительно нужны

    Вопросы по умолчанию — из `app/ragas/questions.py`. Занимает 3-5 минут.
    """
    asyncio.create_task(_ragas_background(
        questions=body.questions or None,
        source_type=body.source_type,
        mode=body.mode,
    ))
    return {
        "status": "started",
        "collection": f"{body.source_type}_{body.mode}",
        "questions": len(body.questions),
        "check_results": "GET /admin/ragas/results",
        "hint": "Займёт 3-5 минут. Следи за логами или проверяй результаты по ссылке выше.",
    }


@router.get("/ragas/results", summary="История результатов RAGAS")
def ragas_results(last: int = 1):
    """
    Возвращает последние N результатов оценки из data/ragas/.

    - **last** — сколько последних запусков показать (по умолчанию 1)
    """
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


# ── Статус коллекций ──────────────────────────────────────────

@router.get("/collections", summary="Статус всех коллекций Qdrant")
def collections_status():
    """Количество точек во всех коллекциях."""
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    return {
        c.name: client.get_collection(c.name).points_count
        for c in client.get_collections().collections
    }
