#!/usr/bin/env python3
"""Post-render anchor audit for generated PDFs, HTML, or text files."""

from __future__ import annotations

import argparse
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


ANCHOR_RE = re.compile(r"\b(?:\d+(?:\.\d+)+|Table\s+\d+|Figure\s+\d+|Appendix\s+[A-Z])\b", re.I)


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        return " ".join(self.parts)


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            import fitz
        except Exception as exc:  # pragma: no cover
            raise SystemExit(f"PyMuPDF is required for PDF audit: {exc}")
        doc = fitz.open(path)
        return "\n".join(page.get_text("text") or "" for page in doc)
    raw = path.read_text(encoding="utf-8-sig")
    if suffix in {".html", ".htm"}:
        parser = TextExtractor()
        parser.feed(raw)
        return parser.text()
    return raw


def pdf_visual_clipping(path: Path, margin: float = 2.0) -> dict[str, Any]:
    if path.suffix.lower() != ".pdf":
        return {"status": "skipped", "reason": "visual_clipping_requires_pdf"}
    try:
        import fitz
    except Exception as exc:  # pragma: no cover
        return {"status": "unavailable", "reason": f"PyMuPDF unavailable: {exc}"}
    doc = fitz.open(path)
    findings = []
    for page_index, page in enumerate(doc):
        rect = page.rect
        blocks = page.get_text("blocks") or []
        for block_index, block in enumerate(blocks):
            bbox = block[:4]
            if bbox[0] < rect.x0 - margin or bbox[1] < rect.y0 - margin or bbox[2] > rect.x1 + margin or bbox[3] > rect.y1 + margin:
                findings.append({"page": page_index, "kind": "text_block", "index": block_index, "bbox": list(bbox)})
        for drawing_index, drawing in enumerate(page.get_drawings()):
            drect = drawing.get("rect")
            if drect and (drect.x0 < rect.x0 - margin or drect.y0 < rect.y0 - margin or drect.x1 > rect.x1 + margin or drect.y1 > rect.y1 + margin):
                findings.append({"page": page_index, "kind": "drawing", "index": drawing_index, "bbox": [drect.x0, drect.y0, drect.x1, drect.y1]})
    return {"status": "checked", "finding_count": len(findings), "findings": findings[:200]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run post-render anchor audit.")
    parser.add_argument("rendered_artifact", type=Path)
    parser.add_argument("completeness_report", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=Path("post_render_audit.json"))
    args = parser.parse_args()
    report = json.loads(args.completeness_report.read_text(encoding="utf-8-sig"))
    rendered_text = extract_text(args.rendered_artifact)
    rendered_anchors = {m.group(0).lower() for m in ANCHOR_RE.finditer(rendered_text)}
    expected = set()
    g3 = report.get("audits", {}).get("G3_anchor_audit", {})
    output_anchors = g3.get("required_output_anchors")
    if output_anchors is None:
        output_anchors = sorted(set(g3.get("required_source_anchors", [])) - set(g3.get("missing_required", [])))
    expected.update(a.lower() for a in output_anchors)

    post_render_loss = []
    if not rendered_text.strip():
        post_render_loss.append({"rule_id": "I1", "reason": "rendered_text_empty"})
    missing_after_render = sorted(expected - rendered_anchors)
    if missing_after_render:
        post_render_loss.append({"rule_id": "I2", "reason": "required_anchor_missing_after_render", "anchors": missing_after_render})
    clipping = pdf_visual_clipping(args.rendered_artifact)
    if clipping.get("finding_count", 0):
        post_render_loss.append({"rule_id": "I3", "reason": "rendered_content_outside_page_bounds", "finding_count": clipping["finding_count"]})
    render_status = "review" if post_render_loss else "pass"
    status = "review" if post_render_loss or report.get("document_status") == "review" else report.get("document_status", "draft")
    result = {
        "schema_version": "0.2",
        "document_status": status,
        "render_status": render_status,
        "rendered_artifact": str(args.rendered_artifact),
        "completeness_report": str(args.completeness_report),
        "rendered_anchor_count": len(rendered_anchors),
        "post_render_loss": post_render_loss,
        "visual_clipping": clipping,
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
