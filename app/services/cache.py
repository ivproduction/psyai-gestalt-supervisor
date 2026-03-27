"""
services/cache.py — Redis: кэш ответов + история диалога.

Кэш ответов:
  ключ: cache:{sha256(question)}
  TTL:  CACHE_TTL_DAYS (30 дней)

История диалога:
  ключ: history:{user_id}
  структура: список JSON-строк {"role": "user"|"assistant", "text": "..."}
  макс: HISTORY_MAX_MESSAGES (28 сообщений)
  TTL:  HISTORY_TTL_DAYS (14 дней)
"""

import hashlib
import json
import logging

import redis.asyncio as aioredis

from app.config import (
    CACHE_TTL_DAYS,
    HISTORY_MAX_MESSAGES,
    HISTORY_TTL_DAYS,
    REDIS_HOST,
    REDIS_PORT,
)

log = logging.getLogger(__name__)

_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    return _redis


def _question_key(question: str) -> str:
    h = hashlib.sha256(question.strip().lower().encode()).hexdigest()[:16]
    return f"cache:{h}"


def _history_key(user_id: int) -> str:
    return f"history:{user_id}"


# ── Кэш ответов ───────────────────────────────────────────────

async def get_cached(question: str) -> str | None:
    try:
        value = await get_redis().get(_question_key(question))
        if value:
            log.info("cache HIT: %s...", question[:40])
        return value
    except Exception as e:
        log.warning("cache get error: %s", e)
        return None


async def set_cached(question: str, answer: str) -> None:
    try:
        ttl = CACHE_TTL_DAYS * 86400
        await get_redis().set(_question_key(question), answer, ex=ttl)
        log.info("cache SET: %s...", question[:40])
    except Exception as e:
        log.warning("cache set error: %s", e)


# ── История диалога ────────────────────────────────────────────

async def get_history(user_id: int) -> list[dict]:
    """Возвращает историю как список {"role": ..., "text": ...}"""
    try:
        key = _history_key(user_id)
        items = await get_redis().lrange(key, 0, -1)
        return [json.loads(item) for item in items]
    except Exception as e:
        log.warning("history get error: %s", e)
        return []


async def push_history(user_id: int, role: str, text: str) -> None:
    """Добавляет сообщение в историю. Защита от Race Condition через RPUSH + LTRIM."""
    try:
        key = _history_key(user_id)
        r = get_redis()
        message = json.dumps({"role": role, "text": text}, ensure_ascii=False)
        await r.rpush(key, message)
        await r.ltrim(key, -HISTORY_MAX_MESSAGES, -1)
        await r.expire(key, HISTORY_TTL_DAYS * 86400)
    except Exception as e:
        log.warning("history push error: %s", e)


async def clear_history(user_id: int) -> None:
    try:
        await get_redis().delete(_history_key(user_id))
    except Exception as e:
        log.warning("history clear error: %s", e)
