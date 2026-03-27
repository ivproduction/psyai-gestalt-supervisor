import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
CACHE_TTL_DAYS: int = int(os.getenv("CACHE_TTL_DAYS", "30"))
HISTORY_TTL_DAYS: int = int(os.getenv("HISTORY_TTL_DAYS", "14"))
HISTORY_MAX_MESSAGES: int = int(os.getenv("HISTORY_MAX_MESSAGES", "28"))
QDRANT_HOST: str = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT: int = int(os.getenv("QDRANT_PORT", "6333"))
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "gemini-embedding-2-preview")
EMBEDDING_DIMENSION: int = int(os.getenv("EMBEDDING_DIMENSION", "768"))
RAG_RESPONSE_MODEL: str = os.getenv("RAG_RESPONSE_MODEL", "gemini-2.0-flash")
PDF_PROCESSING_MODEL: str = os.getenv("PDF_PROCESSING_MODEL", "gemini-1.5-flash")
TOP_K: int = int(os.getenv("TOP_K", "5"))
LOG_TO_FILE: bool = os.getenv("LOG_TO_FILE", "false").lower() == "true"

RAW_DIR = Path("data/raw")
DOCS_DIR = {
    "standard": Path("data/docs/standard"),
    "smart":    Path("data/docs/smart"),
}
RAGAS_DIR = Path("data/ragas")

DEFAULT_SKIP_HEADERS = 5


def collection_name(source_type: str, mode: str) -> str:
    """Динамическое имя коллекции: session_guides_smart, therapist_finder_standard, ..."""
    return f"{source_type}_{mode}"


# Алиасы для коллекций загруженных до введения source_type
LEGACY_COLLECTIONS = {
    "gestalt_standard": ("session_guides", "standard"),
    "gestalt_smart":    ("session_guides", "smart"),
}
