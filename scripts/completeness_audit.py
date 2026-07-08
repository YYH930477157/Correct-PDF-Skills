#!/usr/bin/env python3
"""MVP completeness audit for repair manifests."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


REQUIRED_ANCHOR_RE = re.compile(r"\b(?:\d+(?:\.\d+)+|Table\s+\d+|Figure\s+\d+|Appendix\s+[A-Z])\b", re.I)


def anchors(text: str) -> set[str]:
    return {m.group(0).lower() for m in REQUIRED_ANCHOR_RE.finditer(text or "")}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run MVP completeness audit.")
    parser.add_argument("source_inventory", type=Path)
    parser.add_argument("repair_manifest", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=Path("completeness_report.json"))
    args = parser.parse_args()
    inventory = json.loads(args.source_inventory.read_text(encoding="utf-8-sig"))
    manifest = json.loads(args.repair_manifest.read_text(encoding="utf-8-sig"))
    source_units = inventory.get("units", [])
    output_blocks = manifest.get("output_blocks", [])
    source_text = "\n".join(u.get("audit_text", "") for u in source_units if u.get("granularity") in {"block", "page"})
    output_text = "\n".join(b.get("audit_text", "") for b in output_blocks)
    missing = sorted(anchors(source_text) - anchors(output_text))
    dispositions = manifest.get("source_dispositions", {})
    unmapped = [u["unit_id"] for u in source_units if dispositions.get(u["unit_id"]) == "escalated" and u.get("granularity") == "block"]
    content_loss = []
    needs_review = []
    if missing:
        content_loss.append({"rule_id": "G3", "reason": "required_anchor_missing", "anchors": missing})
    if unmapped:
        content_loss.append({"rule_id": "H2", "reason": "unmapped_source_blocks", "source_refs": unmapped[:100]})
    for item in manifest.get("not_implemented", []):
        needs_review.append({"rule_id": item["rule_id"], "reason": "not_implemented_if_applicable"})
    status = "review" if content_loss else ("draft" if needs_review else "final")
    report = {
        "schema_version": "0.1",
        "document_status": status,
        "source_inventory": str(args.source_inventory),
        "repair_manifest": str(args.repair_manifest),
        "content_loss": content_loss,
        "needs_review": needs_review,
        "auto_fixed": manifest.get("findings", []),
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
