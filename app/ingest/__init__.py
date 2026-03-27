"""
ingest — конвертация PDF в текст для RAG.

Использование:
    from app.ingest import convert_file
    text = convert_file(pdf_path, mode="smart")
"""

import logging
from pathlib import Path
from typing import Literal

from app.config import DOCS_DIR
from app.ingest import smart, standard
from app.ingest._common import save_result

log = logging.getLogger(__name__)

_converters = {
    "standard": standard.convert,
    "smart": smart.convert,
}


def convert_file(pdf_path: Path, mode: Literal["standard", "smart"], source_type: str) -> dict:
    """
    Конвертирует один PDF в текст и сохраняет в DOCS_DIR[mode]/.
    Возвращает: {file, output, chars}
    """
    out_dir = DOCS_DIR[mode]
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("=== CONVERT [%s] %s ===", mode, pdf_path.name)
    text = _converters[mode](pdf_path)
    result = save_result(text, pdf_path, out_dir, mode, source_type)
    log.info("  Сохранено: %s (%d символов)", result["output"], result["chars"])
    return result
