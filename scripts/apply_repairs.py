#!/usr/bin/env python3
"""Apply deterministic PDF layout repairs and produce repaired_blocks.json."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any


SECTION_RE = re.compile(r"^(?:\d+(?:\.\d+)*|[A-Z](?:\.\d+)*)$")
FOOTNOTE_START_RE = re.compile(r"^\s*\d+\)")
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
    "\u2264": "<=",
    "\u2265": ">=",
}
ITALIAN_TERMS = {
    "il",
    "la",
    "lo",
    "gli",
    "dei",
    "delle",
    "del",
    "della",
    "di",
    "ed",
    "che",
    "nel",
    "nella",
    "per",
    "un",
    "una",
    "contatore",
    "deve",
    "essere",
    "configurato",
    "funzioni",
    "introduzione",
    "scopo",
    "riferimenti",
    "normativi",
    "termini",
    "definizioni",
    "sigle",
    "abbreviazioni",
    "generalita",
    "spiegazione",
    "tabella",
    "oggetti",
    "giorno",
    "settimana",
    "valore",
    "descrizione",
    "ogni",
    "inizio",
    "mese",
    "mesi",
    "espresso",
    "locale",
    "caso",
    "campi",
    "elemento",
    "devono",
    "dato",
    "diagnostica",
    "relativa",
    "utilizzare",
    "remoto",
}
KNOWN_UNITS = {"bar", "m3/h", "m³/h", "m3", "m³", "l/h", "%", "s", "ms", "v", "hz"}
HEADER_FOOTER_RE = re.compile(r"(?:\b(?:UNI/TS|UNI EN|ISO|Page\s+\d+|Pagina\s+\d+|Copyright)\b|\u00a9)", re.I)
TERM_RE = re.compile(r"\b([a-z][a-z -]{3,30})\s+(?:is|means|refers to|defined as)\b", re.I)
ENGLISH_CONTEXT_TERMS = {"before", "after", "shall", "should", "must", "commissioning", "system", "data", "remote", "meter"}
COMMON_SUBHEADING_LABELS = {
    "definition",
    "definition:",
    "definitions",
    "functional requirements",
    "general information",
    "generality",
    "generalita",
    "generalità",
    "measure",
    "regulations",
    "(regulations)",
}
NON_HEADING_ANCHOR_CONTEXT_RE = re.compile(
    r"^(?:or|and|superior|inferior|greater|less|test|value|values?|u\d+|r|w|litre|liter|m3|mc|bar|bytes?|string|specific)\b",
    re.I,
)
TECH_VALUE_PREFIX_RE = re.compile(r"\b(?:bluetooth|temperature|pressure|profile|declared|minimum|maximum|object|code|version)\s+$", re.I)
NON_DEFINITION_TABLE_TERMS_RE = re.compile(
    r"\b(?:point|diagnostics?|activation|anomal(?:y|ies)|rif|reference|clause|status|code|value|field|"
    r"object|obis|type|length|bytes?|bit|flag|error|alarm)\b",
    re.I,
)
DEFINITION_TABLE_HEADER_RE = re.compile(r"\b(?:term|terms|definition|definitions|abbreviation|abbreviations)\b", re.I)
MONTH_TERMS = {
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
    "gennaio",
    "febbraio",
    "marzo",
    "aprile",
    "maggio",
    "giugno",
    "luglio",
    "agosto",
    "settembre",
    "ottobre",
    "novembre",
    "dicembre",
}
NON_UNIT_WORDS = MONTH_TERMS | {"of", "to", "and", "or", "the", "a", "an", "in", "on", "for", "from", "with", "anni", "anno", "year", "years", "day", "days", "min"}
KNOWN_UNITS.update({"m", "mc", "mc/h", "min", "hour", "hours", "byte", "bytes", "bit", "bits", "mm", "dm", "dbm", "d", "sec", "kbps", "ora"})
NON_UNIT_WORDS.update(
    {
        "e",
        "si",
        "is",
        "o",
        "pf",
        "will",
        "must",
        "by",
        "are",
        "also",
        "ends",
        "most",
        "null",
        "we",
        "full",
        "time",
        "can",
        "so",
        "use",
        "am",
        "che",
        "come",
        "deve",
        "del",
        "dell",
        "di",
        "ed",
        "fa",
        "feb",
        "ha",
        "il",
        "la",
        "long",
        "max",
        "mese",
        "mesi",
        "non",
        "ore",
        "pm",
        "per",
        "plan",
        "push",
        "sia",
        "sono",
    }
)


def load_foreign_terms() -> set[str]:
    terms = set(ITALIAN_TERMS)
    inline = os.environ.get("PDF_LAYOUT_REPAIR_FOREIGN_TERMS", "")
    file_path = os.environ.get("PDF_LAYOUT_REPAIR_FOREIGN_TERMS_FILE", "")
    if inline:
        terms = {term.strip().lower() for term in re.split(r"[,;\n]", inline) if term.strip()}
    if file_path:
        path = Path(file_path)
        if path.exists():
            terms.update(term.strip().lower() for term in re.split(r"[,;\n]", path.read_text(encoding="utf-8-sig")) if term.strip())
    return terms


def cy(unit: dict[str, Any]) -> float:
    bbox = unit.get("bbox") or [0, 0, 0, 0]
    return (bbox[1] + bbox[3]) / 2


def is_left_isolated_section(unit: dict[str, Any]) -> bool:
    bbox = unit.get("bbox") or [999, 0, 999, 0]
    page_width = float(unit.get("page_width") or 595)
    return unit.get("granularity") == "block" and SECTION_RE.match(unit.get("raw_text", "").strip()) and bbox[0] < page_width * 0.2


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
    page_width = float(unit.get("page_width") or 595)
    return unit.get("dtype") == "toc_number" or (TOC_NUMBER_RE.match(text) and (unit.get("bbox") or [999])[0] < page_width * 0.16)


def is_toc_title(unit: dict[str, Any]) -> bool:
    return unit.get("dtype") == "toc_title"


def is_toc_page(unit: dict[str, Any]) -> bool:
    text = unit.get("raw_text", "").strip()
    bbox = unit.get("bbox") or [0, 0, 0, 0]
    page_width = float(unit.get("page_width") or 595)
    return unit.get("dtype") == "toc_page" or (text.isdigit() and bbox[0] >= page_width * 0.75)


def normalize_bullets(text: str) -> str:
    out = text
    for old, new in BULLET_REPLACEMENTS.items():
        out = out.replace(old, new)
    return re.sub(r"^\s*-\s*", "- ", out.strip())


def repair_symbols(text: str) -> str:
    out = text
    for old, new in SYMBOL_REPLACEMENTS.items():
        out = out.replace(old, new)
    out = re.sub(r"(?<=\d)\s*\u0177\s*(?=\d|\s*(?:bar|m3|m³|l/h|%|s|ms|V|Hz)\b)", " <= ", out, flags=re.I)
    out = re.sub(r"\b(pressure|flow|temperature|value|limit|max|min)\s*\u0177\s*(?=\d)", r"\1 <= ", out, flags=re.I)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out


def review(rule_id: str, source_refs: list[str], reason: str, severity: str = "needs_review", **extra: Any) -> dict[str, Any]:
    item = {"rule_id": rule_id, "severity": severity, "source_refs": source_refs, "reason": reason}
    item.update(extra)
    return item


def section_anchor(text: str) -> tuple[int, ...] | None:
    if is_footnote_start(text):
        return None
    match = re.match(r"^\s*(\d+(?:\.\d+)*)\b", text or "")
    if not match:
        return None
    after = (text or "")[match.end() : match.end() + 8]
    if after.startswith("%") or after.startswith(":"):
        return None
    first = match.group(1)
    if "." not in first and int(first) > 50:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def embedded_section_anchors(unit: dict[str, Any]) -> list[tuple[tuple[int, ...], str]]:
    text = unit.get("raw_text", "") or ""
    if unit.get("dtype") not in {"table", "table_body"} and "<table" not in text.lower():
        return []
    found: list[tuple[tuple[int, ...], str]] = []
    if should_use_table_cell_section_anchors(text):
        for idx, match in enumerate(re.finditer(r"<td[^>]*>\s*(\d+(?:\.\d+)+)\s*</td>", text, re.I)):
            anchor = tuple(int(part) for part in match.group(1).split("."))
            found.append((anchor, f"{unit['unit_id']}#embedded-section-{idx}:{match.group(1)}"))
    plain_segments = html_outside_table_segments(text) if "<table" in text.lower() else [text]
    for segment_index, text_for_plain_anchors in enumerate(plain_segments):
        if not text_for_plain_anchors.strip():
            continue
        for idx, match in enumerate(re.finditer(r"(?<![\w.])(\d+(?:\.\d+)+)\s+([A-Za-z\u00c0-\u024f][A-Za-z\u00c0-\u024f0-9 /(),'-]{2,})", text_for_plain_anchors)):
            anchor_text = match.group(1)
            following = match.group(2).strip()
            before = text_for_plain_anchors[max(0, match.start() - 32) : match.start()]
            if NON_HEADING_ANCHOR_CONTEXT_RE.match(following) or TECH_VALUE_PREFIX_RE.search(before):
                continue
            anchor = tuple(int(part) for part in anchor_text.split("."))
            ref = f"{unit['unit_id']}#embedded-section-text-{segment_index}-{idx}:{anchor_text}"
            if all(existing_ref != ref and existing_anchor != anchor for existing_anchor, existing_ref in found):
                found.append((anchor, ref))
    return found


def html_outside_table_segments(text: str) -> list[str]:
    segments: list[str] = []
    last_end = 0
    for match in re.finditer(r"<table\b.*?</table>", text or "", re.I | re.S):
        segments.append(text[last_end : match.start()])
        last_end = match.end()
    segments.append(text[last_end:])
    return segments


def html_table_rows(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for row_match in re.finditer(r"<tr[^>]*>(.*?)</tr>", text or "", re.I | re.S):
        cells = []
        for cell_match in re.finditer(r"<t[dh][^>]*>(.*?)</t[dh]>", row_match.group(1), re.I | re.S):
            cell = re.sub(r"<[^>]+>", " ", cell_match.group(1))
            cell = re.sub(r"\s+", " ", cell).strip()
            cells.append(cell)
        if cells:
            rows.append(cells)
    return rows


def looks_like_term_cell(text: str) -> bool:
    value = re.sub(r"\s+", " ", text or "").strip()
    if not value:
        return False
    words = value.split()
    if len(words) > 8:
        return False
    if re.search(r"[.;:?!]", value):
        return False
    if re.match(r"^(?:no|not|when|if|after|before|immediate|delayed|open|closed|active|inactive)\b", value, re.I):
        return False
    return bool(re.search(r"[A-Za-z\u00c0-\u024f]", value))


def should_use_table_cell_section_anchors(text: str) -> bool:
    if "<table" not in (text or "").lower():
        return False
    rows = html_table_rows(text)
    if not rows:
        return False
    header_text = " ".join(rows[0]).strip()
    full_text = " ".join(" ".join(row) for row in rows)
    if NON_DEFINITION_TABLE_TERMS_RE.search(header_text) and not DEFINITION_TABLE_HEADER_RE.search(header_text):
        return False
    if NON_DEFINITION_TABLE_TERMS_RE.search(full_text) and not DEFINITION_TABLE_HEADER_RE.search(full_text):
        return False
    candidate_rows = 0
    anchored_rows = 0
    for row in rows:
        if len(row) < 2:
            continue
        candidate_rows += 1
        if re.fullmatch(r"\d+(?:\.\d+)+", row[0]) and looks_like_term_cell(row[1]):
            anchored_rows += 1
    if anchored_rows < 2:
        return False
    return anchored_rows / max(candidate_rows, 1) >= 0.5


def numbered_anchor(text: str, label: str) -> int | None:
    match = re.search(rf"\b{label}\s+(\d+)\b", text or "", re.I)
    return int(match.group(1)) if match else None


def is_numbered_figure_table_source(unit: dict[str, Any], label: str, text: str) -> bool:
    dtype = unit.get("dtype")
    stripped = re.sub(r"\s+", " ", text or "").strip()
    caption_like = re.match(rf"^{label}\s+\d+\s*(?:[-–—:]\s*)?[^.?!]{{0,120}}$", stripped, re.I) is not None
    if label.lower() == "table":
        return dtype in {"table", "table_body", "caption"} or caption_like
    return dtype in {"image", "figure", "caption"} or caption_like


def is_mixed_foreign_contamination(audit: str, foreign_terms: set[str]) -> bool:
    tokens = re.findall(r"[a-z\u00e0-\u00ff]+", audit.lower())
    words = set(tokens)
    foreign_count = sum(1 for token in tokens if token in foreign_terms)
    english_count = sum(1 for token in tokens if token in ENGLISH_CONTEXT_TERMS)
    return foreign_count >= 2 and english_count >= 2 and foreign_count / max(len(tokens), 1) < 0.4


def is_foreign_dominant_document(blocks: list[dict[str, Any]], foreign_terms: set[str]) -> bool:
    tokens: list[str] = []
    for unit in blocks:
        if unit.get("dtype") in {"header", "footer", "page_number"}:
            continue
        text = unit.get("audit_text") or normalize_audit(unit.get("raw_text", ""))
        tokens.extend(re.findall(r"[a-z\u00e0-\u00ff]+", text.lower()))
    if len(tokens) < 20:
        return False
    foreign_count = sum(1 for token in tokens if token in foreign_terms)
    return foreign_count / max(len(tokens), 1) >= 0.06


def is_header_footer_candidate(unit: dict[str, Any], text: str, bbox: list[Any]) -> bool:
    if not (bbox[1] <= 50 or bbox[1] >= 760):
        return False
    stripped = re.sub(r"\s+", " ", text.strip())
    if unit.get("dtype", "").startswith("discarded"):
        return True
    if unit.get("dtype") in {"header", "footer", "page_number"} and len(stripped) <= 100:
        return True
    if re.search(r"\b(?:copyright|all rights reserved|riproduzione vietata)\b", stripped, re.I):
        return True
    return len(stripped) <= 60 and bool(HEADER_FOOTER_RE.search(stripped))


def is_safe_discard_header_footer(unit: dict[str, Any]) -> bool:
    text = unit.get("raw_text", "")
    bbox = unit.get("bbox") or [0, 0, 0, 0]
    dtype = unit.get("dtype", "")
    unit_id = unit.get("unit_id", "")
    discard_like = dtype.startswith("discarded") or dtype in {"header", "footer", "page_number"} or "discarded_blocks" in unit_id
    return discard_like and is_header_footer_candidate(unit, text, bbox)


def is_suspicious_unit(number: str, unit_text: str) -> bool:
    token = unit_text.strip()
    lower = token.lower()
    if not re.search(r"[A-Za-z]", token):
        return False
    if "." in number:
        return False
    if number.isdigit() and int(number) >= 1000:
        return False
    if lower in KNOWN_UNITS or lower.startswith("m3") or lower in NON_UNIT_WORDS:
        return False
    if token[:1].isupper():
        return False
    if "." in number and token[:1].isupper():
        return False
    if token.isupper() and len(token) > 1:
        return False
    return len(token) <= 4


def is_common_subheading(text: str) -> bool:
    label = re.sub(r"^\s*\d+(?:\.\d+)*\s+", "", text or "").strip().lower()
    label = re.sub(r"\s+", " ", label)
    if label.strip("()") in COMMON_SUBHEADING_LABELS:
        return True
    return label in COMMON_SUBHEADING_LABELS


def is_parent_child_heading(parent_text: str, child_text: str) -> bool:
    parent = section_anchor(parent_text)
    child = section_anchor(child_text)
    return bool(parent and child and len(child) == len(parent) + 1 and child[: len(parent)] == parent)


def is_split_number_heading_pair(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_text = left.get("raw_text", "").strip()
    right_text = right.get("raw_text", "").strip()
    if not (SECTION_RE.match(left_text) or SECTION_RE.match(right_text)):
        return False
    if section_anchor(left_text) and section_anchor(right_text):
        return False
    return left.get("page") == right.get("page") and same_baseline(left, right)


def is_heading_number_pair(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_section = bool(section_anchor(left.get("raw_text", "")))
    right_section = bool(section_anchor(right.get("raw_text", "")))
    return left.get("page") == right.get("page") and left_section != right_section


def is_appendix_heading_pair(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_text = (left.get("raw_text") or "").strip().lower()
    right_text = (right.get("raw_text") or "").strip().lower()
    return left.get("page") == right.get("page") and (
        left_text.startswith(("appendix", "appendice"))
        or right_text.startswith(("appendix", "appendice"))
        or re.fullmatch(r"[a-z]\.\d+(?:\.\d+)*", left_text or "") is not None
        or re.fullmatch(r"[a-z]\.\d+(?:\.\d+)*", right_text or "") is not None
    )


def is_terms_heading_pair(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_text = re.sub(r"<[^>]+>", " ", left.get("raw_text") or "").lower()
    right_text = re.sub(r"<[^>]+>", " ", right.get("raw_text") or "").lower()
    return "termini" in left_text and "definizioni" in left_text and "termini" in right_text and "definizioni" in right_text


def is_table_title_pair(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_text = (left.get("raw_text") or "").strip().lower()
    right_text = (right.get("raw_text") or "").strip().lower()
    return left.get("page") == right.get("page") and ("prospetto" in left_text or "prospetto" in right_text or "table " in left_text or "table " in right_text)


def is_source_pdf_recovered_unit(unit: dict[str, Any]) -> bool:
    return bool(unit.get("recovery")) or str(unit.get("unit_id", "")).startswith("source-pdf-recovery:")


def is_code_or_schema_line(text: str) -> bool:
    stripped = (text or "").strip()
    if stripped in {"{", "}", "[", "]"}:
        return True
    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*:", stripped):
        return True
    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*:\s*[-A-Za-z0-9_ ,]+[,]?$", stripped):
        return True
    if "::=" in stripped:
        return True
    return False


def is_schema_column_pair(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_text = left.get("raw_text", "").strip()
    right_text = right.get("raw_text", "").strip()
    return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*:$", left_text) and re.search(r"\b(?:array|unsigned|long|string|octet|structure)\b", right_text, re.I))


def is_appendix_anchor_pair(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_text = left.get("raw_text", "").strip()
    right_text = right.get("raw_text", "").strip()
    return bool(re.fullmatch(r"[A-Z]\.\d+(?:\.\d+)*", left_text) and is_common_subheading(right_text))


def is_protocol_expression(text: str) -> bool:
    stripped = text or ""
    return "||" in stripped and bool(re.search(r"\b(?:preamble|payload|access address|crc|idvar|obj\d|tr_cf|cf_\d|tot|lenght|length|value)\b", stripped, re.I))


def is_safe_angle_placeholder(text: str) -> bool:
    stripped = text or ""
    placeholders = re.findall(r"<<\s*[A-Za-z][A-Za-z0-9_]{0,12}\s*>>", stripped)
    without_placeholders = re.sub(r"<<\s*[A-Za-z][A-Za-z0-9_]{0,12}\s*>>", "", stripped)
    return bool(placeholders) and "<<" not in without_placeholders and ">>" not in without_placeholders


def is_footnote_start(text: str) -> bool:
    return bool(FOOTNOTE_START_RE.match(text or ""))


def is_standalone_footnote(unit: dict[str, Any], text: str, bbox: list[Any]) -> bool:
    if not is_footnote_start(text):
        return False
    page_height = float(unit.get("page_height") or 842)
    near_bottom = bbox[1] >= page_height * 0.85
    dtype = unit.get("dtype", "")
    unit_id = unit.get("unit_id", "")
    footnote_like = dtype in {"page_footnote", "footnote", "aside_text"} or "discarded_blocks" in unit_id
    geometric_footnote = near_bottom and bbox[0] >= 90 and len((text or "").split()) <= 90
    return near_bottom and (footnote_like or geometric_footnote)


def has_footnote_contamination(unit: dict[str, Any], text: str, bbox: list[Any]) -> bool:
    if is_standalone_footnote(unit, text, bbox):
        return False
    if is_footnote_start(text) and bbox[1] >= 730:
        return True
    return bool(re.search(r"[.!?]\s+\d+\)\s+\S+", text or ""))


def detect_review_items(blocks: list[dict[str, Any]], foreign_terms: set[str] | None = None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    foreign_terms = foreign_terms or load_foreign_terms()
    sections: list[tuple[tuple[int, ...], str]] = []
    tables: list[tuple[int, str]] = []
    figures: list[tuple[int, str]] = []
    title_run: list[dict[str, Any]] = []
    short_text_run: list[str] = []
    seen_defined_terms: set[str] = set()
    review_blocks = [unit for unit in blocks if not is_safe_discard_header_footer(unit)]
    foreign_dominant = is_foreign_dominant_document(review_blocks, foreign_terms)
    for unit in sorted(review_blocks, key=reading_order):
        text = unit.get("raw_text", "")
        audit = unit.get("audit_text") or normalize_audit(text)
        refs = [unit["unit_id"]]
        bbox = unit.get("bbox") or [0, 0, 0, 0]

        anchor = section_anchor(text)
        if anchor:
            sections.append((anchor, unit["unit_id"]))
            rest = re.sub(r"^\s*\d+(?:\.\d+)*\s+", "", text).strip()
            if unit.get("dtype") in {"title", "heading"} and re.search(r"\b(?:shall|must|should|is|are|the following)\b", rest, re.I):
                items.append(review("A3", refs, "heading_may_include_body_text", sample=text))
            if unit.get("dtype") in {"title", "heading"} and text.rstrip().endswith("-"):
                items.append(review("A4", refs, "heading_ends_with_hyphen_possible_truncation", sample=text))
        for embedded_anchor, embedded_ref in embedded_section_anchors(unit):
            sections.append((embedded_anchor, embedded_ref))

        if unit.get("dtype") in {"title", "heading"}:
            title_run.append(unit)
            if len(title_run) >= 2:
                prev_title, cur_title = title_run[-2], title_run[-1]
                if (
                    not is_parent_child_heading(prev_title.get("raw_text", ""), cur_title.get("raw_text", ""))
                    and not is_split_number_heading_pair(prev_title, cur_title)
                    and not is_heading_number_pair(prev_title, cur_title)
                    and not is_appendix_heading_pair(prev_title, cur_title)
                    and not is_terms_heading_pair(prev_title, cur_title)
                    and not is_table_title_pair(prev_title, cur_title)
                    and not is_source_pdf_recovered_unit(prev_title)
                    and not is_source_pdf_recovered_unit(cur_title)
                    and not is_code_or_schema_line(prev_title.get("raw_text", ""))
                    and not is_code_or_schema_line(cur_title.get("raw_text", ""))
                    and not is_common_subheading(cur_title.get("raw_text", ""))
                ):
                    items.append(review("A5", [prev_title["unit_id"], cur_title["unit_id"]], "consecutive_headings_without_body_between"))
        elif text.strip():
            title_run = []

        if unit.get("dtype") in {"text", "para", "paragraph", "para_blocks"} and len(text.split()) <= 2 and not is_sentence_terminal(text) and not is_code_or_schema_line(text):
            short_text_run.append(unit["unit_id"])
            if len(short_text_run) >= 3:
                items.append(review("B2", short_text_run[-3:], "over_fragmented_short_paragraph_blocks"))
        elif text.strip():
            short_text_run = []

        if not foreign_dominant and is_mixed_foreign_contamination(audit, foreign_terms):
            items.append(review("C3", refs, "possible_foreign_language_contamination", sample=text))

        if has_footnote_contamination(unit, text, bbox):
            items.append(review("C1", refs, "possible_footnote_contamination", sample=text))

        if HEADER_FOOTER_RE.search(text) and is_header_footer_candidate(unit, text, bbox) and not is_safe_discard_header_footer(unit):
            items.append(review("C2", refs, "possible_header_footer_contamination", sample=text))

        if text.count("|") >= 3 and unit.get("dtype") not in {"table", "table_body", "source_pdf_recovery"} and not is_protocol_expression(text):
            items.append(review("D3", refs, "table_like_text_in_paragraph_block", sample=text))

        if unit.get("dtype") == "list" and not re.match(r"^\s*(?:[-*•\u2212]|\d+[.)]|[a-zA-Z][.)])\s+", text):
            items.append(review("D2", refs, "list_block_missing_visible_bullet", sample=text))

        if unit.get("dtype") == "caption" and re.search(r"\b(?:Table|Figure)\s+\d+\b", text, re.I) and bbox[1] >= 700:
            items.append(review("D4", refs, "caption_near_page_edge_possible_displacement", sample=text))

        for number, unit_text in re.findall(r"\b(\d+(?:[.,]\d+)?)\s+([A-Za-zµ³/%]+)\b", text):
            if is_suspicious_unit(number, unit_text):
                items.append(review("E2", refs, "unknown_or_suspicious_unit", value=f"{number} {unit_text}", sample=text))
                break

        if re.search(r"(?:\?\?\?|<<|>>|�|□)", text) and not is_safe_angle_placeholder(text) and unit.get("dtype") not in {"table", "table_body"}:
            items.append(review("E3", refs, "possible_formula_or_encoding_corruption", sample=text))

        table_no = numbered_anchor(text, "Table")
        if table_no is not None and is_numbered_figure_table_source(unit, "Table", text):
            tables.append((table_no, unit["unit_id"]))
        figure_no = numbered_anchor(text, "Figure")
        if figure_no is not None and is_numbered_figure_table_source(unit, "Figure", text):
            figures.append((figure_no, unit["unit_id"]))

        definition = TERM_RE.search(text)
        if definition:
            seen_defined_terms.add(definition.group(1).strip().lower())
        for term in ("gateway", "meter", "endpoint", "application software"):
            term_pattern = r"\b" + re.escape(term) + r"\b"
            if (
                re.search(term_pattern, audit)
                and term not in seen_defined_terms
                and re.search(r"\bdefined\b", audit)
                and "associated with a meter" not in audit
                and "defined in compliance" not in audit
                and "defined in appendix" not in audit
                and "defined in annex" not in audit
                and "defined by" not in audit
                and unit.get("dtype") not in {"page_footnote", "footnote", "aside_text"}
                and "discarded_blocks" not in unit.get("unit_id", "")
            ):
                items.append(review("F3", refs, "term_used_before_clear_definition_order", term=term, sample=text))
                seen_defined_terms.add(term)

    ordered = sorted(review_blocks, key=reading_order)
    for current, nxt in zip(ordered, ordered[1:]):
        if current.get("page") is None or nxt.get("page") is None:
            continue
        if int(nxt.get("page", 0)) == int(current.get("page", 0)) + 1:
            cb = current.get("bbox") or [0, 0, 0, 0]
            nb = nxt.get("bbox") or [0, 0, 0, 0]
            if (
                cb[1] >= 730
                and nb[1] <= 80
                and not is_sentence_terminal(current.get("raw_text", ""))
                and starts_like_continuation(nxt.get("raw_text", ""))
                and not is_code_or_schema_line(current.get("raw_text", ""))
                and not is_code_or_schema_line(nxt.get("raw_text", ""))
            ):
                items.append(review("B3", [current["unit_id"], nxt["unit_id"]], "possible_cross_page_paragraph_continuation"))

    by_page: dict[int, list[dict[str, Any]]] = {}
    for unit in review_blocks:
        by_page.setdefault(int(unit.get("page", 0)), []).append(unit)
    for page_units in by_page.values():
        sorted_page = sorted(page_units, key=reading_order)
        for left, right in zip(sorted_page, sorted_page[1:]):
            lb = left.get("bbox") or [0, 0, 0, 0]
            rb = right.get("bbox") or [0, 0, 0, 0]
            if (
                rb[0] - lb[2] > 80
                and abs(cy(left) - cy(right)) <= 4
                and left.get("dtype") == right.get("dtype") == "text"
                and not is_schema_column_pair(left, right)
                and not is_appendix_anchor_pair(left, right)
            ):
                items.append(review("C4", [left["unit_id"], right["unit_id"]], "possible_cross_column_semantic_pollution"))

    for prev, cur in zip(sections, sections[1:]):
        prev_num, prev_ref = prev
        cur_num, cur_ref = cur
        if len(prev_num) == len(cur_num) and cur_num[:-1] == prev_num[:-1] and cur_num[-1] > prev_num[-1] + 1:
            items.append(review("A2", [prev_ref, cur_ref], "section_number_jump", previous=".".join(map(str, prev_num)), current=".".join(map(str, cur_num))))
            items.append(review("F1", [prev_ref, cur_ref], "section_sequence_gap", previous=".".join(map(str, prev_num)), current=".".join(map(str, cur_num))))

    for label, seq in (("Table", tables), ("Figure", figures)):
        for prev, cur in zip(seq, seq[1:]):
            if cur[0] > prev[0] + 1:
                items.append(review("F2", [prev[1], cur[1]], f"{label.lower()}_number_sequence_gap", previous=prev[0], current=cur[0]))

    return items


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
        page_width = float(number.get("page_width") or 595)
        titles = [
            u
            for u in same_row
            if is_toc_title(u)
            or ((u.get("bbox") or [0])[0] > page_width * 0.16 and (u.get("bbox") or [0])[0] < page_width * 0.75 and not is_toc_page(u))
        ]
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
        if is_safe_discard_header_footer(unit):
            outputs.append(output_block(f"out:{unit['unit_id']}:discard", raw, [unit["unit_id"]], "C2_discard_header_footer", "discarded", unit.get("page"), 0.95))
            findings.append(finding("C2", [unit["unit_id"]], raw))
            used.add(unit["unit_id"])
            continue
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
    review_items = detect_review_items(blocks)
    return outputs, findings, review_items


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply deterministic PDF layout repairs.")
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
