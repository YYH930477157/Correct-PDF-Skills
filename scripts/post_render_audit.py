#!/usr/bin/env python3
"""Post-render anchor audit for generated PDFs, HTML, or text files."""

from __future__ import annotations

import argparse
import json
import re
from html.parser import HTMLParser
from pathlib import Path


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
    expected.update(a.lower() for a in g3.get("missing_required", []))
    expected.update(a.lower() for a in g3.get("required_source_anchors", []))

    post_render_loss = []
    if not rendered_text.strip():
        post_render_loss.append({"rule_id": "I1", "reason": "rendered_text_empty"})
    missing_after_render = sorted(expected - rendered_anchors)
    if missing_after_render:
        post_render_loss.append({"rule_id": "I2", "reason": "required_anchor_missing_after_render", "anchors": missing_after_render})
    status = "review" if post_render_loss or report.get("document_status") == "review" else report.get("document_status", "draft")
    result = {
        "schema_version": "0.2",
        "document_status": status,
        "rendered_artifact": str(args.rendered_artifact),
        "completeness_report": str(args.completeness_report),
        "rendered_anchor_count": len(rendered_anchors),
        "post_render_loss": post_render_loss,
        "visual_clipping": {"status": "not_configured", "reason": "image/OCR visual clipping audit requires optional renderer integration"},
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
