#!/usr/bin/env python3
"""Validate the pdf-layout-repair regression case library."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
SMOKE = ROOT / "scripts" / "run_fixture_smoke.py"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def validate_case_library(path: Path) -> list[str]:
    data = read_json(path)
    errors: list[str] = []
    if data.get("schema_version") != "0.1":
        errors.append("schema_version must be 0.1")
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        errors.append("cases must be a non-empty list")
        return errors
    smoke_text = SMOKE.read_text(encoding="utf-8-sig")
    seen: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            errors.append(f"case[{index}] must be an object")
            continue
        case_id = case.get("id")
        if not case_id:
            errors.append(f"case[{index}] missing id")
        elif case_id in seen:
            errors.append(f"duplicate case id: {case_id}")
        else:
            seen.add(case_id)
        for field in ("defect_class", "source", "expected", "covered_by"):
            if not case.get(field):
                errors.append(f"{case_id or f'case[{index}]'} missing {field}")
        covered_by = str(case.get("covered_by", ""))
        if "::" in covered_by:
            test_name = covered_by.rsplit("::", 1)[-1]
            if f"def {test_name}(" not in smoke_text:
                errors.append(f"{case_id} references missing smoke test {test_name}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate pdf-layout-repair regression cases.")
    parser.add_argument("--cases", type=Path, default=FIXTURES / "regression-cases.json")
    parser.add_argument("--run-smoke", action="store_true", help="Run fixture smoke tests after validating the case library.")
    args = parser.parse_args()
    errors = validate_case_library(args.cases)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"validated {len(read_json(args.cases).get('cases', []))} regression cases")
    if args.run_smoke:
        subprocess.run([sys.executable, str(SMOKE)], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
