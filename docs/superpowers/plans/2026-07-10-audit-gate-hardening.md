# PDF Audit Gate Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Close every review finding that can silently approve lost, substituted, polluted, stale, or undelivered PDF content.

**Architecture:** Keep the existing linear pipeline, but make every promotion to `final` fail closed. Independent PDF evidence participates in page/media gates, content sampling is source-ref-local, recovery emits only complete bbox-backed structural lines, review decisions bind to current artifact hashes and review item IDs, and requested PDF delivery must actually produce and audit a PDF.

**Tech Stack:** Python 3 standard library, PyMuPDF, existing fixture smoke runner.

---

### Task 1: Add failing safety regressions

**Files:**
- Modify: `scripts/run_fixture_smoke.py`

- [x] Add tests for scan/image-only page loss, partial G3R approval, same-length substitution, zero/mislocalized G5 sampling, unsafe snippet recovery, stale decision hashes, and unavailable PDF rendering.
- [x] Run `python scripts/run_fixture_smoke.py` and verify the new tests fail for the expected unsafe behavior.

### Task 2: Harden completeness checks

**Files:**
- Modify: `scripts/completeness_audit.py`
- Modify: `scripts/source_pdf_audit.py`

- [x] Add source-PDF page/media evidence checks and prevent image-only pages from reaching `final` without output evidence.
- [x] Remove character-count-only G2 suppression.
- [x] Compare G5 samples only with output blocks mapped from the sampled source unit; make unexpected zero samples reviewable.
- [x] Run the targeted fixture tests until they pass.

### Task 3: Make recovery evidence-only unless structurally complete

**Files:**
- Modify: `scripts/source_pdf_audit.py`
- Modify: `scripts/recover_source_pdf_anchors.py`
- Modify: `scripts/apply_repairs.py`

- [x] Capture line text and bbox around anchors from PyMuPDF structured text.
- [x] Recover only complete structural lines with real bbox evidence; retain unsafe snippets as non-emitted evidence.
- [x] Ensure recovered title/caption text does not contain truncated prose, watermarks, or table-body tails.
- [x] Run recovery fixtures and real-output structural checks.

### Task 4: Bind review decisions to exact findings and artifacts

**Files:**
- Modify: `scripts/completeness_audit.py`
- Modify: `scripts/run_pipeline.py`
- Modify: `scripts/run_fixture_smoke.py`

- [x] Give each review item a stable ID and require exact source/unit refs.
- [x] Require inventory, manifest, and optional source-PDF SHA-256 values plus a review timestamp.
- [x] Reject stale or partial decisions and record rejection reasons.
- [x] Run positive and negative decision fixtures.

### Task 5: Enforce requested PDF delivery

**Files:**
- Modify: `scripts/run_pipeline.py`
- Modify: `scripts/post_render_audit.py`
- Modify: `scripts/run_fixture_smoke.py`

- [x] Return a non-zero pipeline result when PDF was requested but not generated.
- [x] Distinguish HTML-only audit from successful PDF delivery in `pipeline_summary.json`.
- [x] Include final document/render/delivery status in the summary.
- [x] Run delivery-state fixtures.

### Task 6: Update the skill contract and verify

**Files:**
- Modify: `README.md`
- Modify: `SKILL.md`
- Modify: `references/completeness-check.md`
- Modify: `references/provenance-model.md`
