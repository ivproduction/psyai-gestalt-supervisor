"""
ingest/smart.py — конвертация PDF через Gemini Vision.

Медленно (загрузка в Gemini Files API), но понимает:
- двухколоночный layout
- диалоговый формат
- таблицы и схемы
"""

import logging
import math
from pathlib import Path

import pymupdf
from google import genai as google_genai
from google.genai import types as genai_types
from langchain_text_splitters import MarkdownHeaderTextSplitter

from app.config import GEMINI_API_KEY, PDF_PROCESSING_MODEL
from app.ingest._common import skip_intro

log = logging.getLogger(__name__)

_genai = google_genai.Client(api_key=GEMINI_API_KEY)

PROMPT = """You are a document processing assistant preparing content for a RAG knowledge base.
Analyze these PDF pages and rewrite their content in your own words as structured Markdown.

Rules:
- Use proper heading hierarchy (# ## ###) based on document structure
- Rewrite and paraphrase all content — do not quote verbatim
- Summarize key ideas, concepts, and practical guidance
- Convert tables to Markdown tables
- Describe diagrams and figures: [Figure: brief description]
- Skip page numbers, running headers, footers, copyright notices
- Output ONLY raw Markdown text — do NOT wrap in code blocks, do NOT use ```markdown or ``` fences
- No explanations, no meta-commentary, no preamble"""

BATCH_PAGES = 30  # страниц за один запрос к Gemini


def _convert_pages(pdf_path: Path, start: int, end: int) -> str:
    """Конвертирует страницы [start, end) одного PDF через Gemini."""
    import tempfile, os
    doc = pymupdf.open(str(pdf_path))
    batch_doc = pymupdf.open()
    for i in range(start, min(end, len(doc))):
        batch_doc.insert_pdf(doc, from_page=i, to_page=i)

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name
    batch_doc.save(tmp_path)
    batch_doc.close()
    doc.close()

    try:
        uploaded = _genai.files.upload(file=tmp_path)
        try:
            response = _genai.models.generate_content(
                model=PDF_PROCESSING_MODEL,
                contents=[uploaded, PROMPT],
                config=genai_types.GenerateContentConfig(max_output_tokens=8192),
            )
            text = response.text or ""
            # убираем случайные код-блоки от Gemini
            if text.startswith("```"):
                text = text.split("\n", 1)[-1]
            if text.rstrip().endswith("```"):
                text = text.rstrip()[:-3].rstrip()
            return text
        finally:
            _genai.files.delete(name=uploaded.name)
    finally:
        os.unlink(tmp_path)


def convert(pdf_path: Path) -> str:
    doc = pymupdf.open(str(pdf_path))
    total_pages = len(doc)
    doc.close()
    log.info("  [smart] %s — %d страниц, батчи по %d", pdf_path.name, total_pages, BATCH_PAGES)

    parts_md = []
    num_batches = math.ceil(total_pages / BATCH_PAGES)
    for batch_idx in range(num_batches):
        start = batch_idx * BATCH_PAGES
        end = start + BATCH_PAGES
        log.info("  [smart] Батч %d/%d (стр. %d–%d)...", batch_idx + 1, num_batches, start + 1, min(end, total_pages))
        batch_text = _convert_pages(pdf_path, start, end)
        if batch_text.strip():
            parts_md.append(batch_text)
        log.info("  [smart] Батч %d: %d символов", batch_idx + 1, len(batch_text))

    md_text = "\n\n".join(parts_md)
    log.info("  [smart] Итого: %d символов из %d батчей", len(md_text), num_batches)

    md_text = skip_intro(md_text)

    splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[("#", "chapter"), ("##", "section"), ("###", "subsection")],
        strip_headers=False,
    )
    chunks = splitter.split_text(md_text)
    log.info("  [smart] Смысловых чанков: %d", len(chunks))

    parts = []
    for chunk in chunks:
        header = " / ".join(
            v for v in [
                chunk.metadata.get("chapter"),
                chunk.metadata.get("section"),
                chunk.metadata.get("subsection"),
            ] if v
        )
        parts.append(f"[{header}]\n{chunk.page_content}" if header else chunk.page_content)

    return "\n\n---\n\n".join(parts)
