# Супервизор в кармане

RAG-ассистент для начинающих гештальт-терапевтов. Отвечает на вопросы по теории и практике, опираясь на базу знаний из книг по гештальт-терапии.

## Стек

- **FastAPI** — REST API + Swagger UI
- **Qdrant** — векторное хранилище чанков
- **Gemini** — эмбеддинги + генерация ответов
- **Redis** — кэш ответов (TTL 30 дней)
- **RAGAS** — оценка качества RAG пайплайна
- **Docker Compose** — оркестрация сервисов

## Быстрый старт

```bash
cp .env.docker .env.docker  # настрой API ключи
docker compose up --build -d
```

Swagger UI: http://localhost:8000/docs

## Локальная разработка

```bash
cp .env.docker .env         # скопируй и поправь хосты на localhost
uv run uvicorn app.main:app --reload --port 8005
```

Swagger UI: http://localhost:8005/docs

## Структура

```
app/
├── api/
│   ├── admin.py     # /admin/* — загрузка файлов, инжест, поиск, RAGAS
│   └── chat.py      # /app/* — RAG чат
├── ragas/
│   ├── eval.py      # логика RAGAS оценки
│   └── questions.py # тест-вопросы (редактируй здесь)
├── services/
│   ├── rag.py       # RAG пайплайн: поиск + генерация
│   ├── search.py    # семантический поиск по Qdrant
│   └── cache.py     # Redis кэш
├── ingest/          # конвертация PDF → текст (standard / smart)
├── vector_store.py  # чанкинг + эмбеддинг + загрузка в Qdrant
└── config.py        # конфигурация из .env

data/
├── raw/             # исходные PDF
├── docs/            # конвертированные тексты
└── ragas/           # отчёты RAGAS оценки
```

## Коллекции Qdrant

Имя коллекции: `{source_type}_{mode}`

Примеры: `session_guides_smart`, `session_guides_standard`

## RAG пайплайн

```
вопрос → Gemini Embeddings → Qdrant top-5 → Gemini Flash → ответ → Redis кэш
```

## RAGAS оценка

```bash
# Запустить оценку (фоново, 3-5 минут)
POST /admin/ragas

# Проверить результаты
GET /admin/ragas/results?last=1
```

Метрики:
- **faithfulness** — ответ основан на контексте (нет галлюцинаций)
- **answer_relevancy** — ответ релевантен вопросу
- **context_precision** — найденные чанки действительно нужны

## Переменные окружения

| Переменная | Описание |
|---|---|
| `GEMINI_API_KEY` | API ключ Google Gemini |
| `EMBEDDING_MODEL` | модель для эмбеддингов |
| `RAG_RESPONSE_MODEL` | модель для генерации ответов |
| `PDF_PROCESSING_MODEL` | модель для конвертации PDF (smart mode) |
| `TOP_K` | количество чанков для контекста |
| `CACHE_TTL_DAYS` | TTL кэша ответов |
| `LOG_TO_FILE` | писать логи в app.log (только локально) |
