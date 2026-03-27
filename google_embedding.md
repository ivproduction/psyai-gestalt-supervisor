# Супервизор в кармане — План реализации

## Этапы

### Этап 1. Инфраструктура
- [ ] `docker-compose.yml` — 4 сервиса: app, redis, qdrant, postgres
- [ ] `.env.example` — все переменные окружения
- [ ] Проверка: `docker compose up` — все сервисы стартуют

### Этап 2. Подготовка данных
- [ ] `ingest.py` — PDF → Markdown → очистка → `data/docs/`
- [ ] Проверка: запустить, посмотреть качество текста

### Этап 3. База данных
- [ ] `app/config.py` — настройки из env
- [ ] `app/db/models.py` — SQLAlchemy модели (users, subscriptions, audio_messages, evaluations)
- [ ] `app/db/database.py` — подключение к PostgreSQL
- [ ] `app/db/migrations/` — Alembic, первая миграция
- [ ] Проверка: `alembic upgrade head` — таблицы созданы

### Этап 4. Векторное хранилище
- [ ] `app/vector_store.py` — Qdrant + чанкинг + эмбеддинг через Gemini
- [ ] Проверка: загрузить книги, сделать тестовый поиск

### Этап 5. Кэш и история
- [ ] `app/cache.py` — Redis кэш ответов (TTL 30д) + история (28 сообщ, TTL 14д)
- [ ] Проверка: сохранить/получить из кэша, проверить TTL

### Этап 6. RAG пайплайн
- [ ] `app/rag_pipeline.py` — двухшаговая генерация через Gemini
- [ ] Проверка: задать вопрос, получить ответ, повторить — второй раз из кэша

### Этап 7. Admin API
- [ ] `app/admin.py` — FastAPI + Swagger UI на порту 8000
- [ ] Endpoints: ingest, cache/reset, history/reset, users, subscription, ragas
- [ ] Проверка: открыть `http://localhost:8000/docs`, запустить ingest

### Этап 8. Telegram бот
- [ ] `app/main.py` — handlers, регистрация пользователя, отправка вопроса в пайплайн
- [ ] Проверка: написать боту вопрос, получить ответ

---

## Текущий этап

**→ Этап 1. Инфраструктура**
