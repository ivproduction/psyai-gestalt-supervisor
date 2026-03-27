"""
api/chat.py — основные пользовательские эндпоинты.
Префикс: /api/app

Текущая реализация: RAG без истории (база знаний).
TODO: добавить историю диалога, персонализацию по user_id.
"""

from typing import Literal

from fastapi import APIRouter, HTTPException

from app.services import rag

router = APIRouter(prefix="/api/app", tags=["app"])


@router.post("/ask", summary="Задать вопрос супервизору")
async def ask(
    question: str,
    source_type: str = "session_guides",
    mode: Literal["standard", "smart"] = "smart",
):
    """
    RAG пайплайн: поиск в базе знаний + генерация ответа через Gemini.

    - **source_type** — тип базы знаний (session_guides, ...)
    - **mode** — коллекция: smart (рекомендуется) или standard
    """
    try:
        return await rag.ask(question=question, source_type=source_type, mode=mode)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
