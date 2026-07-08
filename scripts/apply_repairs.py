#!/usr/bin/env python3
"""Apply MVP repairs and produce repaired_blocks.json."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


SECTION_RE = re.compile(r"^(?:\d+(?:\.\d+)*|[A-Z](?:\.\d+)*)$")


def cy(unit: dict[str, Any]) -> float:
    bbox = unit.get("bbox") or [0, 0, 0, 0]
    return (bbox[1] + bbox[3]) / 2


def is_left_isolated_section(unit: dict[str, Any]) -> bool:
    bbox = unit.get("bbox") or [999, 0, 999, 0]
    return unit.get("granularity") == "block" and SECTION_RE.match(unit.get("raw_text", "").strip()) and bbox[0] < 120


def same_baseline(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return abs(cy(a) - cy(b)) <= 8


def apply_a1(units: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    blocks = [u for u in units if u.get("granularity") == "block"]
    used: set[str] = set()
    outputs: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []

    def reading_order(unit: dict[str, Any]) -> tuple[Any, ...]:
        bbox = unit.get("bbox") or [0, 0, 0, 0]
        return (unit.get("page", 0), bbox[1], bbox[0])

    for unit in sorted((u for u in blocks if is_left_isolated_section(u)), key=reading_order):
        if is_left_isolated_section(unit):
            bbox = unit.get("bbox") or [0, 0, 0, 0]
            candidates = [
                other
                for other in blocks
                if other["unit_id"] not in used
                and other["unit_id"] != unit["unit_id"]
                and other.get("page") == unit.get("page")
                and (other.get("bbox") or [0])[0] > bbox[2] + 20
                and same_baseline(unit, other)
            ]
            if candidates:
                target = sorted(candidates, key=lambda u: ((u.get("bbox") or [0])[0]))[0]
                text = f"{unit['raw_text'].strip()} {target['raw_text'].strip()}"
                output_id = f"out:{target['unit_id']}"
                outputs.append(
                    {
                        "output_id": output_id,
                        "raw_text": text,
                        "audit_text": text.lower(),
                        "source_refs": [unit["unit_id"], target["unit_id"]],
                        "operation": "A1_merge_section_number",
                        "confidence": 0.9,
                        "disposition": "merged",
                        "page": unit.get("page"),
                    }
                )
                used.update({unit["unit_id"], target["unit_id"]})
                findings.append({"rule_id": "A1", "severity": "auto_fixed", "source_refs": [unit["unit_id"], target["unit_id"]], "fixed": text})
                continue

    for unit in sorted(blocks, key=reading_order):
        if unit["unit_id"] in used:
            continue
        outputs.append(
            {
                "output_id": f"out:{unit['unit_id']}",
                "raw_text": unit.get("raw_text", ""),
                "audit_text": unit.get("audit_text", ""),
                "source_refs": [unit["unit_id"]],
                "operation": "emit",
                "confidence": 1.0,
                "disposition": "emitted",
                "page": unit.get("page"),
            }
        )
        used.add(unit["unit_id"])
    return outputs, findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply MVP PDF layout repairs.")
    parser.add_argument("source_inventory", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=Path("repaired_blocks.json"))
    args = parser.parse_args()
    inventory = json.loads(args.source_inventory.read_text(encoding="utf-8-sig"))
    outputs, findings = apply_a1(inventory.get("units", []))
    result = {
        "schema_version": "0.1",
        "source_inventory": str(args.source_inventory),
        "output_blocks": outputs,
        "findings": findings,
        "not_implemented": [
            {"rule_id": "TOC", "status": "not_implemented", "default": "needs_review_if_applicable"},
            {"rule_id": "B-F", "status": "not_implemented", "default": "needs_review_if_applicable"},
        ],
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
