"""
main.py — точка входа: FastAPI + Telegram bot в одном процессе.
"""

import logging
import logging.config
from pathlib import Path

from fastapi import FastAPI

from app.api.admin import router as admin_router
from app.api.chat import router as chat_router
from app.config import LOG_TO_FILE

_fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_log_file = str(Path(__file__).resolve().parent.parent / "app.log")

_handlers = {
    "console": {
        "class": "logging.StreamHandler",
        "formatter": "default",
        "stream": "ext://sys.stdout",
    }
}
if LOG_TO_FILE:
    _handlers["file"] = {
        "class": "logging.handlers.RotatingFileHandler",
        "formatter": "default",
        "filename": _log_file,
        "maxBytes": 10 * 1024 * 1024,
        "backupCount": 3,
        "encoding": "utf-8",
    }

_active_handlers = list(_handlers.keys())

logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"default": {"format": _fmt}},
    "handlers": _handlers,
    "root": {"level": "INFO", "handlers": _active_handlers},
    "loggers": {
        "uvicorn":        {"handlers": _active_handlers, "level": "INFO", "propagate": False},
        "uvicorn.access": {"handlers": _active_handlers, "level": "INFO", "propagate": False},
        "uvicorn.error":  {"handlers": _active_handlers, "level": "INFO", "propagate": False},
    },
})

app = FastAPI(
    title="Супервизор в кармане",
    description="RAG-ассистент для гештальт-терапевтов.",
    version="0.1.0",
)

app.include_router(admin_router)
app.include_router(chat_router)
