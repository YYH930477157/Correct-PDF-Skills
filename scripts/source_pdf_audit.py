#!/usr/bin/env python3
"""Audit source PDF evidence with PyMuPDF, independent of MinerU."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from statistics import median
from pathlib import Path


ANCHOR_RE = re.compile(r"\b(?:\d+(?:\.\d+)+|Table\s+\d+|Figure\s+\d+|Appendix\s+[A-Z]|UNI(?:/[A-Z]+)?\s+\d+|ISO\s+\d+)\b", re.I)


def normalize_anchor(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\u00a0", " ")).strip().lower()


def snippet_for(text: str, start: int, end: int, radius: int = 80) -> str:
    snippet = text[max(0, start - radius) : min(len(text), end + radius)]
    return re.sub(r"\s+", " ", snippet).strip()


def structured_lines(page: object) -> list[dict[str, object]]:
    page_sizes: list[float] = []
    result: list[dict[str, object]] = []
    data = page.get_text("dict") or {}
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = "".join(str(span.get("text", "")) for span in spans)
            text = re.sub(r"\s+", " ", text).strip()
            bbox = line.get("bbox")
            if text and isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                sizes = [float(span.get("size", 0)) for span in spans if span.get("text")]
                weighted_chars = sum(len(str(span.get("text", ""))) for span in spans)
                bold_chars = sum(len(str(span.get("text", ""))) for span in spans if int(span.get("flags", 0)) & 16)
                page_sizes.extend(sizes)
                result.append({"line_text": text, "bbox": [float(value) for value in bbox], "max_font_size": max(sizes, default=0.0), "bold_ratio": bold_chars / max(weighted_chars, 1)})
    body_size = median(page_sizes) if page_sizes else 0.0
    return result


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
    source_sha256 = hashlib.sha256(args.pdf.read_bytes()).hexdigest()
    pages = []
    all_anchors = set()
    anchor_locations: dict[str, list[dict[str, object]]] = {}
    for idx, page in enumerate(doc):
        text = page.get_text("text") or ""
        page_area = max(float(page.rect.width * page.rect.height), 1.0)
        page_anchor_set = set()
        line_anchor_set = set()
        for line in structured_lines(page):
            line_text = str(line["line_text"])
            for match in ANCHOR_RE.finditer(line_text):
                anchor = normalize_anchor(match.group(0))
                page_anchor_set.add(anchor)
                line_anchor_set.add(anchor)
                anchor_locations.setdefault(anchor, []).append(
                    {
                        "page": idx,
                        "snippet": line_text,
                        "line_text": line_text,
                        "bbox": line["bbox"],
                        "heading_like": line.get("heading_like", False),
                        "max_font_size": line.get("max_font_size", 0.0),
                        "bold_ratio": line.get("bold_ratio", 0.0),
                    }
                )
        for match in ANCHOR_RE.finditer(text):
            anchor = normalize_anchor(match.group(0))
            page_anchor_set.add(anchor)
            if anchor not in line_anchor_set:
                anchor_locations.setdefault(anchor, []).append(
                    {
                        "page": idx,
                        "snippet": snippet_for(text, match.start(), match.end()),
                    }
                )
        anchors = sorted(page_anchor_set)
        all_anchors.update(anchors)
        drawings = page.get_drawings()
        significant_drawings = [drawing for drawing in drawings if drawing.get("rect") and float(drawing["rect"].width * drawing["rect"].height) / page_area >= 0.02]
        significant_images = [info for info in (page.get_image_info() or []) if info.get("bbox") and float((info["bbox"][2] - info["bbox"][0]) * (info["bbox"][3] - info["bbox"][1])) / page_area >= 0.02]
        pages.append(
            {
                "page": idx,
                "text_chars": len(re.sub(r"\s+", "", text)),
                "image_count": len(page.get_images(full=True)),
                "drawing_count": len(drawings),
                "significant_image_count": len(significant_images),
                "significant_drawing_count": len(significant_drawings),
                "anchor_count": len(anchors),
                "anchors": anchors[:300],
            }
        )
    result = {
        "schema_version": "0.2",
        "input": str(args.pdf),
        "page_count": len(doc),
        "source_pdf_sha256": source_sha256,
        "pages": pages,
        "anchors": sorted(all_anchors)[:2000],
        "anchor_locations": {anchor: locations[:20] for anchor, locations in sorted(anchor_locations.items())},
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
