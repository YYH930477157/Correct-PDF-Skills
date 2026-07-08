#!/usr/bin/env python3
"""Build repair_manifest.json from repaired_blocks.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build repair_manifest.json.")
    parser.add_argument("source_inventory", type=Path)
    parser.add_argument("repaired_blocks", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=Path("repair_manifest.json"))
    args = parser.parse_args()
    inventory = json.loads(args.source_inventory.read_text(encoding="utf-8-sig"))
    repaired = json.loads(args.repaired_blocks.read_text(encoding="utf-8-sig"))
    dispositions = {unit["unit_id"]: "escalated" for unit in inventory.get("units", [])}
    for block in repaired.get("output_blocks", []):
        for ref in block.get("source_refs", []):
            dispositions[ref] = block.get("disposition", "emitted")
    manifest = {
        "schema_version": "0.1",
        "source_inventory": str(args.source_inventory),
        "repaired_blocks": str(args.repaired_blocks),
        "document_status": "draft",
        "output_blocks": repaired.get("output_blocks", []),
        "source_dispositions": dispositions,
        "findings": repaired.get("findings", []),
        "needs_review": repaired.get("needs_review", []),
        "not_implemented": repaired.get("not_implemented", []),
    }
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
