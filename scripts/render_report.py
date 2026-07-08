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
    audits = comp.get("audits", {})
    if audits:
        lines.extend(["", "## Audit Summary", ""])
        g1 = audits.get("G1_page_coverage", {})
        lines.append(f"- `G1` source pages: {len(g1.get('source_pages_with_text', []))}; missing pages: {len(g1.get('missing_pages', []))}")
        g2 = audits.get("G2_text_amount", {})
        lines.append(f"- `G2` low coverage pages: {len(g2.get('low_coverage', []))}; threshold: {g2.get('threshold')}")
        g3 = audits.get("G3_anchor_audit", {})
        lines.append(f"- `G3` required anchors: {g3.get('required_source_count', 0)}; missing: {len(g3.get('missing_required', []))}")
        lines.append(f"- `G3C` candidate anchors: {g3.get('candidate_source_count', 0)}; missing: {len(g3.get('missing_candidate', []))}")
        g4 = audits.get("G4_figure_table_audit", {})
        lines.append(f"- `G4` figure/table anchors: {len(g4.get('source_figure_table_anchors', []))}; missing: {len(g4.get('missing', []))}")
        g5 = audits.get("G5_ai_semantic_sampling", {})
        lines.append(f"- `G5` {g5.get('status', 'unknown')}: {g5.get('reason', '')}")
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
