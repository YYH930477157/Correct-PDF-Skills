#!/usr/bin/env python3
"""Build source_inventory.json from MinerU JSON."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from canonicalize import normalize_for_audit


def stable_id(*parts: object) -> str:
    text = "|".join(str(p) for p in parts)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def span_text(span: dict[str, Any]) -> str:
    if span.get("type") == "table" and span.get("html"):
        return span["html"]
    return span.get("content") or span.get("text") or ""


def block_text(block: dict[str, Any]) -> str:
    out: list[str] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            if isinstance(obj.get("spans"), list):
                out.extend(span_text(span) for span in obj["spans"])
            for key in ("lines", "blocks"):
                if key in obj:
                    walk(obj[key])
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(block)
    return "\n".join(part.strip() for part in out if part and part.strip()).strip()


def shingles(text: str, size: int = 8, limit: int = 10) -> list[str]:
    words = re.findall(r"\S+", normalize_for_audit(text))
    if len(words) < size:
        return []
    step = max(1, len(words) // limit)
    result = []
    for start in range(0, len(words) - size + 1, step):
        result.append(" ".join(words[start : start + size]))
        if len(result) >= limit:
            break
    return result


def make_unit(engine: str, page: int, index: str, granularity: str, dtype: str, raw_text: str, block: dict[str, Any]) -> dict[str, Any]:
    audit_text = normalize_for_audit(raw_text)
    canonical = "cu:" + stable_id(audit_text, granularity, dtype)
    unit_id = f"{engine}:p{page}:{index}"
    return {
        "unit_id": unit_id,
        "canonical_unit_id": canonical,
        "engine_unit_id": f"p{page}:{index}",
        "dedupe_group_id": "dg:" + stable_id(audit_text),
        "primary_engine": engine,
        "supporting_evidence": [],
        "granularity": granularity,
        "page": page,
        "dtype": dtype,
        "raw_text": raw_text,
        "audit_text": audit_text,
        "bbox": block.get("bbox"),
        "bbox_space": "pdf_points",
        "page_width": None,
        "page_height": None,
        "scale": 1.0,
        "metadata": {"block_type": block.get("type")},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build source_inventory.json from MinerU JSON.")
    parser.add_argument("mineru_json", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=Path("source_inventory.json"))
    args = parser.parse_args()

    data = json.loads(args.mineru_json.read_text(encoding="utf-8-sig"))
    pages = data.get("pdf_info", [])
    units: list[dict[str, Any]] = []
    for page in pages:
        page_idx = int(page.get("page_idx", len(units)))
        page_size = page.get("page_size") or [None, None]
        page_text_parts = []
        for group_name in ("para_blocks", "discarded_blocks"):
            for idx, block in enumerate(page.get(group_name, [])):
                raw = block_text(block)
                if not raw:
                    continue
                dtype = block.get("type") or group_name
                unit = make_unit("mineru", page_idx, f"{group_name}{idx}", "block", dtype, raw, block)
                unit["page_width"], unit["page_height"] = page_size[0], page_size[1]
                units.append(unit)
                page_text_parts.append(raw)
        page_raw = "\n".join(page_text_parts)
        page_unit = make_unit("mineru", page_idx, "page", "page", "page", page_raw, {"bbox": None, "type": "page"})
        page_unit["page_width"], page_unit["page_height"] = page_size[0], page_size[1]
        units.append(page_unit)
        for sidx, shingle in enumerate(shingles(page_raw)):
            units.append(make_unit("mineru", page_idx, f"shingle{sidx}", "text", "shingle", shingle, {"bbox": None, "type": "shingle"}))
    result = {"schema_version": "0.1", "source": str(args.mineru_json), "units": units}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
