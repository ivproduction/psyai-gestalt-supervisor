"""
ingest/standard.py — конвертация PDF через pymupdf4llm.

Быстро, работает локально.
Плохо справляется с двухколоночными PDF и диалоговым форматом.
"""

import logging
from pathlib import Path

import pymupdf4llm

from app.ingest._common import clean_text, skip_intro

log = logging.getLogger(__name__)


def convert(pdf_path: Path) -> str:
    log.info("  [standard] pymupdf4llm → %s", pdf_path.name)
    md = pymupdf4llm.to_markdown(str(pdf_path), page_chunks=False)
    md = skip_intro(md)
    return clean_text(md)
