"""
ingest/_common.py — общие утилиты для обоих режимов конвертации.
"""

import json
import re
from pathlib import Path

from app.config import DEFAULT_SKIP_HEADERS


def clean_text(text: str) -> str:
    lines = text.split("\n")
    cleaned = [
        line for line in lines
        if not (len(line.strip()) < 40 and not line.strip().startswith("#"))
        and not re.match(r"^[\W_]+$", line.strip())
    ]
    text = "\n".join(cleaned)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return re.sub(r" {2,}", " ", text).strip()


def skip_intro(md_text: str, skip_count: int = DEFAULT_SKIP_HEADERS) -> str:
    lines = md_text.split("\n")
    count = 0
    for i, line in enumerate(lines):
        if line.startswith("# ") or line.startswith("## "):
            count += 1
            if count > skip_count:
                return "\n".join(lines[i:])
    return md_text


def pdf_stem_to_safe(pdf_path: Path) -> str:
    """Безопасное имя файла для .txt: убирает пробелы → подчёркивания."""
    return re.sub(r"\s+", "_", pdf_path.stem) + ".txt"


def save_result(text: str, pdf_path: Path, out_dir: Path, mode: str, source_type: str) -> dict:
    """Сохраняет .txt и .meta.json. Возвращает dict с результатом."""
    out_name = pdf_stem_to_safe(pdf_path)
    out_path = out_dir / out_name

    out_path.write_text(text, encoding="utf-8")

    meta = {
        "source_file": pdf_path.name,
        "source_type": source_type,
        "output_file": out_name,
        "char_count": len(text),
        "ingest_mode": mode,
    }
    out_path.with_suffix(".meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return {"file": pdf_path.name, "output": out_name, "chars": len(text)}
