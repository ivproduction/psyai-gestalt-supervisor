# Text-first Ingest Workflow Implementation Plan

**Goal:** Убрать PDF-workflow целиком, заменить на загрузку готовых текстовых файлов прямо в Qdrant за один шаг. Коллекция = имя файла без расширения.

**Architecture:** Новый `POST /files/ingest` принимает `.txt`/`.md`, сохраняет в `data/docs/{collection}/`, сразу загружает в Qdrant. `DELETE /collections/{name}` дропает коллекцию и директорию. RAG-сервис читает коллекцию из env `RAG_COLLECTION` вместо `source_type`+`mode`.

---

## Карта файлов

| Файл | Действие | Что меняется |
|---|---|---|
| `app/config.py` | Modify | убрать `DOCS_DIR` dict, `RAW_DIR`, `PDF_PROCESSING_MODEL`, `collection_name()`, `LEGACY_COLLECTIONS`; добавить `DOCS_DIR = Path("data/docs")`, `RAG_COLLECTION` |
| `app/vector_store.py` | Modify | убрать `mode` из `ingest_to_qdrant`, всегда Markdown-сплиттер; заменить `delete_file_chunks` на `delete_collection` |
| `app/services/search.py` | Modify | заменить `source_type`+`mode` → `collection: str` |
| `app/services/rag.py` | Modify | заменить `source_type`+`mode` → `collection` из `RAG_COLLECTION` |
| `app/api/admin.py` | Modify | удалить PDF/convert эндпоинты, переписать ingest, добавить `DELETE /collections/{name}`, `GET /files/list`, упростить search/ragas |
| `app/api/chat.py` | Modify | убрать `source_type`+`mode` из `/ask` |
| `app/bot/handlers.py` | Modify | убрать `source_type`+`mode` из вызова `rag_ask` |
| `app/ragas/eval.py` | Modify | `evaluate_rag(collection=...)` вместо `source_type`+`mode` |
| `app/ingest/` | Delete | весь модуль (standard.py, smart.py, _common.py, __init__.py) |
| `tests/test_admin_ingest.py` | Create | тесты нового ingest endpoint |

---

## Task 1: Обновить config.py

- Убрать: `DOCS_DIR` dict, `RAW_DIR`, `PDF_PROCESSING_MODEL`, `collection_name()`, `LEGACY_COLLECTIONS`, `DEFAULT_SKIP_HEADERS`
- Добавить: `RAG_COLLECTION: str = os.getenv("RAG_COLLECTION", "session_guides")`
- Изменить: `DOCS_DIR = Path("data/docs")` (плоский путь, не словарь)
- Добавить `RAG_COLLECTION` в `.env.example`

## Task 2: Обновить vector_store.py

- `ingest_to_qdrant(text, source_file, collection)` — убрать `source_type`, `mode`; всегда MarkdownHeaderTextSplitter
- Payload: `{text, source_file, chunk_index}` — без `source_type`, без `mode`
- Убрать `delete_file_chunks`, добавить `delete_collection(collection: str) -> None`
- `embed_texts` использует `task_type="retrieval_document"`
- Тесты: `tests/test_vector_store.py` (4 теста)

## Task 3: Обновить services/search.py

- Новая сигнатура: `search(query, collection, top_k, source_file=None)`
- Убрать: `source_type`, `mode`, импорт `collection_name`, `Literal`
- Передавать `collection` напрямую в `_qdrant.query_points(collection_name=collection)`
- Результат без поля `source_type`
- Тест: `tests/test_search.py`

## Task 4: Обновить rag.py, chat.py, bot/handlers.py

- `rag.py`: `ask(question, user_id, collection=None, ...)` — если `collection is None`, брать из `RAG_COLLECTION`; убрать `source_type`+`mode`
- `chat.py`: убрать `source_type`+`mode` из `/ask`, коллекция из env
- `bot/handlers.py`: вызов `rag_ask(question, user_id, channel="telegram")` без `source_type`+`mode`

## Task 5: Обновить ragas/eval.py

- `evaluate_rag(questions=None, collection=None, top_k=TOP_K)`
- Если `collection is None` → брать из `RAG_COLLECTION`
- Убрать `source_type`+`mode` везде внутри функции

## Task 6: Переписать api/admin.py

- `POST /files/ingest` — принимает `.txt`/`.md`, коллекция = stem файла, сохраняет в `data/docs/{collection}/`, сразу ingest
- `GET /files/list` — список файлов с количеством чанков
- `DELETE /collections/{name}` — удаляет Qdrant-коллекцию и директорию
- `GET /search` — принимает `collection: str` (не `source_type`+`mode`)
- `POST /ragas` — `RagasRequest(collection: str, questions: list)`
- Убрать: все PDF/convert эндпоинты, `upload`, `files/status`, `files/docs`, `files/raw`
- Тесты: `tests/test_admin_ingest.py` (3 теста)

## Task 7: Удалить app/ingest/

- Убедиться что нет импортов: `grep -r "from app.ingest" app/`
- `rm -rf app/ingest/`
- Запустить все тесты

## Task 8: Smoke-тест

- `python -c "from app.main import app; print('OK')"` — без ошибок
- `grep -r "source_type\|RAW_DIR\|collection_name(" app/` — пустой вывод
- Добавить `RAG_COLLECTION=session_guides` в `.env`
