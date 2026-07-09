#!/usr/bin/env python3
"""Audit source PDF evidence with PyMuPDF, independent of MinerU."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ANCHOR_RE = re.compile(r"\b(?:\d+(?:\.\d+)+|Table\s+\d+|Figure\s+\d+|Appendix\s+[A-Z]|UNI(?:/[A-Z]+)?\s+\d+|ISO\s+\d+)\b", re.I)


def normalize_anchor(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\u00a0", " ")).strip().lower()


def snippet_for(text: str, start: int, end: int, radius: int = 80) -> str:
    snippet = text[max(0, start - radius) : min(len(text), end + radius)]
    return re.sub(r"\s+", " ", snippet).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit source PDF text/image/vector evidence.")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=Path("source_pdf_audit.json"))
    args = parser.parse_args()
    try:
        import fitz
    except Exception as exc:  # pragma: no cover
        raise SystemExit(f"PyMuPDF is required: {exc}")

    doc = fitz.open(args.pdf)
    pages = []
    all_anchors = set()
    anchor_locations: dict[str, list[dict[str, object]]] = {}
    for idx, page in enumerate(doc):
        text = page.get_text("text") or ""
        page_anchor_set = set()
        for match in ANCHOR_RE.finditer(text):
            anchor = normalize_anchor(match.group(0))
            page_anchor_set.add(anchor)
            anchor_locations.setdefault(anchor, []).append(
                {
                    "page": idx,
                    "snippet": snippet_for(text, match.start(), match.end()),
                }
            )
        anchors = sorted(page_anchor_set)
        all_anchors.update(anchors)
        pages.append(
            {
                "page": idx,
                "text_chars": len(re.sub(r"\s+", "", text)),
                "image_count": len(page.get_images(full=True)),
                "drawing_count": len(page.get_drawings()),
                "anchor_count": len(anchors),
                "anchors": anchors[:300],
            }
        )
    result = {
        "schema_version": "0.1",
        "input": str(args.pdf),
        "page_count": len(doc),
        "pages": pages,
        "anchors": sorted(all_anchors)[:2000],
        "anchor_locations": {anchor: locations[:20] for anchor, locations in sorted(anchor_locations.items())},
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
