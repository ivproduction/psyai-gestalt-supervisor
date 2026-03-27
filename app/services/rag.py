"""
services/rag.py — RAG пайплайн: поиск + генерация.

Текущая реализация: база знаний без истории.
  вопрос → поиск в Qdrant → контекст → Gemini → ответ (кэшируется)

TODO (следующий этап):
  - добавить историю диалога (services/cache.py::get_history/push_history)
  - персонализация ответа под конкретного пользователя
"""

import asyncio
import logging
import time
from typing import Literal

from google import genai as google_genai

from app.config import GEMINI_API_KEY, RAG_RESPONSE_MODEL, TOP_K
from app.services.cache import get_cached, set_cached
from app.services.search import search as _search_sync

log = logging.getLogger(__name__)

_genai = google_genai.Client(api_key=GEMINI_API_KEY)

SYSTEM_PROMPT = """Ты — опытный супервизор по гештальт-терапии.
Помогаешь начинающим гештальт-терапевтам разобраться в теории и практике.
Отвечай на русском языке, даже если источники на английском.
Будь конкретным, практичным и поддерживающим.
Не упоминай источники, названия книг, авторов и номера чанков в ответе.
Не используй приветствия в начале ответа — начинай сразу с сути."""

RAG_PROMPT = """Используй следующие фрагменты из книг по гештальт-терапии чтобы ответить на вопрос.

КОНТЕКСТ:
{context}

ВОПРОС: {question}

Дай развёрнутый ответ на основе контекста. Отвечай на русском.
Не упоминай источники, авторов, названия книг и технические детали — отвечай как опытный терапевт, а не как реферат.
Если контекст не содержит достаточно информации для ответа — честно скажи об этом, не придумывай."""

# ── Telegram-специфичные промпты ──────────────────────────────

TELEGRAM_SYSTEM_PROMPT = """Ты — опытный супервизор по гештальт-терапии.
Помогаешь начинающим гештальт-терапевтам разобраться в теории и практике.
Отвечай на русском языке, даже если источники на английском.
Будь конкретным, практичным и поддерживающим.
Не упоминай источники, названия книг, авторов и номера чанков в ответе.
Не используй приветствия в начале ответа — начинай сразу с сути.

Формат ответа — HTML для Telegram:
• Разделы начинай с эмодзи и <b>жирного заголовка</b>
• Ключевые термины выделяй <b>жирным</b>
• Примеры и цитаты — <i>курсивом</i>
• Списки — с символом •
• Короткие абзацы, удобные для чтения на телефоне
• Никаких символов * ** # ## — только HTML-теги"""

TELEGRAM_RAG_PROMPT = """Используй следующие фрагменты из книг по гештальт-терапии чтобы ответить на вопрос.

КОНТЕКСТ:
{context}

ВОПРОС: {question}

Дай структурированный ответ с HTML-форматированием для Telegram.
Отвечай как опытный терапевт — не упоминай источники, авторов, названия книг и технические детали.
Если контекста недостаточно — честно скажи об этом, не придумывай.
Отвечай на русском."""


async def ask(
    question: str,
    user_id: int = 0,
    source_type: str = "session_guides",
    mode: Literal["standard", "smart"] = "smart",
    top_k: int = TOP_K,
    use_cache: bool = True,
    channel: str = "api",
) -> dict:
    """
    RAG пайплайн. Возвращает:
      {answer, from_cache, chunks_used, collection}

    use_cache=False — не читать и не писать кэш (используется при RAGAS оценке).
    user_id зарезервирован для будущей персонализации.
    """
    t_total = time.perf_counter()
    collection = f"{source_type}_{mode}"

    log.info("━━━ RAG START ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    log.info("  вопрос   : %s", question)
    log.info("  коллекция: %s | top_k=%d | cache=%s", collection, top_k, use_cache)

    # ── Кэш ───────────────────────────────────────────────────
    if use_cache:
        t0 = time.perf_counter()
        cached = await get_cached(question)
        t_cache = time.perf_counter() - t0

        if cached:
            t_total_ms = (time.perf_counter() - t_total) * 1000
            log.info("  [CACHE]  ✅ HIT (%.0f мс) → ответ %d симв.", t_cache * 1000, len(cached))
            log.info("  итого    : %.0f мс", t_total_ms)
            log.info("━━━ RAG END ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            return {
                "answer": cached,
                "from_cache": True,
                "chunks_used": None,
                "collection": collection,
            }

        log.info("  [CACHE]  ❌ MISS (%.0f мс)", t_cache * 1000)
    else:
        log.info("  [CACHE]  ⏭ пропущен (RAGAS режим)")

    # ── Поиск в Qdrant ─────────────────────────────────────────
    t0 = time.perf_counter()
    chunks = await asyncio.to_thread(_search_sync, question, source_type, mode, top_k)
    t_search = time.perf_counter() - t0

    if not chunks:
        log.info("  [SEARCH] ❌ нет результатов (%.0f мс)", t_search * 1000)
        answer = "К сожалению, я не нашёл релевантной информации в базе знаний по этому вопросу."
        return {"answer": answer, "from_cache": False, "chunks_used": 0, "collection": collection}

    log.info("  [SEARCH] ✅ %d чанков (%.0f мс)", len(chunks), t_search * 1000)
    for i, c in enumerate(chunks):
        log.info("    #%d score=%.4f  %s  chunk_%s  %d симв.",
                 i + 1, c["score"], c["source_file"], c["chunk_index"], len(c["text"]))

    # ── Генерация ──────────────────────────────────────────────
    context = "\n\n---\n\n".join(
        f"[{c['source_file']}, chunk {c['chunk_index']}]\n{c['text']}"
        for c in chunks
    )
    context_chars = len(context)

    if channel == "telegram":
        system_prompt = TELEGRAM_SYSTEM_PROMPT
        prompt = TELEGRAM_RAG_PROMPT.format(context=context, question=question)
    else:
        system_prompt = SYSTEM_PROMPT
        prompt = RAG_PROMPT.format(context=context, question=question)

    prompt_chars = len(prompt)

    log.info("  [GENERATE] модель=%s | канал=%s | контекст=%d симв. | промпт=%d симв.",
             RAG_RESPONSE_MODEL, channel, context_chars, prompt_chars)

    t0 = time.perf_counter()
    response = await asyncio.to_thread(
        _genai.models.generate_content,
        model=RAG_RESPONSE_MODEL,
        contents=[system_prompt, prompt],
    )
    t_gen = time.perf_counter() - t0
    answer = response.text

    log.info("  [GENERATE] ✅ ответ=%d симв. (%.0f мс)", len(answer), t_gen * 1000)

    # ── Кэш ───────────────────────────────────────────────────
    if use_cache:
        await set_cached(question, answer)
        log.info("  [CACHE]  💾 сохранён")
    else:
        log.info("  [CACHE]  ⏭ не сохраняем (RAGAS режим)")

    t_total_ms = (time.perf_counter() - t_total) * 1000
    log.info("  итого    : %.0f мс  (search=%.0f + generate=%.0f)",
             t_total_ms, t_search * 1000, t_gen * 1000)
    log.info("━━━ RAG END ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    return {
        "answer": answer,
        "from_cache": False,
        "chunks_used": len(chunks),
        "collection": collection,
    }
