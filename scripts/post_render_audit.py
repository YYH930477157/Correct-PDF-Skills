#!/usr/bin/env python3
"""Post-render anchor audit for generated PDFs or text files."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ANCHOR_RE = re.compile(r"\b(?:\d+(?:\.\d+)+|Table\s+\d+|Figure\s+\d+|Appendix\s+[A-Z])\b", re.I)


def extract_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        try:
            import fitz
        except Exception as exc:  # pragma: no cover
            raise SystemExit(f"PyMuPDF is required for PDF audit: {exc}")
        doc = fitz.open(path)
        return "\n".join(page.get_text("text") or "" for page in doc)
    return path.read_text(encoding="utf-8")


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
    for item in report.get("content_loss", []):
        expected.update(a.lower() for a in item.get("anchors", []))
    # If completeness already failed, preserve review status; otherwise this MVP verifies artifact is readable.
    post_render_loss = []
    if not rendered_text.strip():
        post_render_loss.append({"rule_id": "I1", "reason": "rendered_text_empty"})
    status = "review" if post_render_loss or report.get("document_status") == "review" else report.get("document_status", "draft")
    result = {
        "schema_version": "0.1",
        "document_status": status,
        "rendered_artifact": str(args.rendered_artifact),
        "completeness_report": str(args.completeness_report),
        "rendered_anchor_count": len(rendered_anchors),
        "post_render_loss": post_render_loss,
        "visual_clipping": {"status": "not_implemented", "result": "needs_review_if_applicable"},
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
