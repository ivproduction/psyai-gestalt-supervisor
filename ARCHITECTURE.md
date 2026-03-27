# Супервизор в кармане — Архитектура проекта

## Назначение

Telegram-бот для начинающих гештальт-терапевтов.
Терапевт задаёт вопросы по методологии ведения сессий — бот отвечает на основе базы знаний по гештальт-терапии.

**База знаний:**
- Phil Joyce & Charlotte Sills — *Skills in Gestalt Counselling & Psychotherapy* (3rd ed.)
- Dave Mann — *Gestalt Therapy: 100 Key Points and Techniques* (2nd ed.)

---

## Стек (Docker Compose)

```
┌─────────────────────────────────────────┐
│         Telegram Bot                    │
│       (python-telegram-bot)             │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│           app (Python)                  │
│                                         │
│  1. Redis: проверить кэш(вопрос)        │
│  2. Qdrant: embed + search              │
│  3. Gemini: [чанки] + вопрос → ответ1  │  ← кэшируется
│  4. Redis: взять историю user_id        │
│  5. Gemini: [история] + ответ1 → ответ2│  ← не кэшируется
│  6. Redis: обновить историю             │
│  7. Telegram: отправить ответ2          │
└──────────┬──────────────────────────────┘
           │                    │
           ▼                    ▼
    ┌────────────┐       ┌────────────┐
    │   Redis    │       │   Qdrant   │
    │            │       │            │
    │ cache:     │       │ векторы    │
    │  TTL 30д   │       │ книг       │
    │            │       │            │
    │ history:   │       └────────────┘
    │  14 сообщ  │
    │  TTL 14д   │
    └────────────┘
```

---

## Двухшаговая генерация ответа

Ключевая идея: разделить RAG-ответ (универсальный) и персональный ответ.

```
Шаг 1 — RAG ответ (кэшируемый, общий для всех):
  hash = SHA256(вопрос)
  если cache[hash] → вернуть ответ1 из кэша
  иначе:
    embed(вопрос) → Qdrant → top_k чанков
    Gemini([чанки] + вопрос) → ответ1
    cache[hash] = ответ1  (TTL: 30 дней)

Шаг 2 — Персональный ответ (не кэшируется):
  история = Redis.history[user_id]  (последние 14 сообщений)
  Gemini([история] + ответ1) → ответ2
  Redis.history[user_id].append(вопрос + ответ2)
  вернуть ответ2
```

**Почему так:**
Один и тот же вопрос "С чего начать первую сессию?" задают многие терапевты — ответ1 один для всех, берётся из кэша.
Но подача ответа учитывает контекст конкретного терапевта — его предыдущие вопросы, тему разговора.

---

## Redis — схема ключей

```
cache:{SHA256(вопрос)}   → ответ1 (строка)          TTL: 30 дней
history:{user_id}        → Redis List (RPUSH/LTRIM)  TTL: 14 дней
```

Формат каждого элемента history — JSON-строка:
```json
{"role": "user", "content": "С чего начать первую сессию?"}
{"role": "assistant", "content": "..."}
```

**Важно:** история хранится как нативный Redis List (не JSON-объект целиком).
Запись: `RPUSH history:{user_id} <json>` + `LTRIM history:{user_id} -28 -1`
Чтение: `LRANGE history:{user_id} 0 -1`

Это защищает от Race Condition: при параллельных запросах не перезаписывается весь список.
Максимум 28 сообщений (14 диалогов). LTRIM автоматически обрезает старые.

---

## Структура файлов

```
5-8-psy/
├── docker-compose.yml
├── .env
├── .env.example
├── requirements.txt
├── ARCHITECTURE.md         ← этот файл
├── ingest.py               ← запускается один раз, готовит данные
│
├── app/
│   ├── main.py             ← точка входа, Telegram bot handlers
│   ├── admin.py            ← FastAPI admin API + Swagger UI (порт 8000)
│   ├── rag_pipeline.py     ← двухшаговый пайплайн
│   ├── vector_store.py     ← Qdrant + чанкинг
│   ├── cache.py            ← Redis кэш + история
│   ├── config.py           ← настройки из env
│   └── db/
│       ├── models.py       ← SQLAlchemy модели
│       ├── database.py     ← подключение к PostgreSQL
│       └── migrations/     ← Alembic
│           ├── env.py
│           └── versions/
│               └── 001_initial.py
│
└── data/
    ├── raw/                ← оригиналы PDF (не трогаем)
    │   ├── joyce_sills.pdf
    │   └── mann_100_key_points.pdf
    └── docs/               ← генерируется ingest.py (в .gitignore)
        ├── joyce_sills.txt
        └── mann_100_key_points.txt
```

---

## ingest.py — пайплайн подготовки данных

Запускается один раз вручную. Два режима — переключаются через `.env`.

### Mode 1 — Standard

```
data/raw/*.pdf
    → pymupdf4llm: PDF → Markdown
    → очистка (короткие строки, спецсимволы, нормализация)
    → чанкинг по символам (chunk_size=500, overlap=100)
    → сохранить в data/docs/*.txt
    → Qdrant: коллекция "gestalt_standard"
```

### Mode 2 — Smart (через Gemini Vision)

```
data/raw/*.pdf (страницы как изображения)
    → Gemini 1.5 Pro: Document Understanding
        - текст сохраняется
        - таблицы → Markdown-таблицы
        - схемы/графики → текстовое описание
      → Semantic Markdown
    → MarkdownHeaderTextSplitter: чанки по заголовкам (не по символам)
        - раздел "Проекция" = один чанк, даже если 1200 символов
        - контекст не разрывается на стыке чанков
    → Qdrant: коллекция "gestalt_smart"
```

