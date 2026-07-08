#!/usr/bin/env python3
"""Preflight PDF pages and emit rough page profiles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def classify_page(text_len: int, image_count: int, drawing_count: int) -> str:
    if text_len < 50 and image_count > 0:
        return "scan_page"
    if drawing_count > 80 or image_count > 3:
        return "figure_heavy_page"
    return "text_page"


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect rough PDF page profiles.")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=Path("pdf_preflight.json"))
    args = parser.parse_args()

    try:
        import fitz  # PyMuPDF
    except Exception as exc:  # pragma: no cover
        raise SystemExit(f"PyMuPDF is required: {exc}")

    doc = fitz.open(args.pdf)
    pages = []
    for idx, page in enumerate(doc):
        text = page.get_text("text") or ""
        images = page.get_images(full=True)
        drawings = page.get_drawings()
        pages.append(
            {
                "page": idx,
                "text_chars": len(text),
                "image_count": len(images),
                "drawing_count": len(drawings),
                "initial_page_profile": classify_page(len(text), len(images), len(drawings)),
            }
        )
    result = {"input": str(args.pdf), "page_count": len(doc), "pages": pages}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
