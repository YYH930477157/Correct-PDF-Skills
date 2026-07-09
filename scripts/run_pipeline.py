#!/usr/bin/env python3
"""Run the pdf-layout-repair pipeline end to end."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def run(*args: str) -> None:
    subprocess.run([sys.executable, *args], check=True)


def html_to_pdf(html_path: Path, pdf_path: Path) -> dict[str, str]:
    candidates = [
        shutil.which("chrome"),
        shutil.which("chrome.exe"),
        shutil.which("msedge"),
        shutil.which("msedge.exe"),
        str(Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Google" / "Chrome" / "Application" / "chrome.exe"),
        str(Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Google" / "Chrome" / "Application" / "chrome.exe"),
        str(Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Microsoft" / "Edge" / "Application" / "msedge.exe"),
        str(Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft" / "Edge" / "Application" / "msedge.exe"),
    ]
    chrome = next((candidate for candidate in candidates if candidate and Path(candidate).exists()), None)
    if not chrome:
        return {"status": "skipped", "reason": "headless_chrome_not_found", "artifact": str(html_path)}
    subprocess.run(
        [chrome, "--headless=new", "--disable-gpu", f"--print-to-pdf={pdf_path}", str(html_path)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return {"status": "created", "artifact": str(pdf_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run PDF layout repair pipeline.")
    parser.add_argument("input", type=Path, help="MinerU JSON or source_inventory.json")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("pdf-layout-repair-output"))
    parser.add_argument("--input-kind", choices=["mineru-json", "inventory"], default="mineru-json")
    parser.add_argument("--title", default="Repaired PDF")
    parser.add_argument("--no-pdf", action="store_true", help="Render HTML only.")
    parser.add_argument("--source-pdf", type=Path, help="Optional original PDF for independent preflight/source audit.")
    parser.add_argument("--recover-source-pdf-anchors", action="store_true", help="Recover missing required anchors from source_pdf_audit snippets and mark them needs_review.")
    parser.add_argument("--review-decisions", type=Path, help="Optional audited review decision JSON for resolving matched needs_review findings.")
    args = parser.parse_args()

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    inventory = out / "source_inventory.json"
    repaired = out / "repaired_blocks.json"
    manifest = out / "repair_manifest.json"
    completeness = out / "completeness_report.json"
    html = out / "repaired.html"
    pdf = out / "repaired.pdf"
    rendered_artifact = html
    post = out / "post_render_audit.json"
    report = out / "repair_report.md"
    preflight = out / "pdf_preflight.json"
    source_audit = out / "source_pdf_audit.json"
    recovered_inventory = out / "source_inventory_recovered.json"

    optional_artifacts: dict[str, str | None] = {"pdf_preflight": None, "source_pdf_audit": None}
    if args.source_pdf:
        run(str(SCRIPTS / "detect_pdf_type.py"), str(args.source_pdf), "-o", str(preflight))
        run(str(SCRIPTS / "source_pdf_audit.py"), str(args.source_pdf), "-o", str(source_audit))
        optional_artifacts["pdf_preflight"] = str(preflight)
        optional_artifacts["source_pdf_audit"] = str(source_audit)

    if args.input_kind == "inventory":
        inventory.write_text(args.input.read_text(encoding="utf-8-sig"), encoding="utf-8")
    else:
        run(str(SCRIPTS / "build_inventory.py"), str(args.input), "-o", str(inventory))
    active_inventory = inventory
    if args.recover_source_pdf_anchors:
        if not args.source_pdf:
            raise SystemExit("--recover-source-pdf-anchors requires --source-pdf")
        run(str(SCRIPTS / "recover_source_pdf_anchors.py"), str(inventory), str(source_audit), "-o", str(recovered_inventory))
        active_inventory = recovered_inventory

    run(str(SCRIPTS / "apply_repairs.py"), str(active_inventory), "-o", str(repaired))
    run(str(SCRIPTS / "build_manifest.py"), str(active_inventory), str(repaired), "-o", str(manifest))
    completeness_args = [str(SCRIPTS / "completeness_audit.py"), str(active_inventory), str(manifest), "-o", str(completeness)]
    if args.source_pdf:
        completeness_args.extend(["--source-pdf-audit", str(source_audit)])
    if args.review_decisions:
        completeness_args.extend(["--review-decisions", str(args.review_decisions)])
    run(*completeness_args)
    run(str(SCRIPTS / "render_html.py"), str(repaired), "-o", str(html), "--title", args.title)

    pdf_generation = {"status": "skipped", "reason": "no_pdf_requested", "artifact": str(html)}
    if not args.no_pdf:
        pdf_generation = html_to_pdf(html.resolve(), pdf)
        if pdf_generation["status"] == "created":
            rendered_artifact = pdf

    run(str(SCRIPTS / "post_render_audit.py"), str(rendered_artifact), str(completeness), "-o", str(post))
    run(str(SCRIPTS / "render_report.py"), str(completeness), str(post), "-o", str(report))

    summary = {
        "schema_version": "0.1",
        "output_dir": str(out),
        "artifacts": {
            "source_inventory": str(inventory),
            "active_source_inventory": str(active_inventory),
            "source_inventory_recovered": str(recovered_inventory) if recovered_inventory.exists() else None,
            "repair_manifest": str(manifest),
            "completeness_report": str(completeness),
            "post_render_audit": str(post),
            "repair_report": str(report),
            "html": str(html),
            "pdf": str(pdf) if pdf.exists() else None,
            "review_decisions": str(args.review_decisions) if args.review_decisions else None,
            **optional_artifacts,
        },
        "pdf_generation": pdf_generation,
        "llm_api": {"status": "not_configured", "reason": "left blank intentionally"},
    }
    (out / "pipeline_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out / "pipeline_summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
