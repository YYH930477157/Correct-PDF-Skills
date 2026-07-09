#!/usr/bin/env python3
"""Augment source inventory with source-PDF snippets for missing required anchors."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


REQUIRED_ANCHOR_RE = re.compile(r"\b(?:\d+(?:\.\d+)+|Table\s+\d+|Figure\s+\d+|Appendix\s+[A-Z])\b", re.I)
SECTION_ANCHOR_RE = re.compile(r"^\d+(?:\.\d+)+$")
TABLE_ANCHOR_RE = re.compile(r"^table\s+\d+$", re.I)
FIGURE_ANCHOR_RE = re.compile(r"^figure\s+\d+$", re.I)
APPENDIX_ANCHOR_RE = re.compile(r"^appendix\s+[a-z]$", re.I)


def normalize_anchor(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\u00a0", " ")).strip().lower()


def anchors(text: str) -> set[str]:
    return {normalize_anchor(match.group(0)) for match in REQUIRED_ANCHOR_RE.finditer(text or "")}


def structural_anchor_text(units: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for unit in units:
        dtype = unit.get("dtype")
        text = unit.get("audit_text") or unit.get("raw_text") or ""
        if dtype in {"title", "heading", "caption", "image", "figure"}:
            parts.append(text)
        elif dtype in {"table", "table_body"}:
            parts.extend(match.group(1) for match in re.finditer(r"<td[^>]*>\s*(\d+(?:\.\d+)+)\s*</td>", unit.get("raw_text", "") or "", re.I))
            if re.match(r"^\s*(?:Table|Figure)\s+\d+\b", unit.get("raw_text", "") or "", re.I):
                parts.append(text)
    return "\n".join(parts)


def slug(anchor: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalize_anchor(anchor)).strip("-") or "anchor"


def recovery_kind(anchor: str) -> str:
    normalized = normalize_anchor(anchor)
    if SECTION_ANCHOR_RE.match(normalized):
        return "section"
    if TABLE_ANCHOR_RE.match(normalized):
        return "table"
    if FIGURE_ANCHOR_RE.match(normalized):
        return "figure"
    if APPENDIX_ANCHOR_RE.match(normalized):
        return "appendix"
    return "anchor"


def is_plausible_section_anchor(anchor: str) -> bool:
    if not SECTION_ANCHOR_RE.match(anchor):
        return False
    parts = [int(part) for part in anchor.split(".")]
    if not parts:
        return False
    if parts[0] == 0 or parts[0] > 20:
        return False
    if len(parts) >= 4 and parts[-1] in {255, 0}:
        return False
    if len(parts) == 2 and parts[1] >= 100:
        return False
    if len(parts) > 6:
        return False
    return True


def recovery_dtype(kind: str) -> str:
    if kind in {"section", "appendix"}:
        return "title"
    if kind in {"table", "figure"}:
        return "caption"
    return "source_pdf_recovery"


def pseudo_bbox(hit: dict[str, Any], ordinal: int) -> list[float]:
    if isinstance(hit.get("bbox"), list) and len(hit["bbox"]) == 4:
        return hit["bbox"]
    y = hit.get("y")
    if isinstance(y, (int, float)):
        return [0, float(y), 0, float(y)]
    char_start = hit.get("char_start")
    if isinstance(char_start, (int, float)):
        return [0, float(char_start), 0, float(char_start)]
    order = hit.get("order")
    if isinstance(order, (int, float)):
        return [0, float(order), 0, float(order)]
    return [0, float(ordinal), 0, float(ordinal)]


def trim_to_anchor(snippet: str, anchor: str) -> str:
    match = re.search(rf"(?<![\w.]){re.escape(anchor)}(?![\w.])", snippet, re.I)
    if not match:
        return snippet
    return snippet[match.start() :].strip()


def credible_recovery_snippet(snippet: str, anchor: str, kind: str) -> bool:
    normalized = re.sub(r"\s+", " ", snippet or "").strip()
    lower = normalized.lower()
    if not normalized:
        return False
    if re.search(r"\.{6,}", normalized):
        return False
    if re.search(rf"\b(?:see|refer to|referring to|paragraph|clause|section)\s+{re.escape(anchor)}\b", lower):
        return False
    if kind == "section":
        if not is_plausible_section_anchor(anchor):
            return False
        if re.fullmatch(r"\d+\.\d{3,}(?:\.\d{3,})*", anchor):
            return False
        after = trim_to_anchor(normalized, anchor)[len(anchor) :].strip()
        if not re.match(r"^[A-Za-z\u00c0-\u024f][A-Za-z\u00c0-\u024f0-9 /(),'-]{2,}", after):
            return False
        if re.match(r"^(?:u\d+|r\b|w\b|litre|liter|m3|mc|bar|bytes?|string|specific)\b", after, re.I):
            return False
    return True


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Recover source-PDF anchors missing from MinerU inventory.")
    parser.add_argument("source_inventory", type=Path)
    parser.add_argument("source_pdf_audit", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=Path("source_inventory_recovered.json"))
    args = parser.parse_args()

    inventory = load_json(args.source_inventory)
    source_pdf_audit = load_json(args.source_pdf_audit)
    units = list(inventory.get("units", []))
    inventory_text = "\n".join(unit.get("audit_text") or unit.get("raw_text") or "" for unit in units)
    inventory_anchors = anchors(inventory_text)
    source_anchors = set()
    for value in source_pdf_audit.get("anchors", []):
        source_anchors.update(anchors(str(value)))
    missing = sorted(source_anchors - inventory_anchors)
    locations = source_pdf_audit.get("anchor_locations", {})
    recovered = []
    seen_snippets: set[tuple[int, str]] = set()
    for ordinal, anchor in enumerate(missing):
        hits = locations.get(anchor) if isinstance(locations, dict) else None
        if not hits:
            continue
        kind = recovery_kind(anchor)
        hit = None
        snippet = ""
        for candidate in hits:
            candidate_snippet = re.sub(r"\s+", " ", str(candidate.get("snippet", ""))).strip()
            if credible_recovery_snippet(candidate_snippet, anchor, kind):
                hit = candidate
                snippet = trim_to_anchor(candidate_snippet, anchor)
                break
        if hit is None:
            continue
        page = int(hit.get("page", 0))
        if not snippet:
            continue
        key = (page, snippet.lower())
        if key in seen_snippets:
            continue
        seen_snippets.add(key)
        unit_id = f"source-pdf-recovery:p{page}:{slug(anchor)}"
        unit = {
            "unit_id": unit_id,
            "granularity": "block",
            "page": page,
            "dtype": recovery_dtype(kind),
            "raw_text": snippet,
            "audit_text": snippet.lower(),
            "bbox": pseudo_bbox(hit, ordinal),
            "recovery": {
                "rule_id": "G3R",
                "anchor": anchor,
                "kind": kind,
                "source": "source_pdf_audit",
                "requires_review": True,
            },
        }
        units.append(unit)
        recovered.append({"anchor": anchor, "unit_id": unit_id, "page": page, "snippet": snippet})

    inventory["units"] = units
    inventory["source_pdf_recovered_anchors"] = recovered
    args.output.write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
