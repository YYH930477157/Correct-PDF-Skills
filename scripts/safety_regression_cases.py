#!/usr/bin/env python3
"""Negative regressions for completeness and delivery gates."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def load_module(name: str, script: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / script)
    if not spec or not spec.loader:
        raise AssertionError(f"Cannot load {script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_image_only_page_gate(tmp: Path) -> None:
    inventory_path = tmp / "image-only-inventory.json"
    manifest_path = tmp / "image-only-manifest.json"
    source_audit_path = tmp / "image-only-source-audit.json"
    report_path = tmp / "image-only-report.json"
    write_json(inventory_path, {"schema_version": "0.1", "units": []})
    write_json(manifest_path, {"schema_version": "0.1", "output_blocks": [], "source_dispositions": {}, "findings": [], "needs_review": [], "not_implemented": []})
    write_json(source_audit_path, {
        "schema_version": "0.2",
        "page_count": 1,
        "pages": [{"page": 0, "text_chars": 0, "image_count": 1, "drawing_count": 0, "anchors": []}],
        "anchors": [],
        "anchor_locations": {},
    })
    subprocess.run([sys.executable, str(SCRIPTS / "completeness_audit.py"), str(inventory_path), str(manifest_path), "--source-pdf-audit", str(source_audit_path), "-o", str(report_path)], check=True)
    report = read_json(report_path)
    assert report["document_status"] != "final", report
    findings = report["content_loss"] + report["needs_review"]
    assert any(item.get("rule_id") in {"G1P", "G4M"} for item in findings), report


def test_partial_review_decision() -> None:
    module = load_module("safety_partial_review", "completeness_audit.py")
    item = module.assign_review_item_ids(
        [{"rule_id": "G3R", "reason": "source_pdf_recovered_content_requires_review", "units": [{"unit_id": "u1"}, {"unit_id": "u2"}, {"unit_id": "u3"}]}]
    )[0]
    context = {"source_inventory_sha256": "a" * 64, "repair_manifest_sha256": "b" * 64}
    decisions = {
        "reviewer": "fixture-reviewer",
        "reviewed_at": "2026-07-10T00:00:00Z",
        "artifacts": context,
        "decisions": [{"action": "accept_review", "review_item_id": item["review_item_id"], "rule_id": "G3R", "unit_ids": ["u1"], "reason": "Only u1 was checked."}],
    }
    unresolved, audit = module.apply_review_decisions([item], decisions, context)
    assert unresolved == [item], audit


def test_g5_locality_and_zero_samples() -> None:
    module = load_module("safety_g5", "completeness_audit.py")
    short = {"unit_id": "short", "granularity": "block", "page": 0, "audit_text": "short text"}
    zero = module.local_semantic_sampling([short], {}, [])
    assert zero["status"] == "review", zero
    source = {"unit_id": "src1", "granularity": "block", "page": 0, "audit_text": "alpha beta gamma delta epsilon zeta eta theta iota kappa"}
    outputs = [{"output_id": "other", "source_refs": ["different-source"], "audit_text": source["audit_text"], "disposition": "emitted", "page": 4}]
    misplaced = module.local_semantic_sampling([source], {}, outputs)
    assert misplaced["status"] == "review", misplaced


def test_recovery_requires_bbox_line(tmp: Path) -> None:
    module = load_module("safety_recovery", "recover_source_pdf_anchors.py")
    inventory = {"schema_version": "0.1", "units": []}
    source_audit = {
        "schema_version": "0.2",
        "anchors": ["5.8", "5.9"],
        "anchor_locations": {
            "5.8": [{"page": 1, "snippet": "5.8 Machine Translated by Google"}],
            "5.9": [{"page": 2, "snippet": "5.9 Functional requirements followed by unrelated body text", "line_text": "5.9 Functional requirements", "heading_like": True, "bbox": [40, 120, 260, 138]}],
        },
    }
    recovered = module.recover_inventory(inventory, source_audit)
    emitted = {unit.get("recovery", {}).get("anchor"): unit for unit in recovered.get("units", []) if unit.get("recovery")}
    assert "5.8" not in emitted, emitted
    assert emitted["5.9"]["raw_text"] == "5.9 Functional requirements", emitted
    candidates = {item.get("anchor") for item in recovered.get("source_pdf_recovery_candidates", [])}
    assert "5.8" in candidates, recovered


def test_review_hash_binding(tmp: Path) -> None:
    module = load_module("safety_review_hash", "completeness_audit.py")
    inventory_path = tmp / "inventory.json"
    manifest_path = tmp / "manifest.json"
    write_json(inventory_path, {"units": [{"unit_id": "u1"}]})
    write_json(manifest_path, {"output_blocks": []})
    item = module.assign_review_item_ids([{"rule_id": "C3", "reason": "possible_foreign_language_contamination", "source_refs": ["u1"]}])[0]
    context = {"source_inventory_sha256": sha256(inventory_path), "repair_manifest_sha256": sha256(manifest_path)}
    stale = {
        "reviewer": "fixture-reviewer",
        "reviewed_at": "2026-07-10T00:00:00Z",
        "artifacts": {"source_inventory_sha256": "0" * 64, "repair_manifest_sha256": context["repair_manifest_sha256"]},
        "decisions": [{"action": "accept_review", "review_item_id": item["review_item_id"], "rule_id": "C3", "source_refs": ["u1"], "reason": "Checked current source."}],
    }
    unresolved, audit = module.apply_review_decisions([item], stale, context)
    assert unresolved == [item], audit
    assert audit["status"] == "invalid", audit


def test_pdf_delivery_failure(tmp: Path) -> None:
    module = load_module("safety_pdf_delivery", "run_pipeline.py")
    html = tmp / "delivery.html"
    pdf = tmp / "delivery.pdf"
    html.write_text("<html><body>content</body></html>", encoding="utf-8")
    result = module.html_to_pdf(html, pdf, candidates=[])
    assert result["status"] == "failed", result
    assert not pdf.exists()
    delivery_status, exit_code = module.delivery_exit_code(False, result, pdf.exists())
    assert delivery_status == "failed", delivery_status


    assert exit_code != 0, exit_code
def main() -> int:
    with tempfile.TemporaryDirectory(prefix="pdf-layout-repair-safety-") as tmp_name:
        tmp = Path(tmp_name)
        test_image_only_page_gate(tmp)
        test_partial_review_decision()
        test_g5_locality_and_zero_samples()
        test_recovery_requires_bbox_line(tmp)
        test_review_hash_binding(tmp)
        test_pdf_delivery_failure(tmp)
    print("safety regression cases passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
