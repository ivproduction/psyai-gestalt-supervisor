# Супервизор в кармане — План реализации

## Этапы

### Этап 1. Инфраструктура ✅
- [x] `docker-compose.yml` — 4 сервиса: app, redis, qdrant, postgres
- [x] `.env.example` — все переменные окружения
- [x] `Dockerfile` с uv
- [x] Проверка: `docker compose up` — все сервисы стартуют

### Этап 2. Подготовка данных ✅
- [x] `ingest_standard.py` — pymupdf4llm → очистка → `data/docs/standard/`
- [x] `ingest_smart.py` — Gemini Vision → Semantic Markdown → `data/docs/smart/`
- [x] Данные: `smart/joyce_sills.txt` (247k), `smart/mann_100_key_points.txt` (41k)
- [x] Проверка: качество smart >> standard (566 чанков vs 15 для joyce_sills)

### Этап 3. База данных ⏳ (пропущен пока)
- [ ] `app/db/models.py` — SQLAlchemy модели (users, subscriptions, audio_messages, evaluations)
- [ ] `app/db/database.py` — подключение к PostgreSQL
- [ ] `app/db/migrations/` — Alembic, первая миграция
- [ ] Проверка: `alembic upgrade head` — таблицы созданы

### Этап 4. Векторное хранилище ✅
- [x] `app/vector_store.py` — Qdrant + чанкинг (800/100) + эмбеддинги Gemini
- [x] `app/config.py` — все настройки из env
- [x] Данные в Qdrant: `gestalt_smart` = 648 чанков, `gestalt_standard` = 82 чанка

### Этап 5. Кэш и история ⬜
- [ ] `app/cache.py` — Redis кэш ответов (TTL 30д) + история (28 сообщ, TTL 14д)
- [ ] Проверка: сохранить/получить из кэша, проверить TTL

### Этап 6. RAG пайплайн ⬜
- [ ] `app/rag_pipeline.py` — поиск в Qdrant + двухшаговая генерация через Gemini
- [ ] Проверка: задать вопрос, получить ответ, повторить — второй раз из кэша

### Этап 7. Admin API ✅ (частично)
- [x] `app/admin.py` — FastAPI + Swagger UI на порту 8000
- [x] `POST /admin/convert` — PDF → текст
- [x] `POST /admin/embed` — текст → Qdrant
- [x] `GET /admin/collections` — статус коллекций
- [ ] `POST /admin/search` — тестовый поиск по вопросу
- [ ] `POST /admin/cache/flush` — сброс Redis
- [ ] `POST /admin/ragas` — запуск оценки качества

### Этап 8. Telegram бот ⬜
- [ ] `app/main.py` — handlers, регистрация пользователя, отправка вопроса в пайплайн
- [ ] Проверка: написать боту вопрос, получить ответ

---

## Текущий этап

**→ Этап 5 + 6: cache.py + rag_pipeline.py**

Рекомендуемый порядок:
1. `app/cache.py` — Redis
2. `app/rag_pipeline.py` — поиск + генерация
3. `POST /admin/search` в admin.py — проверить в Swagger
4. Потом DB (Этап 3) и бот (Этап 8)
