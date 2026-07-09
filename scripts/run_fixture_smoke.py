#!/usr/bin/env python3
"""Run fixture smoke tests for pdf-layout-repair."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "fixtures"


def run(*args: str) -> None:
    subprocess.run([sys.executable, *args], check=True)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_script_module(name: str, script: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / script)
    if not spec or not spec.loader:
        raise AssertionError(f"Cannot load script module: {script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_chain(tmp: Path, units: list[dict[str, Any]], rendered_text: str = "") -> dict[str, Any]:
    inventory = tmp / "source_inventory.json"
    repaired = tmp / "repaired_blocks.json"
    manifest = tmp / "repair_manifest.json"
    completeness = tmp / "completeness_report.json"
    rendered = tmp / "rendered.txt"
    post_render = tmp / "post_render_audit.json"
    report = tmp / "repair_report.md"

    write_json(inventory, {"schema_version": "0.1", "source": "fixture", "units": units})
    run(str(SCRIPTS / "apply_repairs.py"), str(inventory), "-o", str(repaired))
    run(str(SCRIPTS / "build_manifest.py"), str(inventory), str(repaired), "-o", str(manifest))
    run(str(SCRIPTS / "completeness_audit.py"), str(inventory), str(manifest), "-o", str(completeness))
    rendered.write_text(rendered_text, encoding="utf-8")
    run(str(SCRIPTS / "post_render_audit.py"), str(rendered), str(completeness), "-o", str(post_render))
    run(str(SCRIPTS / "render_report.py"), str(completeness), str(post_render), "-o", str(report))

    return {
        "repaired": read_json(repaired),
        "manifest": read_json(manifest),
        "completeness": read_json(completeness),
        "post_render": read_json(post_render),
        "report": report.read_text(encoding="utf-8-sig"),
    }


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_a1_positive(tmp: Path) -> None:
    fixture = read_json(FIXTURES / "isolated-section-number.json")
    result = run_chain(tmp / "a1-positive", fixture["positive"]["units"], fixture["positive"]["expected"])
    blocks = result["repaired"]["output_blocks"]
    assert_true(any(b.get("raw_text") == "3.3 APP" for b in blocks), "A1 positive did not merge section number and title")
    assert_true(any(f.get("rule_id") == "A1" for f in result["completeness"]["auto_fixed"]), "A1 finding missing")


def test_a1_negative(tmp: Path) -> None:
    fixture = read_json(FIXTURES / "isolated-section-number.json")
    result = run_chain(tmp / "a1-negative", fixture["negative"]["units"], "3.3\nAPP")
    blocks = result["repaired"]["output_blocks"]
    assert_true(not any(b.get("raw_text") == "3.3 APP" for b in blocks), "A1 negative merged different baselines")


def test_missing_anchor(tmp: Path) -> None:
    fixture = read_json(FIXTURES / "missing-anchor.json")
    inventory = tmp / "missing-anchor" / "source_inventory.json"
    repaired = tmp / "missing-anchor" / "repaired_blocks.json"
    manifest = tmp / "missing-anchor" / "repair_manifest.json"
    completeness = tmp / "missing-anchor" / "completeness_report.json"
    inventory.parent.mkdir(parents=True, exist_ok=True)

    write_json(
        inventory,
        {
            "schema_version": "0.1",
            "source": "fixture",
            "units": [
                {
                    "unit_id": "fixture:p0:block0",
                    "granularity": "block",
                    "page": 0,
                    "dtype": "text",
                    "raw_text": fixture["source_audit_text"],
                    "audit_text": fixture["source_audit_text"].lower(),
                    "bbox": [0, 0, 100, 20],
                }
            ],
        },
    )
    write_json(
        repaired,
        {
            "schema_version": "0.1",
            "source_inventory": str(inventory),
            "output_blocks": [
                {
                    "output_id": "out:fixture:p0:block0",
                    "raw_text": fixture["output_audit_text"],
                    "audit_text": fixture["output_audit_text"].lower(),
                    "source_refs": ["fixture:p0:block0"],
                    "operation": "emit",
                    "confidence": 1.0,
                    "disposition": "emitted",
                    "page": 0,
                }
            ],
            "findings": [],
            "not_implemented": [],
        },
    )
    run(str(SCRIPTS / "build_manifest.py"), str(inventory), str(repaired), "-o", str(manifest))
    run(str(SCRIPTS / "completeness_audit.py"), str(inventory), str(manifest), "-o", str(completeness))
    report = read_json(completeness)
    missing = {a for item in report["content_loss"] for a in item.get("anchors", [])}
    assert_true({"4.2.1", "table 1"}.issubset(missing), "G3 did not report missing required anchors")


def test_general_repairs(tmp: Path) -> None:
    fixture = read_json(FIXTURES / "general-repair.json")
    expected = fixture["expected"]
    result = run_chain(tmp / "general-repair", fixture["units"], "\n".join(expected.values()))
    texts = [b.get("raw_text") for b in result["repaired"]["output_blocks"]]
    operations = {b.get("operation") for b in result["repaired"]["output_blocks"]}
    rule_ids = {f.get("rule_id") for f in result["completeness"]["auto_fixed"]}
    assert_true(expected["toc_text"] in texts, "TOC three-column row was not rebuilt")
    assert_true(expected["joined_paragraph"] in texts, "Paragraph continuation was not joined")
    assert_true(expected["bullet_text"] in texts, "Bullet was not normalized")
    assert_true(expected["symbol_text"] in texts, "Symbol corruption was not repaired")
    assert_true({"D0", "B1", "D1", "E1"}.issubset(rule_ids), "Expected rule findings are missing")
    assert_true("TOC_three_column_repair" in operations, "TOC operation missing")


def test_general_repair_negatives(tmp: Path) -> None:
    fixture = read_json(FIXTURES / "general-repair.json")
    negative = fixture["negative"]

    b1_result = run_chain(tmp / "negative-b1", negative["b1"]["units"], "\n".join(u["raw_text"] for u in negative["b1"]["units"]))
    b1_texts = [b.get("raw_text") for b in b1_result["repaired"]["output_blocks"]]
    assert_true(negative["b1"]["forbidden_text"] not in b1_texts, "B1 negative incorrectly joined independent paragraphs")

    d1_result = run_chain(tmp / "negative-d1", negative["d1"]["units"], negative["d1"]["expected_text"])
    d1_texts = [b.get("raw_text") for b in d1_result["repaired"]["output_blocks"]]
    assert_true(negative["d1"]["expected_text"] in d1_texts, "D1 negative rewrote semantic hyphen text")
    d1_rules = {f.get("rule_id") for f in d1_result["completeness"]["auto_fixed"]}
    assert_true("D1" not in d1_rules, "D1 negative produced an auto_fix finding")

    e1_result = run_chain(tmp / "negative-e1", negative["e1"]["units"], negative["e1"]["expected_text"])
    e1_texts = [b.get("raw_text") for b in e1_result["repaired"]["output_blocks"]]
    assert_true(negative["e1"]["expected_text"] in e1_texts, "E1 negative replaced a legal glyph")
    e1_rules = {f.get("rule_id") for f in e1_result["completeness"]["auto_fixed"]}
    assert_true("E1" not in e1_rules, "E1 negative produced an auto_fix finding")


def test_g2_review_band(tmp: Path) -> None:
    inventory = tmp / "g2-review-band" / "source_inventory.json"
    repaired = tmp / "g2-review-band" / "repaired_blocks.json"
    manifest = tmp / "g2-review-band" / "repair_manifest.json"
    completeness = tmp / "g2-review-band" / "completeness_report.json"
    inventory.parent.mkdir(parents=True, exist_ok=True)
    source_text = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
    output_text = "alpha beta gamma delta epsilon zeta eta theta"
    write_json(
        inventory,
        {
            "schema_version": "0.1",
            "source": "fixture",
            "units": [
                {
                    "unit_id": "g2:p0:block0",
                    "granularity": "block",
                    "page": 0,
                    "dtype": "text",
                    "raw_text": source_text,
                    "audit_text": source_text,
                    "bbox": [0, 0, 100, 20],
                }
            ],
        },
    )
    write_json(
        repaired,
        {
            "schema_version": "0.1",
            "source_inventory": str(inventory),
            "output_blocks": [
                {
                    "output_id": "out:g2:p0:block0",
                    "raw_text": output_text,
                    "audit_text": output_text,
                    "source_refs": ["g2:p0:block0"],
                    "operation": "emit",
                    "confidence": 1.0,
                    "disposition": "emitted",
                    "page": 0,
                }
            ],
            "findings": [],
            "not_implemented": [],
        },
    )
    run(str(SCRIPTS / "build_manifest.py"), str(inventory), str(repaired), "-o", str(manifest))
    run(str(SCRIPTS / "completeness_audit.py"), str(inventory), str(manifest), "-o", str(completeness))
    report = read_json(completeness)
    assert_true(not any(item.get("rule_id") == "G2" for item in report["content_loss"]), "G2 review band was escalated to content_loss")
    assert_true(any(item.get("rule_id") == "G2" for item in report["needs_review"]), "G2 review band did not produce needs_review")


def test_g2_full_char_coverage_with_anchors_is_suppressed(tmp: Path) -> None:
    inventory = tmp / "g2-char-complete" / "source_inventory.json"
    repaired = tmp / "g2-char-complete" / "repaired_blocks.json"
    manifest = tmp / "g2-char-complete" / "repair_manifest.json"
    completeness = tmp / "g2-char-complete" / "completeness_report.json"
    inventory.parent.mkdir(parents=True, exist_ok=True)
    source_text = "4.2 Remote meter commissioning requires secure activation and operator confirmation."
    output_text = "4.2 Remote-meter commissioning requires secure activation and operator confirmation."
    write_json(
        inventory,
        {
            "schema_version": "0.1",
            "source": "fixture",
            "units": [
                {
                    "unit_id": "g2:p0:block0",
                    "granularity": "block",
                    "page": 0,
                    "dtype": "text",
                    "raw_text": source_text,
                    "audit_text": source_text.lower(),
                    "bbox": [0, 0, 100, 20],
                }
            ],
        },
    )
    write_json(
        repaired,
        {
            "schema_version": "0.1",
            "source_inventory": str(inventory),
            "output_blocks": [
                {
                    "output_id": "out:g2:p0:block0",
                    "raw_text": output_text,
                    "audit_text": output_text.lower(),
                    "source_refs": ["g2:p0:block0"],
                    "operation": "emit",
                    "confidence": 1.0,
                    "disposition": "emitted",
                    "page": 0,
                }
            ],
            "findings": [],
            "not_implemented": [],
        },
    )
    run(str(SCRIPTS / "build_manifest.py"), str(inventory), str(repaired), "-o", str(manifest))
    run(str(SCRIPTS / "completeness_audit.py"), str(inventory), str(manifest), "-o", str(completeness), "--text-threshold", "1.01")
    report = read_json(completeness)
    assert_true(not any(item.get("rule_id") == "G2" for item in report["needs_review"]), f"G2 should suppress char-complete pages with anchors intact: {report['needs_review']}")
    suppressed = report["audits"].get("G2_text_amount", {}).get("suppressed_review", [])
    assert_true(suppressed and suppressed[0].get("page") == 0, f"G2 suppression was not audited: {suppressed}")


def test_g5_local_semantic_sampling_passes_when_samples_are_covered(tmp: Path) -> None:
    inventory = tmp / "g5-local-pass" / "source_inventory.json"
    repaired = tmp / "g5-local-pass" / "repaired_blocks.json"
    manifest = tmp / "g5-local-pass" / "repair_manifest.json"
    completeness = tmp / "g5-local-pass" / "completeness_report.json"
    inventory.parent.mkdir(parents=True, exist_ok=True)
    source_text = "4.2 Remote meter commissioning requires secure activation and operator confirmation before service starts."
    write_json(
        inventory,
        {
            "schema_version": "0.1",
            "source": "fixture",
            "units": [
                {
                    "unit_id": "g5:p0:block0",
                    "granularity": "block",
                    "page": 0,
                    "dtype": "text",
                    "raw_text": source_text,
                    "audit_text": source_text.lower(),
                    "bbox": [0, 0, 100, 20],
                }
            ],
        },
    )
    write_json(
        repaired,
        {
            "schema_version": "0.1",
            "source_inventory": str(inventory),
            "output_blocks": [
                {
                    "output_id": "out:g5:p0:block0",
                    "raw_text": source_text,
                    "audit_text": source_text.lower(),
                    "source_refs": ["g5:p0:block0"],
                    "operation": "emit",
                    "confidence": 1.0,
                    "disposition": "emitted",
                    "page": 0,
                }
            ],
            "findings": [],
            "not_implemented": [],
        },
    )
    run(str(SCRIPTS / "build_manifest.py"), str(inventory), str(repaired), "-o", str(manifest))
    run(str(SCRIPTS / "completeness_audit.py"), str(inventory), str(manifest), "-o", str(completeness))
    report = read_json(completeness)
    g5 = report["audits"].get("G5_ai_semantic_sampling", {})
    assert_true(g5.get("status") == "pass", f"G5 local sampling should pass: {g5}")
    assert_true(not any(item.get("rule_id") == "G5" for item in report["needs_review"]), f"G5 pass should not require review: {report['needs_review']}")


def test_canonical_tokens_preserve_angle_expressions() -> None:
    module = load_script_module("completeness_audit_angle_tokens", "completeness_audit.py")
    text = 'the interval is always included (0<x<16); - cxh= after every "x" cubic meters and x>1 minutes later'
    tokens = module.canonical_tokens(text)
    for expected in ["cxh", "cubic", "meters", "minutes", "later"]:
        assert_true(expected in tokens, f"Angle-expression token was stripped as HTML: {expected} not in {tokens}")


def test_review_decisions_resolve_matched_needs_review(tmp: Path) -> None:
    inventory = tmp / "review-decisions" / "source_inventory.json"
    manifest = tmp / "review-decisions" / "repair_manifest.json"
    decisions = tmp / "review-decisions" / "review_decisions.json"
    completeness = tmp / "review-decisions" / "completeness_report.json"
    inventory.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        inventory,
        {
            "schema_version": "0.1",
            "source": "fixture",
            "units": [
                {
                    "unit_id": "source-pdf-recovery:p0:4-2",
                    "granularity": "block",
                    "page": 0,
                    "dtype": "title",
                    "raw_text": "4.2 Recovered section",
                    "audit_text": "4.2 recovered section",
                    "bbox": [0, 0, 100, 20],
                    "recovery": {"rule_id": "G3R", "anchor": "4.2", "kind": "section", "requires_review": True},
                },
                {
                    "unit_id": "mineru:p0:block1",
                    "granularity": "block",
                    "page": 0,
                    "dtype": "table",
                    "raw_text": "Table row contains expected term modulo in source.",
                    "audit_text": "table row contains expected term modulo in source.",
                    "bbox": [0, 30, 100, 60],
                },
            ],
        },
    )
    write_json(
        manifest,
        {
            "schema_version": "0.1",
            "source_inventory": str(inventory),
            "document_status": "draft",
            "output_blocks": [
                {
                    "output_id": "out:source-pdf-recovery:p0:4-2",
                    "raw_text": "4.2 Recovered section",
                    "audit_text": "4.2 recovered section",
                    "source_refs": ["source-pdf-recovery:p0:4-2"],
                    "operation": "emit",
                    "confidence": 1.0,
                    "disposition": "emitted",
                    "page": 0,
                },
                {
                    "output_id": "out:mineru:p0:block1",
                    "raw_text": "Table row contains expected term modulo in source.",
                    "audit_text": "table row contains expected term modulo in source.",
                    "source_refs": ["mineru:p0:block1"],
                    "operation": "emit",
                    "confidence": 1.0,
                    "disposition": "emitted",
                    "page": 0,
                },
            ],
            "source_dispositions": {
                "source-pdf-recovery:p0:4-2": "emitted",
                "mineru:p0:block1": "emitted",
            },
            "findings": [],
            "needs_review": [
                {"rule_id": "C3", "reason": "possible_foreign_language_contamination", "source_refs": ["mineru:p0:block1"]}
            ],
            "not_implemented": [],
        },
    )
    write_json(
        decisions,
        {
            "schema_version": "0.1",
            "reviewer": "fixture-reviewer",
            "decisions": [
                {
                    "action": "accept_review",
                    "rule_id": "G3R",
                    "unit_ids": ["source-pdf-recovery:p0:4-2"],
                    "reason": "Recovered source PDF section was visually checked against the source page.",
                },
                {
                    "action": "accept_review",
                    "rule_id": "C3",
                    "source_refs": ["mineru:p0:block1"],
                    "reason": "The foreign term is present in the source table and is not extraction contamination.",
                },
            ],
        },
    )
    run(str(SCRIPTS / "completeness_audit.py"), str(inventory), str(manifest), "--review-decisions", str(decisions), "-o", str(completeness))
    report = read_json(completeness)
    assert_true(report["document_status"] == "final", f"Matched review decisions should allow final: {report}")
    assert_true(not report["needs_review"], f"Matched decisions did not resolve review items: {report['needs_review']}")
    applied = report["audits"].get("review_decisions", {}).get("applied", [])
    assert_true(len(applied) == 2, f"Applied review decisions were not audited: {applied}")


def test_post_render_uses_output_anchors_only(tmp: Path) -> None:
    report_path = tmp / "post-render-output-anchors" / "completeness_report.json"
    rendered = tmp / "post-render-output-anchors" / "rendered.txt"
    post = tmp / "post-render-output-anchors" / "post_render_audit.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        report_path,
        {
            "schema_version": "0.2",
            "document_status": "review",
            "audits": {
                "G3_anchor_audit": {
                    "required_source_anchors": ["3.3", "4.2"],
                    "required_output_anchors": ["4.2"],
                    "missing_required": ["3.3"],
                }
            },
            "content_loss": [{"rule_id": "G3", "anchors": ["3.3"]}],
            "needs_review": [],
            "auto_fixed": [],
        },
    )
    rendered.write_text("4.2 Services", encoding="utf-8")
    run(str(SCRIPTS / "post_render_audit.py"), str(rendered), str(report_path), "-o", str(post))
    result = read_json(post)
    assert_true(not any("3.3" in item.get("anchors", []) for item in result["post_render_loss"]), "Post-render repeated an upstream missing source anchor")


def test_source_pdf_audit_required_anchor_gate(tmp: Path) -> None:
    inventory = tmp / "source-pdf-gate" / "source_inventory.json"
    repaired = tmp / "source-pdf-gate" / "repaired_blocks.json"
    manifest = tmp / "source-pdf-gate" / "repair_manifest.json"
    source_audit = tmp / "source-pdf-gate" / "source_pdf_audit.json"
    completeness = tmp / "source-pdf-gate" / "completeness_report.json"
    inventory.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        inventory,
        {
            "schema_version": "0.1",
            "source": "fixture",
            "units": [
                {
                    "unit_id": "mineru:p0:block0",
                    "granularity": "block",
                    "page": 0,
                    "dtype": "text",
                    "raw_text": "4.1 Present section",
                    "audit_text": "4.1 present section",
                    "bbox": [0, 0, 100, 20],
                }
            ],
        },
    )
    write_json(
        repaired,
        {
            "schema_version": "0.1",
            "source_inventory": str(inventory),
            "output_blocks": [
                {
                    "output_id": "out:mineru:p0:block0",
                    "raw_text": "4.1 Present section",
                    "audit_text": "4.1 present section",
                    "source_refs": ["mineru:p0:block0"],
                    "operation": "emit",
                    "confidence": 1.0,
                    "disposition": "emitted",
                    "page": 0,
                }
            ],
            "findings": [],
            "not_implemented": [],
        },
    )
    write_json(
        source_audit,
        {
            "schema_version": "0.1",
            "anchors": ["4.1", "4.2"],
            "anchor_locations": {
                "4.2": [{"page": 0, "snippet": "4.2 Missing structural section title"}],
            },
        },
    )
    run(str(SCRIPTS / "build_manifest.py"), str(inventory), str(repaired), "-o", str(manifest))
    run(str(SCRIPTS / "completeness_audit.py"), str(inventory), str(manifest), "--source-pdf-audit", str(source_audit), "-o", str(completeness))
    report = read_json(completeness)
    assert_true(any(item.get("rule_id") == "G3P" and "4.2" in item.get("anchors", []) for item in report["content_loss"]), "Independent source PDF anchor loss was not gated")


def test_source_pdf_anchor_whitespace_normalization(tmp: Path) -> None:
    inventory = tmp / "source-pdf-anchor-normalization" / "source_inventory.json"
    repaired = tmp / "source-pdf-anchor-normalization" / "repaired_blocks.json"
    manifest = tmp / "source-pdf-anchor-normalization" / "repair_manifest.json"
    source_audit = tmp / "source-pdf-anchor-normalization" / "source_pdf_audit.json"
    completeness = tmp / "source-pdf-anchor-normalization" / "completeness_report.json"
    inventory.parent.mkdir(parents=True, exist_ok=True)
    source_text = "Table 9\nFigure 1\nAppendix A\n4.2 Service"
    output_text = "Table 9\nFigure 1\nAppendix A\n4.2 Service"
    write_json(
        inventory,
        {
            "schema_version": "0.1",
            "source": "fixture",
            "units": [
                {
                    "unit_id": "mineru:p0:block0",
                    "granularity": "block",
                    "page": 0,
                    "dtype": "text",
                    "raw_text": source_text,
                    "audit_text": source_text.lower(),
                    "bbox": [0, 0, 100, 20],
                }
            ],
        },
    )
    write_json(
        repaired,
        {
            "schema_version": "0.1",
            "source_inventory": str(inventory),
            "output_blocks": [
                {
                    "output_id": "out:mineru:p0:block0",
                    "raw_text": output_text,
                    "audit_text": output_text.lower(),
                    "source_refs": ["mineru:p0:block0"],
                    "operation": "emit",
                    "confidence": 1.0,
                    "disposition": "emitted",
                    "page": 0,
                }
            ],
            "findings": [],
            "not_implemented": [],
        },
    )
    write_json(source_audit, {"schema_version": "0.1", "anchors": ["Table\n9", "Figure  1", "Appendix  A", "4.2"]})
    run(str(SCRIPTS / "build_manifest.py"), str(inventory), str(repaired), "-o", str(manifest))
    run(str(SCRIPTS / "completeness_audit.py"), str(inventory), str(manifest), "--source-pdf-audit", str(source_audit), "-o", str(completeness))
    report = read_json(completeness)
    missing = {a for item in report["content_loss"] if item.get("rule_id") == "G3P" for a in item.get("anchors", [])}
    assert_true(not missing, f"G3P reported whitespace-only anchor mismatches: {sorted(missing)}")


def test_mineru_v4_zip_url_extraction() -> None:
    module = load_script_module("call_mineru_api", "call_mineru_api.py")
    payload = {
        "code": 0,
        "data": {
            "extract_result": [
                {"state": "done", "file_name": "a.pdf", "full_zip_url": "https://example.test/a.zip"},
                {"state": "failed", "file_name": "b.pdf", "full_zip_url": ""},
            ]
        },
    }
    urls = module.extract_zip_urls(payload)
    assert_true(urls == ["https://example.test/a.zip"], f"Unexpected MinerU zip URLs: {urls}")


def test_source_pdf_audit_anchor_locations(tmp: Path) -> None:
    try:
        import fitz
    except Exception:
        print("source PDF anchor location fixture skipped: PyMuPDF unavailable")
        return
    pdf = tmp / "source-pdf-anchor-locations" / "source.pdf"
    audit = tmp / "source-pdf-anchor-locations" / "source_pdf_audit.json"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "5.4.8 Supply Management\nTable 9 - Data structure")
    doc.save(pdf)
    doc.close()
    run(str(SCRIPTS / "source_pdf_audit.py"), str(pdf), "-o", str(audit))
    result = read_json(audit)
    locations = result.get("anchor_locations", {})
    assert_true("5.4.8" in locations, "Source PDF audit did not localize section anchor")
    assert_true(locations["5.4.8"][0]["page"] == 0, "Source PDF audit reported wrong anchor page")
    assert_true("supply management" in locations["5.4.8"][0]["snippet"].lower(), "Source PDF audit did not include anchor snippet")


def test_source_pdf_anchor_recovery_downgrades_loss_to_review(tmp: Path) -> None:
    inventory = tmp / "source-pdf-anchor-recovery" / "source_inventory.json"
    recovered = tmp / "source-pdf-anchor-recovery" / "source_inventory_recovered.json"
    repaired = tmp / "source-pdf-anchor-recovery" / "repaired_blocks.json"
    manifest = tmp / "source-pdf-anchor-recovery" / "repair_manifest.json"
    source_audit = tmp / "source-pdf-anchor-recovery" / "source_pdf_audit.json"
    completeness = tmp / "source-pdf-anchor-recovery" / "completeness_report.json"
    inventory.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        inventory,
        {
            "schema_version": "0.1",
            "source": "fixture",
            "units": [
                {
                    "unit_id": "mineru:p0:block0",
                    "granularity": "block",
                    "page": 0,
                    "dtype": "text",
                    "raw_text": "4.1 Present section",
                    "audit_text": "4.1 present section",
                    "bbox": [0, 0, 100, 20],
                }
            ],
        },
    )
    write_json(
        source_audit,
        {
            "schema_version": "0.1",
            "anchors": ["4.1", "4.2"],
            "anchor_locations": {
                "4.2": [{"page": 0, "snippet": "4.2 Recovered source section text"}],
            },
        },
    )
    run(str(SCRIPTS / "recover_source_pdf_anchors.py"), str(inventory), str(source_audit), "-o", str(recovered))
    run(str(SCRIPTS / "apply_repairs.py"), str(recovered), "-o", str(repaired))
    run(str(SCRIPTS / "build_manifest.py"), str(recovered), str(repaired), "-o", str(manifest))
    run(str(SCRIPTS / "completeness_audit.py"), str(recovered), str(manifest), "--source-pdf-audit", str(source_audit), "-o", str(completeness))
    report = read_json(completeness)
    assert_true(not any(item.get("rule_id") == "G3P" for item in report["content_loss"]), "Recovered source PDF anchor still produced G3P content_loss")
    assert_true(any(item.get("rule_id") == "G3R" for item in report["needs_review"]), "Recovered source PDF anchor did not require review")


def test_source_pdf_recovery_participates_in_section_sequence(tmp: Path) -> None:
    inventory = tmp / "source-pdf-recovery-section-sequence" / "source_inventory.json"
    recovered = tmp / "source-pdf-recovery-section-sequence" / "source_inventory_recovered.json"
    repaired = tmp / "source-pdf-recovery-section-sequence" / "repaired_blocks.json"
    manifest = tmp / "source-pdf-recovery-section-sequence" / "repair_manifest.json"
    source_audit = tmp / "source-pdf-recovery-section-sequence" / "source_pdf_audit.json"
    completeness = tmp / "source-pdf-recovery-section-sequence" / "completeness_report.json"
    inventory.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        inventory,
        {
            "schema_version": "0.1",
            "source": "fixture",
            "units": [
                {"unit_id": "mineru:p0:s31", "granularity": "block", "page": 0, "dtype": "title", "raw_text": "3.1 Present section", "audit_text": "3.1 present section", "bbox": [0, 100, 100, 120]},
                {"unit_id": "mineru:p0:s33", "granularity": "block", "page": 0, "dtype": "title", "raw_text": "3.3 Present section", "audit_text": "3.3 present section", "bbox": [0, 300, 100, 320]},
            ],
        },
    )
    write_json(
        source_audit,
        {
            "schema_version": "0.1",
            "anchors": ["3.1", "3.2", "3.3"],
            "anchor_locations": {
                "3.2": [{"page": 0, "char_start": 160, "snippet": "3.2 Recovered source section"}],
            },
        },
    )
    run(str(SCRIPTS / "recover_source_pdf_anchors.py"), str(inventory), str(source_audit), "-o", str(recovered))
    run(str(SCRIPTS / "apply_repairs.py"), str(recovered), "-o", str(repaired))
    run(str(SCRIPTS / "build_manifest.py"), str(recovered), str(repaired), "-o", str(manifest))
    run(str(SCRIPTS / "completeness_audit.py"), str(recovered), str(manifest), "--source-pdf-audit", str(source_audit), "-o", str(completeness))
    report = read_json(completeness)
    recovered_inventory = read_json(recovered)
    recovered_units = [unit for unit in recovered_inventory["units"] if unit.get("recovery", {}).get("anchor") == "3.2"]
    assert_true(recovered_units and recovered_units[0].get("dtype") == "title", f"Recovered section was not typed as title: {recovered_units}")
    assert_true(not any(item.get("rule_id") in {"A2", "F1"} for item in report["needs_review"]), f"Recovered section did not close sequence gap: {report['needs_review']}")
    assert_true(any(item.get("rule_id") == "G3R" for item in report["needs_review"]), "Recovered section must still require manual G3R review")


def test_source_pdf_recovery_skips_toc_and_inline_reference_candidates(tmp: Path) -> None:
    inventory = tmp / "source-pdf-recovery-candidate-quality" / "source_inventory.json"
    recovered = tmp / "source-pdf-recovery-candidate-quality" / "source_inventory_recovered.json"
    source_audit = tmp / "source-pdf-recovery-candidate-quality" / "source_pdf_audit.json"
    inventory.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        inventory,
        {
            "schema_version": "0.1",
            "source": "fixture",
            "units": [
                {"unit_id": "mineru:p0:s416", "granularity": "block", "page": 0, "dtype": "title", "raw_text": "5.4.19.16 Present", "audit_text": "5.4.19.16 present", "bbox": [0, 100, 100, 120]},
            ],
        },
    )
    write_json(
        source_audit,
        {
            "schema_version": "0.1",
            "anchors": ["5.4.19.16", "5.4.19.17", "5.8", "2.5.2", "1.000.000"],
            "anchor_locations": {
                "5.4.19.17": [{"page": 0, "snippet": "prefix text 5.4.19.17 Recovered section title Body text"}],
                "5.8": [{"page": 1, "snippet": "attempts ................................................ 67 5.8 Power supply ................................"}],
                "2.5.2": [{"page": 2, "snippet": "attributes type U32; see paragraph 2.5.2 UdM AOL When reading"}],
                "1.000.000": [{"page": 3, "snippet": "Post- R Battery 0-1.000.000 U16 Litre/ h *0.1 R"}],
            },
        },
    )
    run(str(SCRIPTS / "recover_source_pdf_anchors.py"), str(inventory), str(source_audit), "-o", str(recovered))
    recovered_inventory = read_json(recovered)
    recovered_units = recovered_inventory.get("source_pdf_recovered_anchors", [])
    anchors = {unit["anchor"] for unit in recovered_units}
    assert_true(anchors == {"5.4.19.17"}, f"Recovery should only keep credible section anchors, got {recovered_units}")
    recovered_text = recovered_inventory["units"][-1]["raw_text"]
    assert_true(recovered_text.startswith("5.4.19.17"), f"Recovered snippet should be trimmed to the anchor start: {recovered_text}")


def test_source_pdf_recovery_rejects_obis_and_numeric_field_codes(tmp: Path) -> None:
    inventory = tmp / "source-pdf-recovery-code-negatives" / "source_inventory.json"
    recovered = tmp / "source-pdf-recovery-code-negatives" / "source_inventory_recovered.json"
    source_audit = tmp / "source-pdf-recovery-code-negatives" / "source_pdf_audit.json"
    inventory.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        inventory,
        {
            "schema_version": "0.1",
            "source": "fixture",
            "units": [
                {"unit_id": "mineru:p0:body", "granularity": "block", "page": 0, "dtype": "text", "raw_text": "Body", "audit_text": "body", "bbox": [0, 0, 100, 20]},
            ],
        },
    )
    write_json(
        source_audit,
        {
            "schema_version": "0.1",
            "anchors": ["96.1.0.255", "802.15", "0.5", "5.4.19.17"],
            "anchor_locations": {
                "96.1.0.255": [{"page": 1, "snippet": "96.1.0.255 logical_name octet-string"}],
                "802.15": [{"page": 2, "snippet": "EN 802.15 wireless protocol"}],
                "0.5": [{"page": 3, "snippet": "0.5 L/h threshold value"}],
                "5.4.19.17": [{"page": 4, "snippet": "5.4.19.17 Compact frame values"}],
            },
        },
    )
    run(str(SCRIPTS / "recover_source_pdf_anchors.py"), str(inventory), str(source_audit), "-o", str(recovered))
    recovered_inventory = read_json(recovered)
    anchors = {unit.get("recovery", {}).get("anchor") for unit in recovered_inventory["units"] if unit.get("recovery")}
    assert_true(anchors == {"5.4.19.17"}, f"Recovery should reject code-like numeric anchors, got {anchors}")


def test_source_pdf_recovery_participates_in_table_figure_sequence(tmp: Path) -> None:
    inventory = tmp / "source-pdf-recovery-table-figure-sequence" / "source_inventory.json"
    recovered = tmp / "source-pdf-recovery-table-figure-sequence" / "source_inventory_recovered.json"
    repaired = tmp / "source-pdf-recovery-table-figure-sequence" / "repaired_blocks.json"
    manifest = tmp / "source-pdf-recovery-table-figure-sequence" / "repair_manifest.json"
    source_audit = tmp / "source-pdf-recovery-table-figure-sequence" / "source_pdf_audit.json"
    completeness = tmp / "source-pdf-recovery-table-figure-sequence" / "completeness_report.json"
    inventory.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        inventory,
        {
            "schema_version": "0.1",
            "source": "fixture",
            "units": [
                {"unit_id": "mineru:p0:t8", "granularity": "block", "page": 0, "dtype": "caption", "raw_text": "Table 8 - Present", "audit_text": "table 8 - present", "bbox": [0, 100, 100, 120]},
                {"unit_id": "mineru:p0:t11", "granularity": "block", "page": 0, "dtype": "caption", "raw_text": "Table 11 - Present", "audit_text": "table 11 - present", "bbox": [0, 400, 100, 420]},
                {"unit_id": "mineru:p1:f2", "granularity": "block", "page": 1, "dtype": "caption", "raw_text": "Figure 2 - Present", "audit_text": "figure 2 - present", "bbox": [0, 100, 100, 120]},
                {"unit_id": "mineru:p1:f5", "granularity": "block", "page": 1, "dtype": "caption", "raw_text": "Figure 5 - Present", "audit_text": "figure 5 - present", "bbox": [0, 400, 100, 420]},
            ],
        },
    )
    write_json(
        source_audit,
        {
            "schema_version": "0.1",
            "anchors": ["Table 8", "Table 9", "Table 10", "Table 11", "Figure 2", "Figure 3", "Figure 4", "Figure 5"],
            "anchor_locations": {
                "table 9": [{"page": 0, "char_start": 180, "snippet": "Table 9 - Recovered"}],
                "table 10": [{"page": 0, "char_start": 260, "snippet": "Table 10 - Recovered"}],
                "figure 3": [{"page": 1, "char_start": 180, "snippet": "Figure 3 - Recovered"}],
                "figure 4": [{"page": 1, "char_start": 260, "snippet": "Figure 4 - Recovered"}],
            },
        },
    )
    run(str(SCRIPTS / "recover_source_pdf_anchors.py"), str(inventory), str(source_audit), "-o", str(recovered))
    run(str(SCRIPTS / "apply_repairs.py"), str(recovered), "-o", str(repaired))
    run(str(SCRIPTS / "build_manifest.py"), str(recovered), str(repaired), "-o", str(manifest))
    run(str(SCRIPTS / "completeness_audit.py"), str(recovered), str(manifest), "--source-pdf-audit", str(source_audit), "-o", str(completeness))
    report = read_json(completeness)
    recovered_inventory = read_json(recovered)
    recovered_units = [unit for unit in recovered_inventory["units"] if unit.get("recovery")]
    assert_true(all(unit.get("dtype") == "caption" for unit in recovered_units), f"Recovered table/figure anchors were not typed as captions: {recovered_units}")
    assert_true(not any(item.get("rule_id") == "F2" for item in report["needs_review"]), f"Recovered table/figure anchors did not close F2 gaps: {report['needs_review']}")
    assert_true(any(item.get("rule_id") == "G3R" for item in report["needs_review"]), "Recovered table/figure anchors must still require manual G3R review")


def test_table_embedded_section_anchors_close_sequence_gap(tmp: Path) -> None:
    module = load_script_module("apply_repairs_table_sections", "apply_repairs.py")
    units = [
        {
            "unit_id": "seq:s36",
            "granularity": "block",
            "page": 0,
            "dtype": "title",
            "raw_text": "3.6 End customer",
            "audit_text": "3.6 end customer",
            "bbox": [40, 100, 180, 120],
        },
        {
            "unit_id": "seq:terms-table",
            "granularity": "block",
            "page": 0,
            "dtype": "table",
            "raw_text": "<table><tr><td>3.7</td><td>data concentrator</td></tr><tr><td>3.8</td><td>display</td></tr><tr><td>3.9</td><td>event</td></tr></table>",
            "audit_text": "3.7 data concentrator 3.8 display 3.9 event",
            "bbox": [40, 140, 520, 260],
        },
        {
            "unit_id": "seq:s310",
            "granularity": "block",
            "page": 0,
            "dtype": "title",
            "raw_text": "3.10 Remote reading",
            "audit_text": "3.10 remote reading",
            "bbox": [40, 300, 220, 320],
        },
    ]
    items = module.detect_review_items(units)
    assert_true(not any(item.get("rule_id") in {"A2", "F1"} for item in items), f"Table-embedded section anchors should close sequence gaps: {items}")


def test_non_definition_table_cells_do_not_create_section_sequence(tmp: Path) -> None:
    module = load_script_module("apply_repairs_table_cell_section_negatives", "apply_repairs.py")
    units = [
        {"unit_id": "seq:s511", "granularity": "block", "page": 0, "dtype": "title", "raw_text": "5.11 Alarm reset", "audit_text": "5.11 alarm reset", "bbox": [40, 100, 180, 120]},
        {
            "unit_id": "seq:diagnostics-table",
            "granularity": "block",
            "page": 0,
            "dtype": "table",
            "raw_text": "<table><tr><td>Point</td><td>Diagnostic</td><td>Activation</td></tr><tr><td>5.12</td><td>No external power supply</td><td>Immediate</td></tr><tr><td>5.15</td><td>Clock error</td><td>Delayed</td></tr></table>",
            "audit_text": "point diagnostic activation 5.12 no external power supply immediate 5.15 clock error delayed",
            "bbox": [40, 140, 520, 260],
        },
        {"unit_id": "seq:s513", "granularity": "block", "page": 1, "dtype": "title", "raw_text": "5.13 Battery alarm", "audit_text": "5.13 battery alarm", "bbox": [40, 100, 180, 120]},
        {"unit_id": "seq:s514", "granularity": "block", "page": 1, "dtype": "title", "raw_text": "5.14 Tamper alarm", "audit_text": "5.14 tamper alarm", "bbox": [40, 140, 180, 160]},
        {"unit_id": "seq:s516", "granularity": "block", "page": 1, "dtype": "title", "raw_text": "5.16 Communication alarm", "audit_text": "5.16 communication alarm", "bbox": [40, 180, 240, 200]},
    ]
    items = module.detect_review_items(units)
    offending = [
        item
        for item in items
        if item.get("rule_id") in {"A2", "F1"}
        and {item.get("previous"), item.get("current")} == {"5.12", "5.15"}
    ]
    assert_true(not offending, f"Non-definition table cells should not create section sequence gaps: {items}")


def test_table_plaintext_section_anchors_close_sequence_gap(tmp: Path) -> None:
    module = load_script_module("apply_repairs_table_plaintext_sections", "apply_repairs.py")
    units = [
        {"unit_id": "seq:s416", "granularity": "block", "page": 0, "dtype": "title", "raw_text": "5.4.19.16 Present", "audit_text": "5.4.19.16 present", "bbox": [40, 100, 180, 120]},
        {
            "unit_id": "seq:table-with-section-title",
            "granularity": "block",
            "page": 0,
            "dtype": "table",
            "raw_text": "This mixed extraction block contains data before 5.4.19.17 Compact frame values Object Value",
            "audit_text": "this table contains data before 5.4.19.17 compact frame values object value",
            "bbox": [40, 140, 520, 260],
        },
        {"unit_id": "seq:s418", "granularity": "block", "page": 1, "dtype": "title", "raw_text": "5.4.19.18 Present", "audit_text": "5.4.19.18 present", "bbox": [40, 100, 180, 120]},
    ]
    items = module.detect_review_items(units)
    assert_true(not any(item.get("rule_id") in {"A2", "F1"} for item in items), f"Plain text section anchors inside table blocks should close sequence gaps: {items}")


def test_table_suffix_section_anchors_close_sequence_gap(tmp: Path) -> None:
    module = load_script_module("apply_repairs_table_suffix_sections", "apply_repairs.py")
    units = [
        {"unit_id": "seq:s416", "granularity": "block", "page": 0, "dtype": "title", "raw_text": "5.4.19.16 Present", "audit_text": "5.4.19.16 present", "bbox": [40, 100, 180, 120]},
        {
            "unit_id": "seq:table-with-section-tail",
            "granularity": "block",
            "page": 0,
            "dtype": "table",
            "raw_text": "<table><tr><td>Object</td><td>Value</td></tr><tr><td>CF49</td><td>49</td></tr></table> 5.4.19.17 Compact frame values",
            "audit_text": "object value cf49 49 5.4.19.17 compact frame values",
            "bbox": [40, 140, 520, 260],
        },
        {"unit_id": "seq:s418", "granularity": "block", "page": 1, "dtype": "title", "raw_text": "5.4.19.18 Present", "audit_text": "5.4.19.18 present", "bbox": [40, 100, 180, 120]},
    ]
    items = module.detect_review_items(units)
    assert_true(not any(item.get("rule_id") in {"A2", "F1"} for item in items), f"Section anchors after table HTML should close sequence gaps: {items}")


def test_source_pdf_recovered_titles_do_not_create_a5_noise(tmp: Path) -> None:
    module = load_script_module("apply_repairs_recovered_title_a5", "apply_repairs.py")
    units = [
        {
            "unit_id": "source-pdf-recovery:p75:5-4-16-11-7",
            "granularity": "block",
            "page": 75,
            "dtype": "title",
            "raw_text": "5.4.16.11.7 push Il metodo push non puo essere richiamato dai client.",
            "audit_text": "5.4.16.11.7 push il metodo push non puo essere richiamato dai client.",
            "bbox": [0, 0, 0, 0],
            "recovery": {"anchor": "5.4.16.11.7"},
        },
        {
            "unit_id": "mineru:p75:para_blocks0",
            "granularity": "block",
            "page": 75,
            "dtype": "title",
            "raw_text": "5.4.16.10.3",
            "audit_text": "5.4.16.10.3",
            "bbox": [40, 100, 90, 120],
        },
    ]
    items = module.detect_review_items(units)
    assert_true(not any(item.get("rule_id") == "A5" for item in items), f"Recovered source-PDF titles should be covered by G3R, not A5 noise: {items}")


def test_table_plaintext_section_anchors_ignore_numeric_values(tmp: Path) -> None:
    module = load_script_module("apply_repairs_table_plaintext_section_negatives", "apply_repairs.py")
    bluetooth_units = [
        {
            "unit_id": "seq:bluetooth-table",
            "granularity": "block",
            "page": 0,
            "dtype": "table",
            "raw_text": "Profile Bluetooth 5.0 or superior",
            "audit_text": "profile bluetooth 5.0 or superior",
            "bbox": [40, 100, 520, 220],
        },
        {"unit_id": "seq:s52", "granularity": "block", "page": 1, "dtype": "title", "raw_text": "5.2 Real section", "audit_text": "5.2 real section", "bbox": [40, 100, 180, 120]},
    ]
    bluetooth_items = module.detect_review_items(bluetooth_units)
    assert_true(not any(item.get("rule_id") in {"A2", "F1"} for item in bluetooth_items), f"Bluetooth version values inside tables should not create section sequence gaps: {bluetooth_items}")

    decimal_units = [
        {
            "unit_id": "seq:decimal-table",
            "granularity": "block",
            "page": 0,
            "dtype": "table",
            "raw_text": "Minimum working water temperature 0.1 R test value",
            "audit_text": "minimum working water temperature 0.1 r test value",
            "bbox": [40, 100, 520, 220],
        },
        {"unit_id": "seq:s0108", "granularity": "block", "page": 2, "dtype": "title", "raw_text": "0.108 Real appendix-like anchor", "audit_text": "0.108 real appendix-like anchor", "bbox": [40, 100, 180, 120]},
    ]
    decimal_items = module.detect_review_items(decimal_units)
    assert_true(not any(item.get("rule_id") in {"A2", "F1"} for item in decimal_items), f"Decimal values inside tables should not create section sequence gaps: {decimal_items}")


def test_numbered_sequence_ignores_inline_references(tmp: Path) -> None:
    module = load_script_module("apply_repairs_numbered_references", "apply_repairs.py")
    units = [
        {"unit_id": "seq:t8", "granularity": "block", "page": 0, "dtype": "table", "raw_text": "Table 8 - Present", "audit_text": "table 8 - present", "bbox": [40, 100, 520, 130]},
        {"unit_id": "seq:ref-t11", "granularity": "block", "page": 0, "dtype": "text", "raw_text": "The reconstruction described in Table 11 is used later.", "audit_text": "the reconstruction described in table 11 is used later.", "bbox": [40, 150, 520, 170]},
        {"unit_id": "seq:t9", "granularity": "block", "page": 0, "dtype": "table", "raw_text": "Table 9 - Present", "audit_text": "table 9 - present", "bbox": [40, 200, 520, 230]},
        {"unit_id": "seq:t10", "granularity": "block", "page": 0, "dtype": "table", "raw_text": "Table 10 - Present", "audit_text": "table 10 - present", "bbox": [40, 260, 520, 290]},
        {"unit_id": "seq:t11", "granularity": "block", "page": 0, "dtype": "table", "raw_text": "Table 11 - Present", "audit_text": "table 11 - present", "bbox": [40, 320, 520, 350]},
        {"unit_id": "seq:f2", "granularity": "block", "page": 1, "dtype": "image", "raw_text": "Figure 2 - Present", "audit_text": "figure 2 - present", "bbox": [40, 100, 520, 130]},
        {"unit_id": "seq:ref-f5", "granularity": "block", "page": 1, "dtype": "text", "raw_text": "Figure 5 provides another example.", "audit_text": "figure 5 provides another example.", "bbox": [40, 150, 520, 170]},
        {"unit_id": "seq:f3", "granularity": "block", "page": 1, "dtype": "image", "raw_text": "Figure 3 - Present", "audit_text": "figure 3 - present", "bbox": [40, 200, 520, 230]},
        {"unit_id": "seq:f4", "granularity": "block", "page": 1, "dtype": "image", "raw_text": "Figure 4 - Present", "audit_text": "figure 4 - present", "bbox": [40, 260, 520, 290]},
        {"unit_id": "seq:f5", "granularity": "block", "page": 1, "dtype": "image", "raw_text": "Figure 5 - Present", "audit_text": "figure 5 - present", "bbox": [40, 320, 520, 350]},
    ]
    items = module.detect_review_items(units)
    assert_true(not any(item.get("rule_id") == "F2" for item in items), f"Inline table/figure references should not create F2 gaps: {items}")


def test_manifest_sequence_gaps_use_source_pdf_evidence(tmp: Path) -> None:
    inventory = tmp / "manifest-sequence-source-evidence" / "source_inventory.json"
    repaired = tmp / "manifest-sequence-source-evidence" / "repaired_blocks.json"
    manifest = tmp / "manifest-sequence-source-evidence" / "repair_manifest.json"
    source_audit = tmp / "manifest-sequence-source-evidence" / "source_pdf_audit.json"
    completeness = tmp / "manifest-sequence-source-evidence" / "completeness_report.json"
    inventory.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        inventory,
        {
            "schema_version": "0.1",
            "source": "fixture",
            "units": [
                {"unit_id": "fixture:p0:t6", "granularity": "block", "page": 0, "dtype": "table", "raw_text": "Table 6 - Present", "audit_text": "table 6 - present", "bbox": [0, 0, 100, 20]},
                {"unit_id": "fixture:p1:t8", "granularity": "block", "page": 1, "dtype": "table", "raw_text": "Table 8 - Present", "audit_text": "table 8 - present", "bbox": [0, 0, 100, 20]},
                {"unit_id": "fixture:p2:t11", "granularity": "block", "page": 2, "dtype": "table", "raw_text": "Table 11 - Present", "audit_text": "table 11 - present", "bbox": [0, 0, 100, 20]},
            ],
        },
    )
    run(str(SCRIPTS / "apply_repairs.py"), str(inventory), "-o", str(repaired))
    run(str(SCRIPTS / "build_manifest.py"), str(inventory), str(repaired), "-o", str(manifest))
    write_json(
        source_audit,
        {
            "schema_version": "0.1",
            "anchors": ["Table 6", "Table 8", "Table 9", "Table 10", "Table 11"],
            "anchor_locations": {
                "table 9": [{"page": 1, "snippet": "Table 9"}],
                "table 10": [{"page": 1, "snippet": "Table 10"}],
            },
        },
    )
    run(str(SCRIPTS / "completeness_audit.py"), str(inventory), str(manifest), "--source-pdf-audit", str(source_audit), "-o", str(completeness))
    report = read_json(completeness)
    f2_items = [item for item in report["needs_review"] if item.get("rule_id") == "F2"]
    assert_true(len(f2_items) == 1 and f2_items[0].get("previous") == 8, f"F2 gaps without source PDF evidence should be suppressed, got {f2_items}")
    suppressed = report["audits"].get("sequence_gap_suppressed", [])
    assert_true(any(item.get("previous") == 6 and item.get("current") == 8 for item in suppressed), "Suppressed F2 gap was not audited")


def test_section_sequence_gaps_use_structural_source_pdf_evidence(tmp: Path) -> None:
    inventory = tmp / "section-sequence-source-evidence" / "source_inventory.json"
    repaired = tmp / "section-sequence-source-evidence" / "repaired_blocks.json"
    manifest = tmp / "section-sequence-source-evidence" / "repair_manifest.json"
    source_audit = tmp / "section-sequence-source-evidence" / "source_pdf_audit.json"
    completeness = tmp / "section-sequence-source-evidence" / "completeness_report.json"
    inventory.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        inventory,
        {
            "schema_version": "0.1",
            "source": "fixture",
            "units": [
                {"unit_id": "fixture:s31", "granularity": "block", "page": 0, "dtype": "title", "raw_text": "3.1 Present", "audit_text": "3.1 present", "bbox": [0, 0, 100, 20]},
                {"unit_id": "fixture:s33", "granularity": "block", "page": 1, "dtype": "title", "raw_text": "3.3 Present", "audit_text": "3.3 present", "bbox": [0, 0, 100, 20]},
                {"unit_id": "fixture:s51", "granularity": "block", "page": 2, "dtype": "title", "raw_text": "5.1 Present", "audit_text": "5.1 present", "bbox": [0, 0, 100, 20]},
                {"unit_id": "fixture:s53", "granularity": "block", "page": 3, "dtype": "title", "raw_text": "5.3 Present", "audit_text": "5.3 present", "bbox": [0, 0, 100, 20]},
            ],
        },
    )
    run(str(SCRIPTS / "apply_repairs.py"), str(inventory), "-o", str(repaired))
    run(str(SCRIPTS / "build_manifest.py"), str(inventory), str(repaired), "-o", str(manifest))
    write_json(
        source_audit,
        {
            "schema_version": "0.1",
            "anchors": ["3.1", "3.2", "3.3", "5.1", "5.2", "5.3"],
            "anchor_locations": {
                "3.2": [{"page": 0, "snippet": "see paragraph 3.2 for details"}],
                "5.2": [{"page": 2, "snippet": "5.2 Missing structural section title"}],
            },
        },
    )
    run(str(SCRIPTS / "completeness_audit.py"), str(inventory), str(manifest), "--source-pdf-audit", str(source_audit), "-o", str(completeness))
    report = read_json(completeness)
    kept = [item for item in report["needs_review"] if item.get("rule_id") in {"A2", "F1"}]
    assert_true(kept and all(item.get("previous") == "5.1" for item in kept), f"Only structural missing section gaps should remain: {kept}")
    suppressed = report["audits"].get("sequence_gap_suppressed", [])
    assert_true(any(item.get("previous") == "3.1" and item.get("current") == "3.3" for item in suppressed), "Non-structural section gap was not suppressed")


def test_source_pdf_audit_ignores_nonstructural_required_anchor_locations(tmp: Path) -> None:
    inventory = tmp / "source-pdf-required-anchor-quality" / "source_inventory.json"
    repaired = tmp / "source-pdf-required-anchor-quality" / "repaired_blocks.json"
    manifest = tmp / "source-pdf-required-anchor-quality" / "repair_manifest.json"
    source_audit = tmp / "source-pdf-required-anchor-quality" / "source_pdf_audit.json"
    completeness = tmp / "source-pdf-required-anchor-quality" / "completeness_report.json"
    inventory.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        inventory,
        {
            "schema_version": "0.1",
            "source": "fixture",
            "units": [
                {"unit_id": "fixture:s1", "granularity": "block", "page": 0, "dtype": "text", "raw_text": "Body content", "audit_text": "body content", "bbox": [0, 0, 100, 20]},
            ],
        },
    )
    write_json(
        source_audit,
        {
            "schema_version": "0.1",
            "anchors": ["2.5.2", "5.8", "1.000.000"],
            "anchor_locations": {
                "2.5.2": [{"page": 2, "snippet": "attributes type U32; see paragraph 2.5.2 UdM AOL When reading"}],
                "5.8": [{"page": 1, "snippet": "attempts ................................................ 67 5.8 Power supply ................................"}],
                "1.000.000": [{"page": 3, "snippet": "Post- R Battery 0-1.000.000 U16 Litre/ h *0.1 R"}],
            },
        },
    )
    run(str(SCRIPTS / "apply_repairs.py"), str(inventory), "-o", str(repaired))
    run(str(SCRIPTS / "build_manifest.py"), str(inventory), str(repaired), "-o", str(manifest))
    run(str(SCRIPTS / "completeness_audit.py"), str(inventory), str(manifest), "--source-pdf-audit", str(source_audit), "-o", str(completeness))
    report = read_json(completeness)
    assert_true(not any(item.get("rule_id") == "G3P" for item in report["content_loss"]), f"Non-structural source PDF anchors should not produce G3P: {report['content_loss']}")


def test_candidate_anchor_filters_standard_prefix_noise(tmp: Path) -> None:
    inventory = tmp / "candidate-anchor-prefix-noise" / "source_inventory.json"
    repaired = tmp / "candidate-anchor-prefix-noise" / "repaired_blocks.json"
    manifest = tmp / "candidate-anchor-prefix-noise" / "repair_manifest.json"
    completeness = tmp / "candidate-anchor-prefix-noise" / "completeness_report.json"
    inventory.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        inventory,
        {
            "schema_version": "0.1",
            "source": "fixture",
            "units": [
                {"unit_id": "fixture:p0:src", "granularity": "block", "page": 0, "dtype": "text", "raw_text": "UNI 5 reference text", "audit_text": "uni 5 reference text", "bbox": [0, 0, 100, 20]},
            ],
        },
    )
    write_json(
        repaired,
        {
            "schema_version": "0.1",
            "source_inventory": str(inventory),
            "output_blocks": [
                {"output_id": "out:fixture:p0:src", "raw_text": "reference text", "audit_text": "reference text", "source_refs": ["fixture:p0:src"], "operation": "emit", "confidence": 1.0, "disposition": "emitted", "page": 0}
            ],
            "findings": [],
            "needs_review": [],
            "not_implemented": [],
        },
    )
    run(str(SCRIPTS / "build_manifest.py"), str(inventory), str(repaired), "-o", str(manifest))
    run(str(SCRIPTS / "completeness_audit.py"), str(inventory), str(manifest), "-o", str(completeness))
    report = read_json(completeness)
    assert_true(not any(item.get("rule_id") == "G3C" and "uni 5" in item.get("anchors", []) for item in report["needs_review"]), "UNI 5 prefix noise should not produce G3C")


def test_regression_case_library_schema() -> None:
    module = load_script_module("run_regression_cases", "run_regression_cases.py")
    errors = module.validate_case_library(FIXTURES / "regression-cases.json")
    assert_true(not errors, f"Regression case library errors: {errors}")


def test_render_html_preserves_tables(tmp: Path) -> None:
    repaired = tmp / "table-html" / "repaired_blocks.json"
    html = tmp / "table-html" / "repaired.html"
    repaired.parent.mkdir(parents=True, exist_ok=True)
    table = "<table><tr><td>A</td></tr></table>"
    write_json(
        repaired,
        {
            "schema_version": "0.1",
            "output_blocks": [
                {
                    "output_id": "out:table",
                    "raw_text": table,
                    "audit_text": "a",
                    "source_refs": ["fixture:p0:block0"],
                    "operation": "emit",
                    "confidence": 1.0,
                    "disposition": "emitted",
                    "page": 0,
                }
            ],
        },
    )
    run(str(SCRIPTS / "render_html.py"), str(repaired), "-o", str(html))
    rendered = html.read_text(encoding="utf-8-sig")
    assert_true("<table><tr><td>A</td></tr></table>" in rendered, "Table HTML was not preserved")
    assert_true("&lt;table" not in rendered, "Table HTML was escaped")


def test_review_rules(tmp: Path) -> None:
    fixture = read_json(FIXTURES / "review-rules.json")
    result = run_chain(tmp / "review-rules", fixture["units"], "\n".join(u["raw_text"] for u in fixture["units"]))
    review_rule_ids = {item.get("rule_id") for item in result["completeness"]["needs_review"]}
    expected = set(fixture["expected_review_rules"])
    assert_true(expected.issubset(review_rule_ids), f"Review rules missing: {sorted(expected - review_rule_ids)}")


def test_noisy_review_rule_negatives(tmp: Path) -> None:
    module = load_script_module("apply_repairs", "apply_repairs.py")
    units = [
        {
            "unit_id": "n:italian-dominant-1",
            "granularity": "block",
            "page": 0,
            "dtype": "text",
            "raw_text": "La specifica tecnica definisce il modello dati del contatore.",
            "audit_text": "la specifica tecnica definisce il modello dati del contatore.",
            "bbox": [40, 100, 520, 120],
        },
        {
            "unit_id": "n:italian-dominant-2",
            "granularity": "block",
            "page": 0,
            "dtype": "text",
            "raw_text": "Il dispositivo deve essere configurato secondo le funzioni previste.",
            "audit_text": "il dispositivo deve essere configurato secondo le funzioni previste.",
            "bbox": [40, 130, 520, 150],
        },
        {
            "unit_id": "n:date-month",
            "granularity": "block",
            "page": 1,
            "dtype": "text",
            "raw_text": "The specification was ratified on 19 February 2026.",
            "audit_text": "the specification was ratified on 19 february 2026.",
            "bbox": [40, 180, 520, 200],
        },
        {
            "unit_id": "n:body-standard-ref",
            "granularity": "block",
            "page": 1,
            "dtype": "text",
            "raw_text": "Users should verify the existence of UNI standards corresponding to EN or ISO standards where cited.",
            "audit_text": "users should verify the existence of uni standards corresponding to en or iso standards where cited.",
            "bbox": [40, 770, 520, 790],
        },
        {
            "unit_id": "n:parent-heading",
            "granularity": "block",
            "page": 2,
            "dtype": "title",
            "raw_text": "5 Requirements",
            "audit_text": "5 requirements",
            "bbox": [40, 100, 200, 118],
        },
        {
            "unit_id": "n:child-heading",
            "granularity": "block",
            "page": 2,
            "dtype": "title",
            "raw_text": "5.1 Functional requirements",
            "audit_text": "5.1 functional requirements",
            "bbox": [40, 130, 280, 148],
        },
    ]
    items = module.detect_review_items(units)
    by_rule = {}
    for item in items:
        by_rule.setdefault(item.get("rule_id"), []).append(item)
    assert_true("C3" not in by_rule, f"C3 should not flag dominant Italian document text: {by_rule.get('C3')}")
    assert_true("E2" not in by_rule, f"E2 should not flag dates/months as units: {by_rule.get('E2')}")
    assert_true("C2" not in by_rule, f"C2 should not flag body text merely because it cites UNI/ISO near page edge: {by_rule.get('C2')}")
    assert_true("A5" not in by_rule, f"A5 should not flag parent-to-child heading transitions: {by_rule.get('A5')}")


def test_header_footer_discard_and_unit_noise(tmp: Path) -> None:
    (tmp / "header-footer-discard-and-unit-noise").mkdir(parents=True, exist_ok=True)
    units = [
        {
            "unit_id": "n:discarded-header",
            "granularity": "block",
            "page": 0,
            "dtype": "discarded_blocks",
            "raw_text": "UNI/TS 12007:2026",
            "audit_text": "uni/ts 12007:2026",
            "bbox": [220, 20, 360, 34],
        },
        {
            "unit_id": "n:toc-title-data",
            "granularity": "block",
            "page": 0,
            "dtype": "text",
            "raw_text": "Functional Requirements .... 37 Data Collection and Recording .... 28",
            "audit_text": "functional requirements .... 37 data collection and recording .... 28",
            "bbox": [40, 120, 520, 140],
        },
        {
            "unit_id": "n:time-unit",
            "granularity": "block",
            "page": 0,
            "dtype": "text",
            "raw_text": "The clock is synchronized every 3 days and the flow is calculated every 5 min.",
            "audit_text": "the clock is synchronized every 3 days and the flow is calculated every 5 min.",
            "bbox": [40, 160, 520, 180],
        },
        {
            "unit_id": "n:bad-unit",
            "granularity": "block",
            "page": 0,
            "dtype": "text",
            "raw_text": "The maximum flow is 10 xyz.",
            "audit_text": "the maximum flow is 10 xyz.",
            "bbox": [40, 200, 520, 220],
        },
    ]
    result = run_chain(tmp / "header-footer-discard-and-unit-noise", units, "Functional Requirements\nThe maximum flow is 10 xyz.")
    dispositions = result["manifest"]["source_dispositions"]
    assert_true(dispositions["n:discarded-header"] == "discarded", "Safe header/footer block was not marked discarded")
    rendered_texts = [block.get("raw_text") for block in result["repaired"]["output_blocks"] if block.get("disposition") != "discarded"]
    assert_true("UNI/TS 12007:2026" not in rendered_texts, "Discarded header/footer remained in rendered output blocks")
    e2_items = [item for item in result["completeness"]["needs_review"] if item.get("rule_id") == "E2"]
    values = {item.get("value") for item in e2_items}
    assert_true(values == {"10 xyz"}, f"E2 should only flag truly suspicious units, got {values}")


def test_remaining_review_noise_boundaries(tmp: Path) -> None:
    (tmp / "remaining-review-noise-boundaries").mkdir(parents=True, exist_ok=True)
    module = load_script_module("apply_repairs_remaining_noise", "apply_repairs.py")
    units = [
        {
            "unit_id": "n:standalone-footnote",
            "granularity": "block",
            "page": 0,
            "dtype": "page_footnote",
            "raw_text": "7) The service also allows the user to detect fraud attempts.",
            "audit_text": "7) the service also allows the user to detect fraud attempts.",
            "bbox": [115, 740, 525, 769],
        },
        {
            "unit_id": "n:copyright-page-footer",
            "granularity": "block",
            "page": 0,
            "dtype": "footer",
            "raw_text": "© UNI\nPagina 8",
            "audit_text": "© uni pagina 8",
            "bbox": [439, 799, 528, 812],
        },
        {
            "unit_id": "n:next-page-table",
            "granularity": "block",
            "page": 1,
            "dtype": "table",
            "raw_text": "Table 1\n<table><tr><td>A</td></tr></table>",
            "audit_text": "table 1 a",
            "bbox": [61, 73, 549, 154],
        },
        {
            "unit_id": "n:heading-main",
            "granularity": "block",
            "page": 1,
            "dtype": "title",
            "raw_text": "Data Collection and Recording",
            "audit_text": "data collection and recording",
            "bbox": [135, 497, 280, 511],
        },
        {
            "unit_id": "n:heading-general",
            "granularity": "block",
            "page": 1,
            "dtype": "title",
            "raw_text": "General information",
            "audit_text": "general information",
            "bbox": [134, 523, 185, 533],
        },
        {
            "unit_id": "n:normal-unit-words",
            "granularity": "block",
            "page": 1,
            "dtype": "text",
            "raw_text": "The table uses 6 sec, 500 kbps, and 1 ora as accepted examples. Italian prose has 2 deve, 11 del, and 1 mese.",
            "audit_text": "the table uses 6 sec, 500 kbps, and 1 ora as accepted examples. italian prose has 2 deve, 11 del, and 1 mese.",
            "bbox": [40, 600, 520, 620],
        },
        {
            "unit_id": "n:bad-unit-2",
            "granularity": "block",
            "page": 1,
            "dtype": "text",
            "raw_text": "The maximum flow is 10 xyz.",
            "audit_text": "the maximum flow is 10 xyz.",
            "bbox": [40, 650, 520, 670],
        },
    ]
    items = module.detect_review_items(units)
    by_rule = {}
    for item in items:
        by_rule.setdefault(item.get("rule_id"), []).append(item)
    assert_true("C1" not in by_rule, f"Standalone footnotes should not be C1 contamination: {by_rule.get('C1')}")
    assert_true("B3" not in by_rule, f"Footer-to-next-page blocks should not be B3: {by_rule.get('B3')}")
    assert_true("A5" not in by_rule, f"Normal adjacent headings should not be A5: {by_rule.get('A5')}")
    e2_values = {item.get("value") for item in by_rule.get("E2", [])}
    assert_true(e2_values == {"10 xyz"}, f"E2 should ignore accepted units/common words, got {e2_values}")


def test_real_pdf_review_noise_boundaries(tmp: Path) -> None:
    module = load_script_module("apply_repairs_real_pdf_noise", "apply_repairs.py")
    units = [
        {
            "unit_id": "real:bottom-footnote-text",
            "granularity": "block",
            "page": 0,
            "dtype": "text",
            "raw_text": "33) Expected date of Welmec 7.2:2022 and OIML D0.31:2023.",
            "audit_text": "33) expected date of welmec 7.2:2022 and oiml d0.31:2023.",
            "bbox": [134, 773, 342, 784],
        },
        {
            "unit_id": "real:long-bottom-footnote-text",
            "granularity": "block",
            "page": 0,
            "dtype": "text",
            "raw_text": "7) The service allows you to verify the error in measuring the quantities consumed during the billing period and verify the adequacy of the installed meter. The service also allows you to detect fraud attempts, recalculate the water network regime, and assess uncertainty.",
            "audit_text": "7) the service allows you to verify the error in measuring the quantities consumed during the billing period and verify the adequacy of the installed meter. the service also allows you to detect fraud attempts, recalculate the water network regime, and assess uncertainty.",
            "bbox": [115, 740, 525, 769],
        },
        {
            "unit_id": "real:italian-technical-1",
            "granularity": "block",
            "page": 1,
            "dtype": "text",
            "raw_text": "Il remote meter deve essere configurato per gestire data ed ora secondo le funzioni previste.",
            "audit_text": "il remote meter deve essere configurato per gestire data ed ora secondo le funzioni previste.",
            "bbox": [132, 74, 529, 159],
        },
        {
            "unit_id": "real:italian-technical-2",
            "granularity": "block",
            "page": 1,
            "dtype": "text",
            "raw_text": "La specifica tecnica definisce il modello dati del contatore.",
            "audit_text": "la specifica tecnica definisce il modello dati del contatore.",
            "bbox": [132, 180, 529, 210],
        },
        {
            "unit_id": "real:heading-name",
            "granularity": "block",
            "page": 2,
            "dtype": "title",
            "raw_text": "Communication",
            "audit_text": "communication",
            "bbox": [134, 451, 199, 463],
        },
        {
            "unit_id": "real:heading-number",
            "granularity": "block",
            "page": 2,
            "dtype": "title",
            "raw_text": "5.17.1",
            "audit_text": "5.17.1",
            "bbox": [37, 476, 62, 487],
        },
        {
            "unit_id": "real:heading-monitoring",
            "granularity": "block",
            "page": 2,
            "dtype": "title",
            "raw_text": "Monitoring parameters at the point of delivery - Verification of the temperature range of the water",
            "audit_text": "monitoring parameters at the point of delivery - verification of the temperature range of the water",
            "bbox": [156, 520, 486, 543],
        },
        {
            "unit_id": "real:heading-definitions",
            "granularity": "block",
            "page": 2,
            "dtype": "title",
            "raw_text": "Definitions",
            "audit_text": "definitions",
            "bbox": [157, 547, 201, 557],
        },
        {
            "unit_id": "real:heading-appendix",
            "granularity": "block",
            "page": 2,
            "dtype": "title",
            "raw_text": "APPENDIX",
            "audit_text": "appendix",
            "bbox": [38, 600, 90, 612],
        },
        {
            "unit_id": "real:heading-regulations",
            "granularity": "block",
            "page": 2,
            "dtype": "title",
            "raw_text": "(regulations)",
            "audit_text": "(regulations)",
            "bbox": [38, 616, 94, 629],
        },
        {
            "unit_id": "real:heading-reset-body",
            "granularity": "block",
            "page": 2,
            "dtype": "text",
            "raw_text": "This appendix contains normative material.",
            "audit_text": "this appendix contains normative material.",
            "bbox": [38, 638, 300, 650],
        },
        {
            "unit_id": "real:terms-heading",
            "granularity": "block",
            "page": 2,
            "dtype": "title",
            "raw_text": "TERMINI E DEFINIZIONI, SIGLE E ABBREVIAZIONI",
            "audit_text": "termini e definizioni, sigle e abbreviazioni",
            "bbox": [134, 658, 372, 673],
        },
        {
            "unit_id": "real:terms-subheading",
            "granularity": "block",
            "page": 2,
            "dtype": "title",
            "raw_text": "Termini e definizioni<sup>1)</sup>",
            "audit_text": "termini e definizioni 1",
            "bbox": [133, 683, 234, 699],
        },
        {
            "unit_id": "real:terms-reset-body",
            "granularity": "block",
            "page": 2,
            "dtype": "text",
            "raw_text": "The following terms are used in this document.",
            "audit_text": "the following terms are used in this document.",
            "bbox": [133, 704, 320, 716],
        },
        {
            "unit_id": "real:table-title",
            "granularity": "block",
            "page": 2,
            "dtype": "title",
            "raw_text": "Bit-mask delle autorizzazioni batterie",
            "audit_text": "bit-mask delle autorizzazioni batterie",
            "bbox": [134, 720, 281, 732],
        },
        {
            "unit_id": "real:table-number-title",
            "granularity": "block",
            "page": 2,
            "dtype": "title",
            "raw_text": "prospetto 10",
            "audit_text": "prospetto 10",
            "bbox": [76, 721, 126, 732],
        },
        {
            "unit_id": "real:struct-open",
            "granularity": "block",
            "page": 3,
            "dtype": "text",
            "raw_text": "{",
            "audit_text": "{",
            "bbox": [157, 170, 164, 183],
        },
        {
            "unit_id": "real:struct-field-1",
            "granularity": "block",
            "page": 3,
            "dtype": "text",
            "raw_text": "image_block_number: double-long-unsigned,",
            "audit_text": "image_block_number: double-long-unsigned,",
            "bbox": [155, 185, 358, 199],
        },
        {
            "unit_id": "real:struct-field-2",
            "granularity": "block",
            "page": 3,
            "dtype": "text",
            "raw_text": "image_block_value: octet-string",
            "audit_text": "image_block_value: octet-string",
            "bbox": [155, 201, 300, 214],
        },
        {
            "unit_id": "real:left-field",
            "granularity": "block",
            "page": 4,
            "dtype": "text",
            "raw_text": "saturday_intervals:",
            "audit_text": "saturday_intervals:",
            "bbox": [173, 734, 261, 747],
        },
        {
            "unit_id": "real:right-type",
            "granularity": "block",
            "page": 4,
            "dtype": "text",
            "raw_text": "array of 5 unsigned,",
            "audit_text": "array of 5 unsigned,",
            "bbox": [348, 734, 440, 748],
        },
        {
            "unit_id": "real:appendix-anchor",
            "granularity": "block",
            "page": 4,
            "dtype": "text",
            "raw_text": "A.1",
            "audit_text": "a.1",
            "bbox": [60, 115, 74, 125],
        },
        {
            "unit_id": "real:appendix-anchor-title",
            "granularity": "block",
            "page": 4,
            "dtype": "text",
            "raw_text": "General information",
            "audit_text": "general information",
            "bbox": [157, 117, 212, 126],
        },
        {
            "unit_id": "real:protocol-expression",
            "granularity": "block",
            "page": 4,
            "dtype": "text",
            "raw_text": "Preamble (1) || Access Address (4) || Header (2) || Payload (AdvData) || CRC (3)",
            "audit_text": "preamble (1) || access address (4) || header (2) || payload (advdata) || crc (3)",
            "bbox": [133, 211, 453, 223],
        },
        {
            "unit_id": "real:source-recovery-expression",
            "granularity": "block",
            "page": 4,
            "dtype": "source_pdf_recovery",
            "raw_text": ")|| Totneg(4)|| Tot_F1(4)|| Tot_F2(4)|| Tot_F3(4) Post- R Battery 0-1.000.000 U16 Litre/ h *0.1 R R Leakage determination interval R Activates",
            "audit_text": ")|| totneg(4)|| tot_f1(4)|| tot_f2(4)|| tot_f3(4) post- r battery 0-1.000.000 u16 litre/ h *0.1 r r leakage determination interval r activates",
            "bbox": [0, 0, 0, 0],
        },
        {
            "unit_id": "real:placeholder-angle",
            "granularity": "block",
            "page": 4,
            "dtype": "text",
            "raw_text": "This program must allow regular provision with a configurable <<P>> periodicity.",
            "audit_text": "this program must allow regular provision with a configurable <<p>> periodicity.",
            "bbox": [133, 300, 453, 320],
        },
        {
            "unit_id": "real:definition-uses-meter",
            "granularity": "block",
            "page": 4,
            "dtype": "text",
            "raw_text": "auxiliary functional device or module associated with a meter, to which ancillary functions are attributable.",
            "audit_text": "auxiliary functional device or module associated with a meter, to which ancillary functions are attributable.",
            "bbox": [133, 330, 453, 350],
        },
        {
            "unit_id": "real:defined-by-standard",
            "granularity": "block",
            "page": 4,
            "dtype": "text",
            "raw_text": "They are divided into AFD1, AFD2, and AFD3 according to the criteria defined by UNI EN 14154-4.",
            "audit_text": "they are divided into afd1, afd2, and afd3 according to the criteria defined by uni en 14154-4.",
            "bbox": [133, 360, 453, 380],
        },
        {
            "unit_id": "real:defined-in-compliance",
            "granularity": "block",
            "page": 4,
            "dtype": "text",
            "raw_text": "The max error at Qstart is defined in compliance with MID-ANNEX I clause 7.3 in the case of gas meter flows.",
            "audit_text": "the max error at qstart is defined in compliance with mid-annex i clause 7.3 in the case of gas meter flows.",
            "bbox": [133, 390, 453, 410],
        },
        {
            "unit_id": "real:defined-in-appendix",
            "granularity": "block",
            "page": 4,
            "dtype": "text",
            "raw_text": "The battery life shall continue beyond the operational life of the meter, if used in reference modes defined in Appendix A.",
            "audit_text": "the battery life shall continue beyond the operational life of the meter, if used in reference modes defined in appendix a.",
            "bbox": [133, 420, 453, 440],
        },
        {
            "unit_id": "real:parameters-not-meter",
            "granularity": "block",
            "page": 4,
            "dtype": "text",
            "raw_text": "security parameters and unique device identifier defined with the OTAA method can be used",
            "audit_text": "security parameters and unique device identifier defined with the otaa method can be used",
            "bbox": [133, 450, 453, 470],
        },
        {
            "unit_id": "real:footnote-defined-by",
            "granularity": "block",
            "page": 4,
            "dtype": "page_footnote",
            "raw_text": "49) The Qstart start-up flow rate influences the macro-indicator M1 defined in ARERA resolution 917-17 downstream of the meter.",
            "audit_text": "49) the qstart start-up flow rate influences the macro-indicator m1 defined in arera resolution 917-17 downstream of the meter.",
            "bbox": [134, 750, 500, 770],
        },
        {
            "unit_id": "real:event-code-table",
            "granularity": "block",
            "page": 4,
            "dtype": "table",
            "raw_text": "Table C.5 - Event Code <table><tr><td>Code</td><td>Meaning of the Event</td><td>M = metrological</td><td>A_Field1</td><td>A_Field2</td></tr><tr><td>1</td><td>Device RESET performed</td><td>M</td><td>0= partial reset 1= total reset</td><td></td></tr></table>",
            "audit_text": "table c.5 - event code code meaning of the event m = metrological a_field1 a_field2 1 device reset performed m 0= partial reset 1= total reset",
            "bbox": [38, 491, 527, 772],
        },
        {
            "unit_id": "real:time-and-month-words",
            "granularity": "block",
            "page": 4,
            "dtype": "text",
            "raw_text": "The schedule runs for 2 mesi and transmits from 7:30 am until 5:30 pm.",
            "audit_text": "the schedule runs for 2 mesi and transmits from 7:30 am until 5:30 pm.",
            "bbox": [133, 250, 453, 270],
        },
        {
            "unit_id": "real:schema-cross-page-bottom",
            "granularity": "block",
            "page": 4,
            "dtype": "text",
            "raw_text": "total_time_spent_in_deep_sleep: il tempo totale speso nella fase di deep-sleep, espresso in secondi",
            "audit_text": "total_time_spent_in_deep_sleep: il tempo totale speso nella fase di deep-sleep, espresso in secondi",
            "bbox": [155, 751, 550, 775],
        },
        {
            "unit_id": "real:schema-cross-page-top",
            "granularity": "block",
            "page": 5,
            "dtype": "text",
            "raw_text": "total_time_spent_in_paging: il tempo totale speso nella fase di paging, espresso in secondi",
            "audit_text": "total_time_spent_in_paging: il tempo totale speso nella fase di paging, espresso in secondi",
            "bbox": [132, 56, 528, 81],
        },
        {
            "unit_id": "real:footnote-72",
            "granularity": "block",
            "page": 5,
            "dtype": "text",
            "raw_text": "72) The default value of Dpm is 25d in compliance with ARERA Resolution 221-2020/idr.",
            "audit_text": "72) the default value of dpm is 25d in compliance with arera resolution 221-2020/idr.",
            "bbox": [134, 718, 477, 738],
        },
        {
            "unit_id": "real:footnote-74",
            "granularity": "block",
            "page": 5,
            "dtype": "text",
            "raw_text": "74) Svf can determine whether the valve can remain closed at the end of the Dpm period.",
            "audit_text": "74) svf can determine whether the valve can remain closed at the end of the dpm period.",
            "bbox": [135, 764, 509, 784],
        },
    ]
    items = module.detect_review_items(units)
    by_rule = {}
    for item in items:
        by_rule.setdefault(item.get("rule_id"), []).append(item)
    for rule in ("C1", "C3", "A5", "B2", "B3", "C4", "D3", "E2", "E3", "F3", "A2", "F1"):
        assert_true(rule not in by_rule, f"{rule} should ignore real-PDF noise boundaries: {by_rule.get(rule)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run pdf-layout-repair fixture smoke tests.")
    parser.add_argument("--keep", action="store_true", help="Keep temporary artifacts and print their path.")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="pdf-layout-repair-fixtures-") as tmp_name:
        tmp = Path(tmp_name)
        for child in (
            "a1-positive",
            "a1-negative",
            "general-repair",
            "review-rules",
            "negative-b1",
            "negative-d1",
            "negative-e1",
        ):
            (tmp / child).mkdir(parents=True, exist_ok=True)
        test_a1_positive(tmp)
        test_a1_negative(tmp)
        test_missing_anchor(tmp)
        test_general_repairs(tmp)
        test_general_repair_negatives(tmp)
        test_g2_review_band(tmp)
        test_g2_full_char_coverage_with_anchors_is_suppressed(tmp)
        test_g5_local_semantic_sampling_passes_when_samples_are_covered(tmp)
        test_canonical_tokens_preserve_angle_expressions()
        test_review_decisions_resolve_matched_needs_review(tmp)
        test_post_render_uses_output_anchors_only(tmp)
        test_source_pdf_audit_required_anchor_gate(tmp)
        test_source_pdf_anchor_whitespace_normalization(tmp)
        test_mineru_v4_zip_url_extraction()
        test_source_pdf_audit_anchor_locations(tmp)
        test_source_pdf_anchor_recovery_downgrades_loss_to_review(tmp)
        test_source_pdf_recovery_participates_in_section_sequence(tmp)
        test_source_pdf_recovery_skips_toc_and_inline_reference_candidates(tmp)
        test_source_pdf_recovery_rejects_obis_and_numeric_field_codes(tmp)
        test_source_pdf_recovery_participates_in_table_figure_sequence(tmp)
        test_table_embedded_section_anchors_close_sequence_gap(tmp)
        test_non_definition_table_cells_do_not_create_section_sequence(tmp)
        test_table_plaintext_section_anchors_close_sequence_gap(tmp)
        test_table_suffix_section_anchors_close_sequence_gap(tmp)
        test_source_pdf_recovered_titles_do_not_create_a5_noise(tmp)
        test_table_plaintext_section_anchors_ignore_numeric_values(tmp)
        test_numbered_sequence_ignores_inline_references(tmp)
        test_manifest_sequence_gaps_use_source_pdf_evidence(tmp)
        test_section_sequence_gaps_use_structural_source_pdf_evidence(tmp)
        test_source_pdf_audit_ignores_nonstructural_required_anchor_locations(tmp)
        test_candidate_anchor_filters_standard_prefix_noise(tmp)
        test_regression_case_library_schema()
        test_render_html_preserves_tables(tmp)
        test_review_rules(tmp)
        test_noisy_review_rule_negatives(tmp)
        test_header_footer_discard_and_unit_noise(tmp)
        test_remaining_review_noise_boundaries(tmp)
        test_real_pdf_review_noise_boundaries(tmp)
        if args.keep:
            keep_path = Path(tempfile.gettempdir()) / "pdf-layout-repair-fixtures-last"
            if keep_path.exists():
                import shutil

                shutil.rmtree(keep_path)
            import shutil

            shutil.copytree(tmp, keep_path)
            print(f"fixture artifacts: {keep_path}")
    print("fixture smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
