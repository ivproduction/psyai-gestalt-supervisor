"""
main.py — точка входа: FastAPI + Telegram bot в одном процессе.
"""

import logging

from fastapi import FastAPI

from app.api.admin import router as admin_router
from app.api.chat import router as chat_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="Супервизор в кармане",
    description="RAG-ассистент для гештальт-терапевтов.",
    version="0.1.0",
)

app.include_router(admin_router)
app.include_router(chat_router)
