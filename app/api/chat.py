"""
api/chat.py — основные пользовательские эндпоинты.
Префикс: /api/app

Текущая реализация: RAG без истории (база знаний).
TODO: добавить историю диалога, персонализацию по user_id.
"""

from fastapi import APIRouter, HTTPException

from app.services import rag

router = APIRouter(prefix="/api/app", tags=["app"])


@router.post("/ask", summary="Задать вопрос супервизору")
async def ask(question: str):
    """
    RAG пайплайн: поиск в базе знаний + генерация ответа через Gemini.
    Коллекция задаётся через RAG_COLLECTION в .env.
    """
    try:
        return await rag.ask(question=question)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
