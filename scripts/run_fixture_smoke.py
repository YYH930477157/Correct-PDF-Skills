#!/usr/bin/env python3
"""Run fixture smoke tests for pdf-layout-repair."""

from __future__ import annotations

import argparse
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Run pdf-layout-repair fixture smoke tests.")
    parser.add_argument("--keep", action="store_true", help="Keep temporary artifacts and print their path.")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="pdf-layout-repair-fixtures-") as tmp_name:
        tmp = Path(tmp_name)
        for child in ("a1-positive", "a1-negative", "general-repair"):
            (tmp / child).mkdir(parents=True, exist_ok=True)
        test_a1_positive(tmp)
        test_a1_negative(tmp)
        test_missing_anchor(tmp)
        test_general_repairs(tmp)
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