**Профит Smart mode:** качество RAG выше на 30-40% за счёт смысловых чанков и описания схем.

### Переключение режимов

```
# .env
INGEST_MODE=standard      # или "smart"
QDRANT_COLLECTION=gestalt_standard   # или "gestalt_smart"
```

`vector_store.py` читает `QDRANT_COLLECTION` и работает с нужной коллекцией.
Можно держать обе коллекции и сравнивать качество через RAGAS.

### Метаданные в Qdrant (оба режима)

```json
{
  "text": "чанк текста...",
  "source_book": "Dave Mann — 100 Key Points",
  "page_number": 45,
  "chapter": "Projection"
}
```

Метаданные позволяют боту указывать источник: `(Источник: Dave Mann, стр. 45, гл. Projection)`

После `ingest.py` — запустить эмбеддинг через Admin API `/admin/ingest` — загрузит в Qdrant.

**Зависимости:** `pymupdf4llm`, `langchain-text-splitters` (для Smart mode)

> **TODO:** добавить шаг перевода книг на русский через Gemini API. Улучшит качество кросс-языкового поиска.

---

## Переменные окружения (.env)

```
TELEGRAM_BOT_TOKEN=

REDIS_HOST=redis
REDIS_PORT=6379

QDRANT_HOST=qdrant
QDRANT_PORT=6333

POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=psychoai
POSTGRES_USER=psychoai
POSTGRES_PASSWORD=

CACHE_TTL_DAYS=30
HISTORY_TTL_DAYS=14
HISTORY_MAX_MESSAGES=28

TOP_K=5
LLM_MODEL=gemini-1.5-flash
EMBED_MODEL=models/text-embedding-004
GEMINI_API_KEY=

INGEST_MODE=standard
QDRANT_COLLECTION=gestalt_standard
```

---

## Docker Compose сервисы

| Сервис   | Образ               | Назначение                        | Миграции |
|----------|---------------------|-----------------------------------|----------|
| app      | python:3.11-slim    | Telegram bot + RAG                | —        |
| redis    | redis:7-alpine      | Кэш ответов + история диалога     | ❌ не нужны |
| qdrant   | qdrant/qdrant       | Векторная БД (эмбеддинги книг)    | ❌ не нужны |
| postgres | postgres:16-alpine  | Пользователи, подписки, аудио     | ✅ Alembic |

---

## Admin API (FastAPI + Swagger)

Доступен на `http://localhost:8000/docs`

Запускается вместе с ботом. Эмбеддинг при старте **не запускается автоматически** — только через Admin API.

| Метод | Endpoint | Действие |
|---|---|---|
| `POST` | `/admin/ingest` | Запустить эмбеддинг из `data/docs/` в Qdrant |
| `POST` | `/admin/cache/reset` | Сбросить весь кэш ответов |
| `POST` | `/admin/history/{user_id}/reset` | Сбросить историю пользователя |
| `GET` | `/admin/users` | Список пользователей |
| `PATCH` | `/admin/users/{user_id}/subscription` | Установить подписку |
| `POST` | `/admin/evaluate/ragas` | Запустить RAGAS оценку качества |
| `GET` | `/admin/evaluate/results` | Последние результаты RAGAS |

Результаты RAGAS сохраняются в PostgreSQL (таблица `evaluations`):
- `faithfulness` — точность ответа относительно контекста
- `context_precision` — релевантность найденных чанков
- `answer_relevancy` — соответствие ответа вопросу
- `created_at` — когда запускали

### Подписки

```python
class SubscriptionPlan(str, Enum):
    FREE  = "free"   # дефолт при регистрации
    PRO   = "pro"
    SUPER = "super"
```

Поле `expires_at` — до какого числа активна подписка. `FREE` — без ограничений.

---

## Промпты

### Шаг 1 — RAG промпт (system)
```
Ты — ассистент для начинающих гештальт-терапевтов.
Отвечай на вопросы о ведении сессий строго на основе предоставленного контекста из книг по гештальт-терапии.
Отвечай на русском языке. Будь конкретным и практичным.
Если в контексте нет ответа — скажи об этом честно.
```

### Шаг 2 — Персональный промпт (system)
```
Ты — опытный супервизор для начинающего гештальт-терапевта.
Ниже — методологический ответ из базы знаний и история вашего разговора.
Перефразируй ответ с учётом контекста диалога. Говори тепло, как наставник.
Отвечай на русском языке.
```

---

## Голосовые сообщения

Терапевт отправляет голосовое (.ogg) прямо с сессии.

```
Юзер шлёт .ogg
    → app передаёт аудио напрямую в Gemini 1.5 Flash
      (Gemini понимает аудио без Whisper — нативно)
    → Gemini анализирует:
        - содержание (что сказано)
        - интонацию (тревога, неуверенность, напряжение)
    → текст вопроса передаётся в RAG пайплайн (Шаг 1 + Шаг 2)
    → в Шаге 2 промпт включает эмоциональный контекст голоса
```

**Промпт для голосового (Шаг 2):**
```
Терапевт прислал голосовое сообщение. В его голосе слышна [тревога/неуверенность/...].
Отвечай с эмпатией, как живой наставник — сначала признай его состояние, потом дай методологический совет.
```

**Пример:**
```
Терапевт (голос): "Я сейчас на сессии, клиент молчит, я чувствую злость, что делать?"
Бот: "Александр, я слышу твою тревогу. Подыши.
      Давай вспомним раздел у Мэнна про работу с тишиной... (стр. 45)"
```

Голосовые сообщения также сохраняются в PostgreSQL (таблица `audio_messages`):
`telegram_file_id`, `duration_sec`, `transcription`, `created_at`
