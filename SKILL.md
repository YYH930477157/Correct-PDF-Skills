---
name: pdf-layout-repair
description: Use when repairing malformed PDF extraction, validating PDF-to-Markdown/PDF conversions, or auditing document parsing for silent content loss.
---

# PDF Layout Repair

## Core Laws

This skill does not guarantee zero loss. It guarantees no silent loss: every source content unit (`page`, `block`, `text`) must be `emitted`, `merged`, `discarded`, or `escalated`, and auditable in `repair_manifest.json`.

No final artifact may be delivered unless `source_inventory.json`, `repair_manifest.json`, `completeness_report.json`, and `post_render_audit.json` all exist and agree on document status.

Priority order:

1. Make the inventory, manifest, audit, and report chain reliable.
2. Repair only defects with tested rules.
3. Rules without negative fixtures must output `suggest_patch` or `needs_review`, never `auto_fix`.

## Workflow

Use `scripts/run_pipeline.py` for the normal path. Run individual scripts only when debugging.

1. Preflight the PDF with `scripts/detect_pdf_type.py` when the source PDF is available.
2. Parse with MinerU remote API using `scripts/call_mineru_api.py`, or use existing MinerU JSON/Markdown artifacts.
3. Run `scripts/run_pipeline.py INPUT -o OUTDIR`; add `--source-pdf SOURCE.pdf` for independent PyMuPDF source audit.
4. Inspect the four-piece audit set and `pipeline_summary.json`.
5. Deliver `final` only if both quality gates pass. Otherwise deliver `draft` or `review`.

## Quality Gates

Pre-render:

- `content_loss` present: no final PDF. Produce review artifacts.
- `needs_review` present without content loss: draft PDF allowed.
- all checks clear: final candidate allowed.

Post-render:

- `post_render_loss` present: final is invalid; downgrade to review.
- Missing four-piece audit set: no final.
- Status mismatch between reports: no final.

Manual override may downgrade noise but cannot promote directly to `final`. To produce `final`, all hard gates must be rerun and pass.

## MVP Scope

Implemented in the first pass:

- A1 isolated section-number merge.
- A2 section number jump detection.
- A3 heading/body contamination detection.
- B1 adjacent paragraph-fragment join.
- C3 foreign-language contamination detection.
- D0 TOC three-column row rebuild.
- D1 bullet normalization.
- D3 table-like text in paragraph detection.
- E1 explicit symbol corruption repair.
- E2 suspicious unit detection.
- E3 formula/encoding corruption detection.
- F1 section sequence gap detection.
- F2 table/figure sequence gap detection.
- G1 page coverage.
- G2 page text amount audit.
- G3 required/candidate anchor audit.
- G4 figure/table/caption audit.
- G5 AI semantic sampling placeholder; API intentionally blank.
- H provenance, raw/audit text separation, bbox space fields.
- I post-render anchor audit for PDF/HTML/text and PDF bbox clipping audit.
- J privacy/token/logging constraints.

Everything else must be reported as `needs_review`, `suggest_patch`, or an explicit not-configured placeholder.

## Rule Classes

| Class | Scope | MVP |
| --- | --- | --- |
| A | Structural defects: section numbers, headings, title/body splits | A1 auto; A2/A3 review; A4/A5 suggest/review |
| B | Paragraph joins and cross-page paragraph repair | B1 implemented; B2-B3 review/suggest |
| C | Content contamination: footnotes, headers, foreign-language/cross-column pollution | C3 review; C1/C2/C4 review when detected |
| D | Lists, bullets, tables, captions | D0/D1 auto; D3 review; D2/D4 review/suggest |
| E | Encoding, symbols, units, formulas | E1 auto; E2/E3 review |
| F | Sequence integrity for sections, tables, figures, terms | F1/F2 review; F3 review when detected |
| G | Completeness audit | G1-G4 implemented; G5 placeholder |
| H | Provenance | MVP |
| I | Post-render audit | Anchor and PDF bbox clipping audit |
| J | Privacy/copyright and remote API safety | MVP |

## References

Read only what is needed:

- `references/mineru-api-guide.md`: MinerU remote API, token, version metadata.
- `references/provenance-model.md`: `source_inventory.json`, `repair_manifest.json`, `raw_text`/`audit_text`, bbox spaces, discard whitelist.
- `references/completeness-check.md`: G-class audits, page profiles, anchors, canonicalization, OCR failure policy.
- `references/defect-rules.md`: A-J rule definitions and implemented/not-configured status.
- `references/confidence-policy.md`: quality gates, status calculation, thresholds, override policy.
- `references/pdf-generation.md`: PDF generation handoff and HTML/Chrome fallback.
- `references/local-deploy.md`: local MinerU/PyMuPDF4LLM/Tesseract upgrade path.
- `references/llm-review-protocol.md`: AI/LLM semantic review contract; API fields are intentionally blank.

## Privacy Rules

- Do not upload sensitive PDFs automatically.
- If local parsing is unavailable for a sensitive document, ask the user or abort.
- Read MinerU tokens from environment variables only.
- Do not log full document text.
- Clean temporary files unless the user asks to keep artifacts.
