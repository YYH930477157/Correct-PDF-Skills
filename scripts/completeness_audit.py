#!/usr/bin/env python3
"""Completeness audit for repair manifests."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from collections import Counter
from collections import defaultdict
from pathlib import Path
from typing import Any


REQUIRED_ANCHOR_RE = re.compile(r"\b(?:\d+(?:\.\d+)+|Table\s+\d+|Figure\s+\d+|Appendix\s+[A-Z])\b", re.I)
CANDIDATE_ANCHOR_RE = re.compile(
    r"\b(?:UNI(?:/[A-Z]+)?\s+\d+(?::\d+)?|EN\s+\d+(?::\d+)?|ISO\s+\d+(?::\d+)?|\d+(?:[.,]\d+)?\s*(?:bar|m3|m³|l/h|%|s|ms|V|Hz))\b",
    re.I,
)
FIGURE_TABLE_RE = re.compile(r"\b(?:Table|Figure)\s+\d+\b", re.I)
SECTION_ANCHOR_RE = re.compile(r"^\d+(?:\.\d+)+$")
TABLE_ANCHOR_RE = re.compile(r"^table\s+\d+$", re.I)
FIGURE_ANCHOR_RE = re.compile(r"^figure\s+\d+$", re.I)
APPENDIX_ANCHOR_RE = re.compile(r"^appendix\s+[a-z]$", re.I)


def normalize_anchor_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\u00a0", " ")).strip().lower()


def normalize_anchor(anchor: str) -> str:
    return normalize_anchor_text(anchor)


def anchors(text: str, regex: re.Pattern[str]) -> set[str]:
    return {normalize_anchor(m.group(0)) for m in regex.finditer(text or "")}


def anchor_present_in_text(anchor: str, text: str) -> bool:
    normalized_anchor = normalize_anchor(anchor)
    normalized_text = f" {normalize_anchor_text(text)} "
    if not normalized_anchor:
        return False
    return re.search(rf"(?<![\w.]){re.escape(normalized_anchor)}(?![\w.])", normalized_text) is not None


def missing_anchors(source: set[str], output: set[str], output_text: str) -> list[str]:
    return sorted(anchor for anchor in source - output if not anchor_present_in_text(anchor, output_text))


def filter_candidate_anchors(values: set[str]) -> set[str]:
    return {
        value
        for value in values
        if not re.fullmatch(r"(?:uni|en|iso)\s+\d{1,2}", value or "", re.I)
    }


def anchors_from_values(values: list[Any], regex: re.Pattern[str]) -> set[str]:
    found: set[str] = set()
    for value in values:
        found.update(anchors(str(value), regex))
    return found


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


def trim_to_anchor(snippet: str, anchor: str) -> str:
    match = re.search(rf"(?<![\w.]){re.escape(anchor)}(?![\w.])", snippet, re.I)
    if not match:
        return snippet
    return snippet[match.start() :].strip()


def credible_source_anchor_location(snippet: str, anchor: str) -> bool:
    normalized = re.sub(r"\s+", " ", snippet or "").strip()
    lower = normalized.lower()
    if not normalized:
        return False
    if re.search(r"\.{6,}", normalized):
        return False
    if re.search(rf"\b(?:see|refer to|referring to|paragraph|clause|section)\s+{re.escape(anchor)}\b", lower):
        return False
    kind = recovery_kind(anchor)
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


def source_pdf_structural_anchors(source_pdf_audit: dict[str, Any]) -> tuple[set[str], dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    locations = source_pdf_audit.get("anchor_locations", {})
    if not isinstance(locations, dict):
        return set(), {}, {}
    accepted: set[str] = set()
    accepted_locations: dict[str, list[dict[str, Any]]] = {}
    rejected_locations: dict[str, list[dict[str, Any]]] = {}
    for value in source_pdf_audit.get("anchors", []):
        for anchor in anchors(str(value), REQUIRED_ANCHOR_RE):
            hits = locations.get(anchor, [])
            credible = [hit for hit in hits if credible_source_anchor_location(str(hit.get("snippet", "")), anchor)]
            if credible:
                accepted.add(anchor)
                accepted_locations[anchor] = credible[:5]
            elif hits:
                rejected_locations[anchor] = hits[:5]
    return accepted, accepted_locations, rejected_locations


def source_pdf_has_anchor(source_pdf_audit: dict[str, Any] | None, anchor: str) -> bool:
    if not source_pdf_audit:
        return True
    normalized = normalize_anchor(anchor)
    locations = source_pdf_audit.get("anchor_locations", {})
    if isinstance(locations, dict) and locations.get(normalized):
        return any(credible_source_anchor_location(str(hit.get("snippet", "")), normalized) for hit in locations.get(normalized, []))
    source_anchors = {normalize_anchor(str(value)) for value in source_pdf_audit.get("anchors", [])}
    return normalized in source_anchors


def missing_sequence_anchors(item: dict[str, Any]) -> list[str]:
    reason = item.get("reason", "")
    previous = item.get("previous")
    current = item.get("current")
    if previous is None or current is None:
        return []
    if "table_number_sequence_gap" in reason:
        return [f"table {n}" for n in range(int(previous) + 1, int(current))]
    if "figure_number_sequence_gap" in reason:
        return [f"figure {n}" for n in range(int(previous) + 1, int(current))]
    if item.get("rule_id") in {"A2", "F1"} and isinstance(previous, str) and isinstance(current, str):
        if re.fullmatch(r"\d+(?:\.\d+)*", previous) and re.fullmatch(r"\d+(?:\.\d+)*", current):
            prev_parts = [int(part) for part in previous.split(".")]
            cur_parts = [int(part) for part in current.split(".")]
            if len(prev_parts) == len(cur_parts) and prev_parts[:-1] == cur_parts[:-1]:
                return [".".join(map(str, prev_parts[:-1] + [n])) for n in range(prev_parts[-1] + 1, cur_parts[-1])]
    return []


def should_suppress_sequence_gap(item: dict[str, Any], source_pdf_audit: dict[str, Any] | None) -> bool:
    if item.get("rule_id") not in {"A2", "F1", "F2"}:
        return False
    missing = missing_sequence_anchors(item)
    return bool(missing) and not any(source_pdf_has_anchor(source_pdf_audit, anchor) for anchor in missing)


def char_count(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def file_sha256(path: Path | None) -> str | None:
    if not path:
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_pdf_evidence_findings(
    source_pdf_audit: dict[str, Any] | None,
    source_units: list[dict[str, Any]],
    output_blocks: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not source_pdf_audit:
        return {"status": "not_provided", "missing_inventory_pages": [], "missing_media_pages": []}, []
    inventory_pages = {int(unit.get("page", 0)) for unit in source_units}
    emitted_refs = {
        str(ref)
        for block in output_blocks
        if block.get("disposition") != "discarded"
        for ref in block.get("source_refs", [])
    }
    media_types = {"image", "figure", "caption", "table", "table_body"}
    emitted_media_pages = {
        int(unit.get("page", 0))
        for unit in source_units
        if unit.get("unit_id") in emitted_refs and str(unit.get("dtype", "")).lower() in media_types
    }
    missing_inventory_pages = []
    missing_media_pages = []
    for page in source_pdf_audit.get("pages", []):
        page_index = int(page.get("page", 0))
        has_source_evidence = bool(page.get("text_chars", 0) or page.get("image_count", 0) or page.get("drawing_count", 0))
        if has_source_evidence and page_index not in inventory_pages:
            missing_inventory_pages.append(page_index)
        significant_images = int(page.get("significant_image_count", page.get("image_count", 0) if not page.get("text_chars", 0) else 0))
        significant_drawings = int(page.get("significant_drawing_count", 0))
        if (significant_images or significant_drawings) and page_index not in emitted_media_pages:
            missing_media_pages.append(
                {
                    "page": page_index,
                    "significant_image_count": significant_images,
                    "significant_drawing_count": significant_drawings,
                }
            )
    findings = []
    if missing_inventory_pages:
        findings.append({"rule_id": "G1P", "reason": "source_pdf_page_has_no_inventory_evidence", "pages": sorted(set(missing_inventory_pages))})
    if missing_media_pages:
        findings.append({"rule_id": "G4M", "reason": "source_pdf_media_has_no_emitted_media_evidence", "pages": missing_media_pages[:100]})
    return {
        "status": "review" if findings else "pass",
        "source_page_count": source_pdf_audit.get("page_count"),
        "inventory_pages": sorted(inventory_pages),
        "emitted_media_pages": sorted(emitted_media_pages),
        "missing_inventory_pages": sorted(set(missing_inventory_pages)),
        "missing_media_pages": missing_media_pages[:100],
    }, findings


def canonical_tokens(text: str) -> list[str]:
    decoded = html.unescape(text or "")
    decoded = re.sub(r"</?\s*[A-Za-z][A-Za-z0-9:-]*(?:\s+[^<>]*?)?>", " ", decoded)
    decoded = decoded.replace("-", " ").replace("/", " ")
    return re.findall(r"[0-9a-z\u00c0-\u024f]+", decoded.lower())


def token_coverage(source: str, output: str) -> float:
    source_tokens = canonical_tokens(source)
    output_counts = Counter(canonical_tokens(output))
    if not source_tokens:
        return 1.0
    present = 0
    for token in source_tokens:
        if output_counts[token] > 0:
            present += 1
            output_counts[token] -= 1
    return present / len(source_tokens)


def semantic_sample_units(units: list[dict[str, Any]], dispositions: dict[str, str]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for unit in units:
        if unit.get("granularity") != "block" or dispositions.get(unit.get("unit_id")) == "discarded":
            continue
        if (unit.get("recovery") or {}).get("requires_review"):
            continue
        text = unit.get("audit_text") or unit.get("raw_text") or ""
        if len(canonical_tokens(text)) >= 8:
            candidates.append(unit)
    if len(candidates) <= 8:
        return candidates
    indexes = {0, len(candidates) - 1, len(candidates) // 2}
    stride = max(1, len(candidates) // 5)
    indexes.update(range(0, len(candidates), stride))
    return [candidates[i] for i in sorted(indexes)[:8]]


def local_semantic_sampling(units: list[dict[str, Any]], dispositions: dict[str, str], output_blocks: list[dict[str, Any]]) -> dict[str, Any]:
    samples = []
    failures = []
    for unit in semantic_sample_units(units, dispositions):
        text = unit.get("audit_text") or unit.get("raw_text") or ""
        unit_id = unit.get("unit_id")
        mapped_text = "\n".join(
            block.get("audit_text") or block.get("raw_text") or ""
            for block in output_blocks
            if block.get("disposition") != "discarded" and unit_id in block.get("source_refs", [])
        )
        coverage = token_coverage(text, mapped_text)
        sample = {
            "unit_id": unit_id,
            "page": unit.get("page"),
            "coverage": round(coverage, 4),
            "token_count": len(canonical_tokens(text)),
        }
        samples.append(sample)
        if coverage < 0.85:
            failure = dict(sample)
            failure["sample"] = text[:240]
            failure["mapped_output_missing"] = not bool(mapped_text.strip())
            failures.append(failure)
    if not samples and any(
        unit.get("granularity") == "block"
        and dispositions.get(unit.get("unit_id")) != "discarded"
        and (unit.get("audit_text") or unit.get("raw_text") or "").strip()
        for unit in units
    ):
        return {
            "status": "review",
            "mode": "local_source_ref",
            "threshold": 0.85,
            "sample_count": 0,
            "samples": [],
            "failures": [],
            "reason": "non_empty_document_has_no_eligible_semantic_samples",
        }
    if failures:
        return {
            "status": "review",
            "mode": "local_source_ref",
            "threshold": 0.85,
            "sample_count": len(samples),
            "samples": samples,
            "failures": failures,
            "reason": "source-ref-local sample token coverage below threshold",
        }
    return {
        "status": "pass",
        "mode": "local_source_ref",
        "threshold": 0.85,
        "sample_count": len(samples),
        "samples": samples,
        "failures": [],
        "reason": "source-ref-local samples covered by mapped output",
    }


def item_refs(item: dict[str, Any]) -> set[str]:
    refs = set(str(ref) for ref in item.get("source_refs", []) if ref)
    for unit in item.get("units", []) if isinstance(item.get("units"), list) else []:
        if isinstance(unit, dict) and unit.get("unit_id"):
            refs.add(str(unit.get("unit_id")))
    return refs


def decision_refs(decision: dict[str, Any]) -> set[str]:
    refs = set(str(ref) for ref in decision.get("source_refs", []) if ref)
    refs.update(str(ref) for ref in decision.get("unit_ids", []) if ref)
    return refs


def stable_review_item_id(item: dict[str, Any]) -> str:
    payload = {
        "rule_id": item.get("rule_id"),
        "reason": item.get("reason"),
        "refs": sorted(item_refs(item)),
        "anchors": sorted(str(value) for value in item.get("anchors", []) if value),
        "pages": item.get("pages", []),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"review:{item.get('rule_id', 'unknown')}:{hashlib.sha256(encoded).hexdigest()[:20]}"


def assign_review_item_ids(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prepared = []
    for item in items:
        copy = dict(item)
        copy["review_item_id"] = stable_review_item_id(copy)
        prepared.append(copy)
    return prepared


def decision_matches_item(decision: dict[str, Any], item: dict[str, Any]) -> bool:
    if decision.get("action") != "accept_review":
        return False
    if decision.get("rule_id") != item.get("rule_id"):
        return False
    if decision.get("review_item_id") != item.get("review_item_id"):
        return False
    refs = decision_refs(decision)
    if refs:
        return refs == item_refs(item)
    reason = decision.get("match_reason")
    return bool(reason and reason == item.get("reason"))


def apply_review_decisions(
    needs_review: list[dict[str, Any]],
    decisions_doc: dict[str, Any] | None,
    artifact_context: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not decisions_doc:
        return needs_review, {"status": "not_provided", "applied": [], "rejected": []}
    reviewer = decisions_doc.get("reviewer")
    reviewed_at = decisions_doc.get("reviewed_at")
    applied: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    if not reviewer or not reviewed_at:
        return needs_review, {"status": "invalid", "reason": "missing_reviewer_or_reviewed_at", "applied": [], "rejected": decisions_doc.get("decisions", [])}
    expected = artifact_context or {}
    supplied = decisions_doc.get("artifacts") or {}
    mismatches = {
        key: {"expected": value, "supplied": supplied.get(key)}
        for key, value in expected.items()
        if value and supplied.get(key) != value
    }
    if mismatches:
        return needs_review, {"status": "invalid", "reason": "artifact_hash_mismatch", "mismatches": mismatches, "applied": [], "rejected": decisions_doc.get("decisions", [])}
    decisions = decisions_doc.get("decisions", [])
    unresolved: list[dict[str, Any]] = []
    used_decisions: set[int] = set()
    for item in needs_review:
        matched_index = None
        matched_decision = None
        for index, decision in enumerate(decisions):
            if index in used_decisions:
                continue
            if not decision.get("reason"):
                continue
            if decision_matches_item(decision, item):
                matched_index = index
                matched_decision = decision
                break
        if matched_decision is None or matched_index is None:
            unresolved.append(item)
            continue
        used_decisions.add(matched_index)
        applied.append(
            {
                "review_item_id": item.get("review_item_id"),
                "rule_id": item.get("rule_id"),
                "item_reason": item.get("reason"),
                "reviewer": reviewer,
                "decision_reason": matched_decision.get("reason"),
                "source_refs": sorted(item_refs(item)),
            }
        )
    for index, decision in enumerate(decisions):
        if index not in used_decisions:
            rejected.append({"decision": decision, "reason": "no_exact_matching_review_item_or_missing_reason"})
    return unresolved, {"status": "applied", "reviewer": reviewer, "applied": applied, "rejected": rejected}


def page_text(units: list[dict[str, Any]], dispositions: dict[str, str] | None = None) -> dict[int, str]:
    pages: dict[int, list[str]] = defaultdict(list)
    for unit in units:
        if dispositions and dispositions.get(unit.get("unit_id")) == "discarded":
            continue
        if unit.get("granularity") == "block":
            pages[int(unit.get("page", 0))].append(unit.get("audit_text") or unit.get("raw_text") or "")
    return {page: "\n".join(parts) for page, parts in pages.items()}


def output_page_text(blocks: list[dict[str, Any]]) -> dict[int, str]:
    pages: dict[int, list[str]] = defaultdict(list)
    for block in blocks:
        if block.get("disposition") == "discarded":
            continue
        page = block.get("page")
        if page is not None:
            pages[int(page)].append(block.get("audit_text") or block.get("raw_text") or "")
    return {page: "\n".join(parts) for page, parts in pages.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run completeness audit.")
    parser.add_argument("source_inventory", type=Path)
    parser.add_argument("repair_manifest", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=Path("completeness_report.json"))
    parser.add_argument("--text-threshold", type=float, default=0.92)
    parser.add_argument("--source-pdf-audit", type=Path, help="Optional independent PyMuPDF source audit JSON.")
    parser.add_argument("--review-decisions", type=Path, help="Optional audited review decision JSON for resolving matched needs_review findings.")
    args = parser.parse_args()
    inventory = json.loads(args.source_inventory.read_text(encoding="utf-8-sig"))
    manifest = json.loads(args.repair_manifest.read_text(encoding="utf-8-sig"))
    source_pdf_audit = json.loads(args.source_pdf_audit.read_text(encoding="utf-8-sig")) if args.source_pdf_audit else None
    review_decisions = json.loads(args.review_decisions.read_text(encoding="utf-8-sig")) if args.review_decisions else None
    source_units = inventory.get("units", [])
    output_blocks = manifest.get("output_blocks", [])
    dispositions = manifest.get("source_dispositions", {})
    source_text = "\n".join((u.get("audit_text") or u.get("raw_text") or "") for u in source_units if u.get("granularity") in {"block", "page"} and dispositions.get(u.get("unit_id")) != "discarded")
    output_text = "\n".join((b.get("audit_text") or b.get("raw_text") or "") for b in output_blocks if b.get("disposition") != "discarded")

    content_loss: list[dict[str, Any]] = []
    needs_review: list[dict[str, Any]] = []
    audits: dict[str, Any] = {}

    source_pages = page_text(source_units, dispositions)
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
    suppressed_review = []
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
        "suppressed_review": suppressed_review[:100],
    }
    if low_coverage:
        content_loss.append({"rule_id": "G2", "reason": "page_text_coverage_below_threshold", "pages": low_coverage[:100]})
    if review_coverage:
        needs_review.append({"rule_id": "G2", "reason": "page_text_coverage_in_review_band", "pages": review_coverage[:100]})

    required_source = anchors(source_text, REQUIRED_ANCHOR_RE)
    required_output = anchors(output_text, REQUIRED_ANCHOR_RE)
    candidate_source = filter_candidate_anchors(anchors(source_text, CANDIDATE_ANCHOR_RE))
    candidate_output = filter_candidate_anchors(anchors(output_text, CANDIDATE_ANCHOR_RE))
    missing_required = missing_anchors(required_source, required_output, output_text)
    missing_candidate = missing_anchors(candidate_source, candidate_output, output_text)
    source_pdf_required: set[str] = set()
    missing_source_pdf_required: list[str] = []
    missing_source_pdf_locations: dict[str, list[dict[str, Any]]] = {}
    source_pdf_nonstructural_locations: dict[str, list[dict[str, Any]]] = {}
    if source_pdf_audit:
        source_pdf_required, source_pdf_structural_locations, source_pdf_nonstructural_locations = source_pdf_structural_anchors(source_pdf_audit)
        missing_source_pdf_required = missing_anchors(source_pdf_required, required_output, output_text)
        missing_source_pdf_locations = {
            anchor: source_pdf_structural_locations.get(anchor, [])[:5]
            for anchor in missing_source_pdf_required
            if source_pdf_structural_locations.get(anchor)
        }
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
        "missing_source_pdf_locations": missing_source_pdf_locations,
        "source_pdf_nonstructural_locations": source_pdf_nonstructural_locations,
        "missing_candidate": missing_candidate[:200],
    }
    if missing_required:
        content_loss.append({"rule_id": "G3", "reason": "required_anchor_missing", "anchors": missing_required})
    if missing_source_pdf_required:
        content_loss.append(
            {
                "rule_id": "G3P",
                "reason": "independent_source_pdf_required_anchor_missing",
                "anchors": missing_source_pdf_required,
                "locations": missing_source_pdf_locations,
            }
        )
    if missing_candidate:
        needs_review.append({"rule_id": "G3C", "reason": "candidate_anchor_missing", "anchors": missing_candidate[:200]})

    source_figures = sorted(anchors(source_text, FIGURE_TABLE_RE))
    output_figures = sorted(anchors(output_text, FIGURE_TABLE_RE))
    media_audit, media_findings = source_pdf_evidence_findings(source_pdf_audit, source_units, output_blocks)
    audits["G4_figure_table_audit"] = {
        "source_figure_table_anchors": source_figures,
        "output_figure_table_anchors": output_figures,
        "missing": sorted(set(source_figures) - set(output_figures)),
        "source_pdf_media": media_audit,
    }
    needs_review.extend(media_findings)

    unmapped = [u["unit_id"] for u in source_units if dispositions.get(u["unit_id"]) == "escalated" and u.get("granularity") == "block"]
    if unmapped:
        content_loss.append({"rule_id": "H2", "reason": "unmapped_source_blocks", "source_refs": unmapped[:100]})

    recovered_units = [
        {
            "unit_id": unit.get("unit_id"),
            "page": unit.get("page"),
            "anchor": (unit.get("recovery") or {}).get("anchor"),
            "kind": (unit.get("recovery") or {}).get("kind"),
            "dtype": unit.get("dtype"),
            "sample": unit.get("raw_text", "")[:240],
        }
        for unit in source_units
        if (unit.get("recovery") or {}).get("requires_review")
    ]
    if recovered_units:
        audits["G3R_source_pdf_recovery"] = {
            "count": len(recovered_units),
            "units": recovered_units[:100],
        }
        needs_review.append({"rule_id": "G3R", "reason": "source_pdf_recovered_content_requires_review", "units": recovered_units[:100]})

    g5_audit = local_semantic_sampling(source_units, dispositions, output_blocks)
    audits["G5_ai_semantic_sampling"] = g5_audit
    if g5_audit.get("status") == "review":
        needs_review.append({"rule_id": "G5", "reason": "local_semantic_sampling_below_threshold", "failures": g5_audit.get("failures", [])[:20]})

    suppressed_sequence_gaps: list[dict[str, Any]] = []
    for item in manifest.get("needs_review", []):
        if should_suppress_sequence_gap(item, source_pdf_audit):
            suppressed = dict(item)
            suppressed["suppressed_reason"] = "missing_sequence_anchor_not_found_in_independent_source_pdf_audit"
            suppressed["missing_sequence_anchors"] = missing_sequence_anchors(item)
            suppressed_sequence_gaps.append(suppressed)
            continue
        needs_review.append(item)
    if suppressed_sequence_gaps:
        audits["sequence_gap_suppressed"] = suppressed_sequence_gaps[:100]
    for item in manifest.get("not_implemented", []):
        needs_review.append({"rule_id": item["rule_id"], "reason": "not_implemented_if_applicable"})

    needs_review = assign_review_item_ids(needs_review)
    artifact_context = {
        "source_inventory_sha256": file_sha256(args.source_inventory),
        "repair_manifest_sha256": file_sha256(args.repair_manifest),
    }
    if source_pdf_audit:
        artifact_context["source_pdf_audit_sha256"] = file_sha256(args.source_pdf_audit)
        if source_pdf_audit.get("source_pdf_sha256"):
            artifact_context["source_pdf_sha256"] = source_pdf_audit["source_pdf_sha256"]
    needs_review, review_decision_audit = apply_review_decisions(needs_review, review_decisions, artifact_context)
    review_decision_audit["artifact_context"] = artifact_context
    audits["review_decisions"] = review_decision_audit

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
