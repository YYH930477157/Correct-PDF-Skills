#!/usr/bin/env python3
"""Apply deterministic PDF layout repairs and produce repaired_blocks.json."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


SECTION_RE = re.compile(r"^(?:\d+(?:\.\d+)*|[A-Z](?:\.\d+)*)$")
TOC_NUMBER_RE = re.compile(r"^\d+(?:\.\d+)*$")
BULLET_REPLACEMENTS = {
    "\u2212": "-",
    "\u2010": "-",
    "\u2011": "-",
    "\u2012": "-",
    "\u2013": "-",
    "\u2014": "-",
    "\u2022": "-",
}
SYMBOL_REPLACEMENTS = {
    "\u0177": "<=",
    "\u2264": "<=",
    "\u2265": ">=",
}


def cy(unit: dict[str, Any]) -> float:
    bbox = unit.get("bbox") or [0, 0, 0, 0]
    return (bbox[1] + bbox[3]) / 2


def is_left_isolated_section(unit: dict[str, Any]) -> bool:
    bbox = unit.get("bbox") or [999, 0, 999, 0]
    return unit.get("granularity") == "block" and SECTION_RE.match(unit.get("raw_text", "").strip()) and bbox[0] < 120


def same_baseline(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return abs(cy(a) - cy(b)) <= 8


def reading_order(unit: dict[str, Any]) -> tuple[Any, ...]:
    bbox = unit.get("bbox") or [0, 0, 0, 0]
    return (unit.get("page", 0), bbox[1], bbox[0])


def normalize_audit(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def output_block(
    output_id: str,
    raw_text: str,
    source_refs: list[str],
    operation: str,
    disposition: str,
    page: int | None,
    confidence: float = 1.0,
) -> dict[str, Any]:
    return {
        "output_id": output_id,
        "raw_text": raw_text,
        "audit_text": normalize_audit(raw_text),
        "source_refs": source_refs,
        "operation": operation,
        "confidence": confidence,
        "disposition": disposition,
        "page": page,
    }


def finding(rule_id: str, source_refs: list[str], fixed: str, severity: str = "auto_fixed") -> dict[str, Any]:
    return {"rule_id": rule_id, "severity": severity, "source_refs": source_refs, "fixed": fixed}


def is_sentence_terminal(text: str) -> bool:
    return bool(re.search(r"[.!?:;)]\s*$", text.strip()))


def starts_like_continuation(text: str) -> bool:
    stripped = text.strip()
    return bool(stripped) and not re.match(r"^(?:[A-Z][A-Z0-9 /()-]{2,}|\d+(?:\.\d+)*)\b", stripped) and stripped[:1].islower()


def is_toc_number(unit: dict[str, Any]) -> bool:
    text = unit.get("raw_text", "").strip()
    return unit.get("dtype") == "toc_number" or (TOC_NUMBER_RE.match(text) and (unit.get("bbox") or [999])[0] < 90)


def is_toc_title(unit: dict[str, Any]) -> bool:
    return unit.get("dtype") == "toc_title"


def is_toc_page(unit: dict[str, Any]) -> bool:
    text = unit.get("raw_text", "").strip()
    bbox = unit.get("bbox") or [0, 0, 0, 0]
    return unit.get("dtype") == "toc_page" or (text.isdigit() and bbox[0] >= 450)


def normalize_bullets(text: str) -> str:
    out = text
    for old, new in BULLET_REPLACEMENTS.items():
        out = out.replace(old, new)
    return re.sub(r"^\s*-\s*", "- ", out.strip())


def repair_symbols(text: str) -> str:
    out = text
    for old, new in SYMBOL_REPLACEMENTS.items():
        out = out.replace(old, new)
    return out


def apply_repairs(units: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    blocks = [u for u in units if u.get("granularity") == "block"]
    used: set[str] = set()
    outputs: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []

    # D0: table-of-contents rows split into number/title/page columns.
    for number in sorted((u for u in blocks if is_toc_number(u)), key=reading_order):
        if number["unit_id"] in used:
            continue
        same_row = [
            other
            for other in blocks
            if other["unit_id"] not in used
            and other["unit_id"] != number["unit_id"]
            and other.get("page") == number.get("page")
            and same_baseline(number, other)
        ]
        titles = [u for u in same_row if is_toc_title(u) or ((u.get("bbox") or [0])[0] > 90 and (u.get("bbox") or [0])[0] < 450 and not is_toc_page(u))]
        pages = [u for u in same_row if is_toc_page(u)]
        if titles and pages:
            title = sorted(titles, key=lambda u: (u.get("bbox") or [0])[0])[0]
            page = sorted(pages, key=lambda u: (u.get("bbox") or [0])[0])[-1]
            text = f"{number['raw_text'].strip()} {title['raw_text'].strip()} {page['raw_text'].strip()}"
            refs = [number["unit_id"], title["unit_id"], page["unit_id"]]
            outputs.append(output_block(f"out:{number['unit_id']}:toc", text, refs, "TOC_three_column_repair", "merged", number.get("page"), 0.9))
            used.update(refs)
            findings.append(finding("D0", refs, text))

    # A1: section number in the margin/left column split from its heading.
    for unit in sorted((u for u in blocks if is_left_isolated_section(u)), key=reading_order):
        if unit["unit_id"] in used:
            continue
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
                refs = [unit["unit_id"], target["unit_id"]]
                outputs.append(output_block(f"out:{target['unit_id']}", text, refs, "A1_merge_section_number", "merged", unit.get("page"), 0.9))
                used.update(refs)
                findings.append(finding("A1", refs, text))
                continue

    # B1: join adjacent paragraph fragments when the first block is unfinished.
    ordered = sorted(blocks, key=reading_order)
    for idx, unit in enumerate(ordered[:-1]):
        if unit["unit_id"] in used:
            continue
        nxt = ordered[idx + 1]
        if nxt["unit_id"] in used:
            continue
        if unit.get("page") != nxt.get("page"):
            continue
        if unit.get("dtype") not in {"text", "para", "paragraph", "para_blocks"} and nxt.get("dtype") not in {"text", "para", "paragraph", "para_blocks"}:
            continue
        bbox = unit.get("bbox") or [0, 0, 0, 0]
        next_bbox = nxt.get("bbox") or [0, 0, 0, 0]
        vertical_gap = next_bbox[1] - bbox[3]
        same_left = abs((bbox[0] or 0) - (next_bbox[0] or 0)) <= 12
        if 0 <= vertical_gap <= 12 and same_left and not is_sentence_terminal(unit.get("raw_text", "")) and starts_like_continuation(nxt.get("raw_text", "")):
            text = f"{unit['raw_text'].strip()} {nxt['raw_text'].strip()}"
            refs = [unit["unit_id"], nxt["unit_id"]]
            outputs.append(output_block(f"out:{unit['unit_id']}:join", text, refs, "B1_join_paragraph_fragment", "merged", unit.get("page"), 0.86))
            used.update(refs)
            findings.append(finding("B1", refs, text))

    # D1/E1: low-risk single-block normalization.
    for unit in sorted(blocks, key=reading_order):
        if unit["unit_id"] in used:
            continue
        raw = unit.get("raw_text", "")
        bullet_text = normalize_bullets(raw)
        symbol_text = repair_symbols(bullet_text)
        if symbol_text != raw:
            rule_id = "E1" if repair_symbols(raw) != raw else "D1"
            operation = "E1_repair_symbol_corruption" if rule_id == "E1" else "D1_normalize_bullet"
            outputs.append(output_block(f"out:{unit['unit_id']}", symbol_text, [unit["unit_id"]], operation, "emitted", unit.get("page"), 0.88))
            findings.append(finding(rule_id, [unit["unit_id"]], symbol_text))
        else:
            outputs.append(output_block(f"out:{unit['unit_id']}", raw, [unit["unit_id"]], "emit", "emitted", unit.get("page")))
        used.add(unit["unit_id"])
    return outputs, findings, []


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply MVP PDF layout repairs.")
    parser.add_argument("source_inventory", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=Path("repaired_blocks.json"))
    args = parser.parse_args()
    inventory = json.loads(args.source_inventory.read_text(encoding="utf-8-sig"))
    outputs, findings, review_items = apply_repairs(inventory.get("units", []))
    result = {
        "schema_version": "0.1",
        "source_inventory": str(args.source_inventory),
        "output_blocks": outputs,
        "findings": findings,
        "needs_review": review_items,
        "not_implemented": [],
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
