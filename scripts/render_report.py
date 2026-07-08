#!/usr/bin/env python3
"""Render markdown report from audit JSON files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Render pdf-layout-repair report.")
    parser.add_argument("completeness_report", type=Path)
    parser.add_argument("post_render_audit", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=Path("repair_report.md"))
    args = parser.parse_args()
    comp = json.loads(args.completeness_report.read_text(encoding="utf-8-sig"))
    post = json.loads(args.post_render_audit.read_text(encoding="utf-8-sig"))
    status = "review" if comp.get("document_status") != post.get("document_status") else comp.get("document_status", "review")
    lines = [
        f"# PDF Layout Repair Report",
        "",
        f"Status: `{status}`",
        "",
        "## Content Loss",
        "",
    ]
    for item in comp.get("content_loss", []):
        lines.append(f"- `{item.get('rule_id')}` {item.get('reason')}: {item}")
    if not comp.get("content_loss"):
        lines.append("- none")
    lines.extend(["", "## Needs Review", ""])
    for item in comp.get("needs_review", []):
        lines.append(f"- `{item.get('rule_id')}` {item.get('reason')}")
    if not comp.get("needs_review"):
        lines.append("- none")
    lines.extend(["", "## Auto Fixed", ""])
    for item in comp.get("auto_fixed", []):
        lines.append(f"- `{item.get('rule_id')}` {item.get('fixed', '')}")
    if not comp.get("auto_fixed"):
        lines.append("- none")
    lines.extend(["", "## Post Render", "", f"- Status: `{post.get('document_status')}`"])
    for item in post.get("post_render_loss", []):
        lines.append(f"- `{item.get('rule_id')}` {item.get('reason')}")
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
