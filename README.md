# Супервизор в кармане

> RAG-ассистент для начинающих гештальт-терапевтов.
> Отвечает на вопросы по теории и практике, опираясь на профессиональную литературу — как опытный коллега, а не поисковик.
>
> 🌐 **[psycho-pocket.com](https://psycho-pocket.com/)** · 🤖 **[@pocket\_supervisor\_bot](https://t.me/pocket_supervisor_bot)**

---

## Что это

Telegram-бот, который помогает начинающим гештальт-терапевтам разбираться в сложных ситуациях на сессии. Вместо того чтобы лезть в книгу или ждать следующей супервизии — терапевт пишет вопрос и получает развёрнутый ответ.

**Примеры вопросов:**
- *«Клиент хочет завершить терапию после двух встреч — что делать?»*
- *«Как работать с человеком, который всё время интеллектуализирует?»*
- *«Чувствую, что этот клиент меня раздражает — это нормально?»*
- *«Что такое ретрофлексия и как её распознать на сессии?»*

---

## База знаний

| Книга | Автор | Что даёт |
|---|---|---|
| *Skills in Gestalt Counselling & Psychotherapy* (3rd ed.) | Phil Joyce & Charlotte Sills | Практика ведения сессии: контакт, эксперименты, завершение |
| *Gestalt Therapy: 100 Key Points and Techniques* (2nd ed.) | Dave Mann | Концентрированный разбор ключевых идей и техник |

---

## Стек

| Компонент | Технология | Роль |
|---|---|---|
| API + Admin | **FastAPI** | REST API, Swagger UI |
| Telegram бот | **python-telegram-bot** | polling (локально) / webhook (VPS) |
| Векторная БД | **Qdrant** | хранение и поиск по эмбеддингам |
| LLM + эмбеддинги | **Google Gemini** | конвертация PDF, эмбеддинги, генерация ответов |
| Кэш | **Redis** | кэш ответов TTL 30 дней |
| Оценка качества | **RAGAS** | faithfulness, relevancy, precision |
| Оркестрация | **Docker Compose** | 4 сервиса, персистентные volumes |
| Reverse proxy | **Caddy** | SSL от Let's Encrypt, субдомены, статический лендинг |
| Деплой | **Portainer** | GitOps, автодеплой при пуше в master |

---

## Варианты запуска

### Локально — приложение без Docker

Для разработки: Redis/Qdrant/Postgres в Docker, приложение запускается напрямую.

```bash
cp .env.example .env
# Заполни GEMINI_API_KEY, TELEGRAM_BOT_TOKEN
# Хосты: REDIS_HOST=localhost, QDRANT_HOST=localhost

# Запусти инфраструктуру
docker compose up redis qdrant postgres -d

# Запусти приложение
uv run uvicorn app.main:app --reload
```

### Локально — всё в Docker

```bash
cp .env.example .env.docker
# Заполни GEMINI_API_KEY, TELEGRAM_BOT_TOKEN
# Хосты: REDIS_HOST=redis, QDRANT_HOST=qdrant

docker compose --env-file .env.docker up --build -d
```

### Продакшен (Portainer GitOps)

Portainer следит за репо и передеплоивает при пуше в `master`. Переменные задаются в Portainer UI — только секреты, остальное берётся из дефолтов в `docker-compose.yml`.

#### 1. Подготовить Docker-сеть на VM (один раз)

```bash
# Создать общую сеть для Caddy + всех ботов
docker network create caddy-public

# Подключить Portainer к этой сети (чтобы был доступен через Caddy)
docker network connect caddy-public portainer
```

#### 2. Задеплоить стек Caddy (один раз)

Репо: `https://github.com/ivproduction/caddy-proxy` — содержит `Caddyfile` + лендинг.
Добавить в Portainer → Stacks → Add stack → Repository.

#### 3. Задеплоить стек приложения

Обязательные переменные в Portainer:
```
GEMINI_API_KEY=...
TELEGRAM_BOT_TOKEN=...
ADMIN_API_KEY=...          # защищает /api/* эндпоинты
WEBHOOK_SECRET=...         # верификация запросов от Telegram
TELEGRAM_MODE=webhook
WEBHOOK_URL=https://gestalt-supervisor.psycho-pocket.com
```

Приложение автоматически подключается к сети `caddy-public` (задано в `docker-compose.yml`) — Caddy сразу видит контейнер по имени `gestalt-supervisor-app-1`.

Swagger UI: https://gestalt-supervisor.psycho-pocket.com/swagger (требует `X-API-Key`)

---

## Пайплайн добавления книги

```
1. Загрузить PDF
   POST /api/admin/files/upload

2. Конвертировать PDF → Semantic Markdown (Gemini Vision, ~2-3 мин)
   POST /api/admin/files/convert?filename=book.pdf&mode=smart&source_type=session_guides

3. Загрузить в Qdrant (эмбеддинги)
   POST /api/admin/files/ingest?filename=smart:book.txt&source_type=session_guides

4. Проверить качество поиска
   GET /api/admin/search?query=сопротивление&source_type=session_guides&mode=smart
```

**Smart vs Standard:**
- `smart` — Gemini Vision читает PDF как визуальный объект, понимает двухколоночный layout, таблицы, схемы → качество RAG выше на 30-40%
- `standard` — pymupdf4llm, быстро, но теряет структуру сложных макетов

---

## RAG пайплайн

```
вопрос пользователя
  │
  ├─→ Redis cache?  ──HIT──→  вернуть кэш (мгновенно)
  │
  MISS
  │
  ├─→ Gemini Embeddings: вопрос → вектор 768d
  ├─→ Qdrant: cosine similarity → top-5 чанков
  ├─→ Gemini: [system_prompt] + [5 чанков] + вопрос → ответ
  │
  ├─→ Redis: сохранить ответ (TTL 30 дней)
  └─→ вернуть ответ
```

**Коллекции Qdrant:** `{source_type}_{mode}` — например `session_guides_smart`

**Каналы:**
- `api` — обычный текст (для HTTP API)
- `telegram` — HTML-форматирование с эмодзи, адаптировано под мобильный экран

---

## Admin API

Swagger (локально): `http://localhost:8000/swagger`
Swagger (прод): `https://gestalt-supervisor.psycho-pocket.com/swagger`

### Управление файлами

| Метод | Endpoint | Описание |
|---|---|---|
| `POST` | `/api/admin/files/upload` | Загрузить PDF в `data/raw/` |
| `GET` | `/api/admin/files/status` | Статус всех PDF: конвертация + наличие в Qdrant |
| `POST` | `/api/admin/files/convert` | PDF → Semantic Markdown (Gemini Vision) |
| `GET` | `/api/admin/files/docs` | Список конвертированных текстов |
| `POST` | `/api/admin/files/ingest` | Текст → Qdrant (эмбеддинги) |
| `DELETE` | `/api/admin/files/ingest` | Удалить чанки файла из Qdrant |

### Отладка и обслуживание

| Метод | Endpoint | Описание |
|---|---|---|
| `GET` | `/api/admin/search` | Семантический поиск (проверка качества) |
| `GET` | `/api/admin/collections` | Статус коллекций Qdrant |
| `DELETE` | `/api/admin/cache` | Сбросить Redis кэш |

### RAGAS оценка качества

| Метод | Endpoint | Описание |
|---|---|---|
| `POST` | `/api/admin/ragas` | Запустить оценку (фоново, ~3-5 минут) |
| `GET` | `/api/admin/ragas/results` | Последние N результатов |

**Метрики RAGAS:**
- `faithfulness` — ответ основан на контексте (нет галлюцинаций)
- `answer_relevancy` — ответ релевантен вопросу
- `context_precision` — найденные чанки действительно нужны

**Последние результаты (2026-03-27):**
```
faithfulness:      0.692   (~30% ответов содержат выводы из общих знаний модели)
answer_relevancy:  0.767   (ответы по теме, есть куда расти)
context_precision: 1.000   (Qdrant находит только нужные чанки — отлично)
```

---

## Telegram бот

**Команды:**
- `/start` — приветствие с примерами вопросов
- `/help` — описание системы, список книг, примеры ситуаций

**Режимы запуска** (переключается через `TELEGRAM_MODE`):
- `polling` — для локальной разработки, не нужен публичный URL
- `webhook` — для прода (Caddy + SSL), Telegram шлёт запросы напрямую на сервер; верифицируется через `X-Telegram-Bot-Api-Secret-Token`

---

## Docker сервисы

| Сервис | Образ | Порт | Данные |
|---|---|---|---|
| `app` | python:3.11-slim | 8000 (внутри сети) | `app_data:/app/data` |
| `redis` | redis:7-alpine | 6379 | `redis_data:/data` |
| `qdrant` | qdrant/qdrant | 6333 | `qdrant_data:/qdrant/storage` |
| `postgres` | postgres:16-alpine | 5432 | `postgres_data:/var/lib/postgresql/data` |

Все данные хранятся в Docker volumes — переживают `docker compose down`.

---

## Переменные окружения

| Переменная | По умолчанию | Описание |
|---|---|---|
| `GEMINI_API_KEY` | — | API ключ Google Gemini (обязательно) |
| `TELEGRAM_BOT_TOKEN` | — | Токен бота от @BotFather (обязательно) |
| `TELEGRAM_MODE` | `polling` | `polling` или `webhook` |
| `WEBHOOK_URL` | — | Публичный HTTPS-адрес (только для webhook) |
| `WEBHOOK_PATH` | `/webhook/gestalt-supervisor` | Путь вебхука |
| `RAG_RESPONSE_MODEL` | `gemini-3-flash-preview` | Модель генерации ответов |
| `PDF_PROCESSING_MODEL` | `gemini-1.5-flash` | Модель конвертации PDF |
| `EMBEDDING_MODEL` | `gemini-embedding-2-preview` | Модель эмбеддингов |
| `EMBEDDING_DIMENSION` | `768` | Размерность вектора |
| `TOP_K` | `5` | Количество чанков для контекста |
| `ADMIN_API_KEY` | — | API ключ для `/api/*` эндпоинтов (обязательно в проде) |
| `WEBHOOK_SECRET` | — | Secret token для верификации Telegram webhook |
| `CACHE_TTL_DAYS` | `30` | TTL кэша ответов (дней) |
| `LOG_TO_FILE` | `false` | Писать логи в `app.log` |

---

## Структура проекта

```
guide/
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── .env.example          ← шаблон переменных
├── .env.docker           ← переменные для Docker
│
├── app/
│   ├── main.py           ← FastAPI + lifespan (бот) + webhook route
│   ├── config.py         ← все настройки из .env
│   │
│   ├── api/
│   │   ├── admin.py      ← /api/admin/*
│   │   └── chat.py       ← /api/app/*
│   │
│   ├── bot/
│   │   └── handlers.py   ← Telegram: команды, обработка сообщений
│   │
│   ├── services/
│   │   ├── rag.py        ← RAG пайплайн
│   │   ├── search.py     ← поиск в Qdrant
│   │   └── cache.py      ← Redis кэш
│   │
│   ├── ingest/
│   │   ├── smart.py      ← Gemini Vision → Semantic Markdown
│   │   └── standard.py   ← pymupdf4llm → текст
│   │
│   ├── ragas/
│   │   ├── eval.py       ← оценка качества
│   │   └── questions.py  ← тест-вопросы (редактируй здесь)
│   │
│   └── vector_store.py   ← чанкинг + эмбеддинг + Qdrant
│
└── data/                 ← Docker volume (персистентно)
    ├── raw/              ← исходные PDF
    ├── docs/
    │   ├── smart/        ← Semantic Markdown
    │   └── standard/     ← plain text
    └── ragas/            ← JSON-отчёты оценки
```

---

## Что дальше (TODO)

- **История диалога** — бот будет помнить контекст разговора с конкретным терапевтом
- **Персонализация** — адаптация ответа под историю пользователя
- **База пользователей** — PostgreSQL: регистрация, подписки
- **Голосовые сообщения** — Gemini Audio API
- **Перевод базы знаний** — русскоязычные чанки для лучшего поиска
