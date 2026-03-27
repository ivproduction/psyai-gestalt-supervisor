"""
main.py — точка входа: FastAPI + Telegram bot в одном процессе.
"""

import logging
import logging.config
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Security

from app.api.admin import require_api_key, router as admin_router
from app.api.chat import router as chat_router
from app.config import LOG_TO_FILE, TELEGRAM_MODE, WEBHOOK_PATH

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.bot.handlers import startup, shutdown
    await startup()
    yield
    await shutdown()


app = FastAPI(
    title="Супервизор в кармане",
    description="RAG-ассистент для гештальт-терапевтов.",
    version="0.1.0",
    docs_url="/swagger",
    redoc_url=None,
    lifespan=lifespan,
)

app.include_router(admin_router, dependencies=[Security(require_api_key)])
app.include_router(chat_router, dependencies=[Security(require_api_key)])


if TELEGRAM_MODE == "webhook":
    @app.post(WEBHOOK_PATH, include_in_schema=False)
    async def telegram_webhook(request: Request):
        from app.bot.handlers import process_update
        data = await request.json()
        await process_update(data)
        return {"ok": True}
