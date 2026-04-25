import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
CACHE_TTL_DAYS: int = int(os.getenv("CACHE_TTL_DAYS", "30"))
RATE_LIMIT_REQUESTS: int = int(os.getenv("RATE_LIMIT_REQUESTS", "20"))
RATE_LIMIT_DAYS: int = int(os.getenv("RATE_LIMIT_DAYS", "3"))
RATE_LIMIT_WHITELIST: set[int] = {
    int(x) for x in os.getenv("RATE_LIMIT_WHITELIST", "").split(",") if x.strip()
}
HISTORY_TTL_DAYS: int = int(os.getenv("HISTORY_TTL_DAYS", "14"))
HISTORY_MAX_MESSAGES: int = int(os.getenv("HISTORY_MAX_MESSAGES", "28"))
QDRANT_HOST: str = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT: int = int(os.getenv("QDRANT_PORT", "6333"))
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "gemini-embedding-2-preview")
EMBEDDING_DIMENSION: int = int(os.getenv("EMBEDDING_DIMENSION", "768"))
RAG_RESPONSE_MODEL: str = os.getenv("RAG_RESPONSE_MODEL", "gemini-2.0-flash")
RAGAS_MODEL: str = os.getenv("RAGAS_MODEL", "gemini-2.0-flash")
TOP_K: int = int(os.getenv("TOP_K", "5"))
LOG_TO_FILE: bool = os.getenv("LOG_TO_FILE", "false").lower() == "true"

ADMIN_API_KEY: str = os.getenv("ADMIN_API_KEY", "")

TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_MODE: str = os.getenv("TELEGRAM_MODE", "polling")
WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "")
WEBHOOK_PATH: str = os.getenv("WEBHOOK_PATH", "/webhook/gestalt-supervisor")
WEBHOOK_SECRET: str = os.getenv("WEBHOOK_SECRET", "")

RAG_COLLECTION: str = os.getenv("RAG_COLLECTION", "session_guides")

DOCS_DIR = Path("data/docs")
RAGAS_DIR = Path("data/ragas")
