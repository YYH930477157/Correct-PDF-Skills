#!/usr/bin/env python3
"""Completeness audit for repair manifests."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


REQUIRED_ANCHOR_RE = re.compile(r"\b(?:\d+(?:\.\d+)+|Table\s+\d+|Figure\s+\d+|Appendix\s+[A-Z])\b", re.I)
CANDIDATE_ANCHOR_RE = re.compile(
    r"\b(?:UNI(?:/[A-Z]+)?\s+\d+(?::\d+)?|EN\s+\d+(?::\d+)?|ISO\s+\d+(?::\d+)?|\d+(?:[.,]\d+)?\s*(?:bar|m3|m³|l/h|%|s|ms|V|Hz))\b",
    re.I,
)
FIGURE_TABLE_RE = re.compile(r"\b(?:Table|Figure)\s+\d+\b", re.I)


def anchors(text: str, regex: re.Pattern[str]) -> set[str]:
    return {m.group(0).lower() for m in regex.finditer(text or "")}


def char_count(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def token_coverage(source: str, output: str) -> float:
    source_tokens = re.findall(r"\S+", (source or "").lower())
    output_tokens = set(re.findall(r"\S+", (output or "").lower()))
    if not source_tokens:
        return 1.0
    present = sum(1 for token in source_tokens if token in output_tokens)
    return present / len(source_tokens)


def page_text(units: list[dict[str, Any]]) -> dict[int, str]:
    pages: dict[int, list[str]] = defaultdict(list)
    for unit in units:
        if unit.get("granularity") == "block":
            pages[int(unit.get("page", 0))].append(unit.get("audit_text", ""))
    return {page: "\n".join(parts) for page, parts in pages.items()}


def output_page_text(blocks: list[dict[str, Any]]) -> dict[int, str]:
    pages: dict[int, list[str]] = defaultdict(list)
    for block in blocks:
        page = block.get("page")
        if page is not None:
            pages[int(page)].append(block.get("audit_text", ""))
    return {page: "\n".join(parts) for page, parts in pages.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run completeness audit.")
    parser.add_argument("source_inventory", type=Path)
    parser.add_argument("repair_manifest", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=Path("completeness_report.json"))
    parser.add_argument("--text-threshold", type=float, default=0.92)
    parser.add_argument("--source-pdf-audit", type=Path, help="Optional independent PyMuPDF source audit JSON.")
    args = parser.parse_args()
    inventory = json.loads(args.source_inventory.read_text(encoding="utf-8-sig"))
    manifest = json.loads(args.repair_manifest.read_text(encoding="utf-8-sig"))
    source_pdf_audit = json.loads(args.source_pdf_audit.read_text(encoding="utf-8-sig")) if args.source_pdf_audit else None
    source_units = inventory.get("units", [])
    output_blocks = manifest.get("output_blocks", [])
    source_text = "\n".join(u.get("audit_text", "") for u in source_units if u.get("granularity") in {"block", "page"})
    output_text = "\n".join(b.get("audit_text", "") for b in output_blocks)

    content_loss: list[dict[str, Any]] = []
    needs_review: list[dict[str, Any]] = []
    audits: dict[str, Any] = {}

    source_pages = page_text(source_units)
    output_pages = output_page_text(output_blocks)
    missing_pages = [page for page, text in source_pages.items() if text.strip() and not output_pages.get(page, "").strip()]
    audits["G1_page_coverage"] = {
        "source_pages_with_text": sorted(source_pages),
        "output_pages_with_text": sorted(output_pages),
        "missing_pages": missing_pages,
    }
    if missing_pages:
        content_loss.append({"rule_id": "G1", "reason": "source_page_has_no_output_content", "pages": missing_pages})

    page_ratios = {}
    low_coverage = []
    review_coverage = []
    hard_floor = max(0.5, args.text_threshold - 0.15)
    for page, text in source_pages.items():
        source_chars = char_count(text)
        if source_chars == 0:
            continue
        output_for_page = output_pages.get(page, "")
        char_ratio = char_count(output_for_page) / source_chars
        ratio = token_coverage(text, output_for_page)
        page_ratios[str(page)] = round(ratio, 4)
        item = {
            "page": page,
            "ratio": round(ratio, 4),
            "char_ratio": round(char_ratio, 4),
            "source_chars": source_chars,
            "output_chars": char_count(output_for_page),
        }
        if ratio < hard_floor:
            low_coverage.append(item)
        elif ratio < args.text_threshold:
            review_coverage.append(item)
    audits["G2_text_amount"] = {
        "threshold": args.text_threshold,
        "hard_floor": round(hard_floor, 4),
        "page_ratios": page_ratios,
        "low_coverage": low_coverage[:100],
        "review_coverage": review_coverage[:100],
    }
    if low_coverage:
        content_loss.append({"rule_id": "G2", "reason": "page_text_coverage_below_threshold", "pages": low_coverage[:100]})
    if review_coverage:
        needs_review.append({"rule_id": "G2", "reason": "page_text_coverage_in_review_band", "pages": review_coverage[:100]})

    required_source = anchors(source_text, REQUIRED_ANCHOR_RE)
    required_output = anchors(output_text, REQUIRED_ANCHOR_RE)
    candidate_source = anchors(source_text, CANDIDATE_ANCHOR_RE)
    candidate_output = anchors(output_text, CANDIDATE_ANCHOR_RE)
    missing_required = sorted(required_source - required_output)
    missing_candidate = sorted(candidate_source - candidate_output)
    source_pdf_required: set[str] = set()
    missing_source_pdf_required: list[str] = []
    if source_pdf_audit:
        source_pdf_required = anchors("\n".join(source_pdf_audit.get("anchors", [])), REQUIRED_ANCHOR_RE)
        missing_source_pdf_required = sorted(source_pdf_required - required_output)
    audits["G3_anchor_audit"] = {
        "required_source_count": len(required_source),
        "required_output_count": len(required_output),
        "source_pdf_required_count": len(source_pdf_required),
        "candidate_source_count": len(candidate_source),
        "required_source_anchors": sorted(required_source),
        "required_output_anchors": sorted(required_output),
        "source_pdf_required_anchors": sorted(source_pdf_required),
        "candidate_source_anchors": sorted(candidate_source)[:500],
        "missing_required": missing_required,
        "missing_source_pdf_required": missing_source_pdf_required,
        "missing_candidate": missing_candidate[:200],
    }
    if missing_required:
        content_loss.append({"rule_id": "G3", "reason": "required_anchor_missing", "anchors": missing_required})
    if missing_source_pdf_required:
        content_loss.append({"rule_id": "G3P", "reason": "independent_source_pdf_required_anchor_missing", "anchors": missing_source_pdf_required})
    if missing_candidate:
        needs_review.append({"rule_id": "G3C", "reason": "candidate_anchor_missing", "anchors": missing_candidate[:200]})

    source_figures = sorted(anchors(source_text, FIGURE_TABLE_RE))
    output_figures = sorted(anchors(output_text, FIGURE_TABLE_RE))
    audits["G4_figure_table_audit"] = {
        "source_figure_table_anchors": source_figures,
        "output_figure_table_anchors": output_figures,
        "missing": sorted(set(source_figures) - set(output_figures)),
    }

    dispositions = manifest.get("source_dispositions", {})
    unmapped = [u["unit_id"] for u in source_units if dispositions.get(u["unit_id"]) == "escalated" and u.get("granularity") == "block"]
    if unmapped:
        content_loss.append({"rule_id": "H2", "reason": "unmapped_source_blocks", "source_refs": unmapped[:100]})

    audits["G5_ai_semantic_sampling"] = {
        "status": "not_configured",
        "reason": "LLM API intentionally left blank; semantic sampling must produce needs_review findings when enabled.",
    }
    needs_review.append({"rule_id": "G5", "reason": "ai_semantic_sampling_not_configured"})

    for item in manifest.get("needs_review", []):
        needs_review.append(item)
    for item in manifest.get("not_implemented", []):
        needs_review.append({"rule_id": item["rule_id"], "reason": "not_implemented_if_applicable"})

    status = "review" if content_loss else ("draft" if needs_review else "final")
    report = {
        "schema_version": "0.2",
        "document_status": status,
        "source_inventory": str(args.source_inventory),
        "repair_manifest": str(args.repair_manifest),
        "audits": audits,
        "content_loss": content_loss,
        "needs_review": needs_review,
        "auto_fixed": manifest.get("findings", []),
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
