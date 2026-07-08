# Correct PDF Skills

`pdf-layout-repair` is a Codex skill for repairing malformed PDF extraction output and auditing whether content was silently lost during PDF to Markdown/HTML/PDF conversion.

The core promise is intentionally conservative:

- It does not promise fully automatic zero-loss repair.
- It does promise that suspected loss, risky layout defects, and unverified semantic checks are surfaced in audit artifacts instead of being hidden.

## What It Does

The skill turns MinerU JSON or an existing source inventory into:

- repaired structured blocks,
- a provenance manifest,
- completeness and post-render audits,
- a human-readable report,
- print-friendly HTML,
- optional PDF output when Chrome or Edge headless printing is available.

It is designed for standards/specification documents with dense numbering, tables, figures, definitions, and cross references.

## Quick Start

Run with an existing MinerU JSON file:

```powershell
python scripts\run_pipeline.py "MinerU_output.json" -o out --title "Repaired PDF"
```

Run with the original PDF as independent audit evidence:

```powershell
python scripts\run_pipeline.py "MinerU_output.json" -o out --source-pdf "source.pdf" --title "Repaired PDF"
```

Generate HTML only:

```powershell
python scripts\run_pipeline.py "MinerU_output.json" -o out --no-pdf
```

Use an already-built source inventory:

```powershell
python scripts\run_pipeline.py "source_inventory.json" --input-kind inventory -o out
```

Customize foreign-language contamination terms:

```powershell
$env:PDF_LAYOUT_REPAIR_FOREIGN_TERMS = "le,les,des,etre,configuration"
python scripts\run_pipeline.py "MinerU_output.json" -o out
```

## Output Artifacts

The pipeline writes:

- `source_inventory.json`: source units with IDs, text, bbox, page, and audit text.
- `repaired_blocks.json`: emitted, merged, or normalized output blocks.
- `repair_manifest.json`: every source unit disposition and provenance mapping.
- `completeness_report.json`: G-class source-vs-output completeness audit.
- `post_render_audit.json`: rendered artifact audit, including required anchors and PDF bbox clipping when applicable.
- `repair_report.md`: readable defect/completeness summary.
- `repaired.html`: print-friendly repaired document.
- `repaired.pdf`: optional, if a headless Chrome-compatible browser is available.
- `pdf_preflight.json`: optional source PDF page profile when `--source-pdf` is used.
- `source_pdf_audit.json`: optional independent PyMuPDF source evidence when `--source-pdf` is used.
- `pipeline_summary.json`: paths and high-level execution status.

## Rule Coverage

Automatic low-risk repairs:

- A1 isolated section number merge.
- B1 adjacent paragraph-fragment join.
- D0 TOC three-column row rebuild.
- D1 bullet normalization.
- E1 explicit symbol repair using a whitelist.

Deterministic review detection:

- A2-A5 structural risks.
- B2-B3 paragraph fragmentation/cross-page risks.
- C1-C4 contamination and cross-column risks.
- D2-D4 list/table/caption risks.
- E2-E3 unit/formula/encoding risks.
- F1-F3 sequence and term-order risks.

Completeness and render audits:

- G1 page coverage.
- G2 page token coverage with a review band before hard `content_loss`.
- G3 required and candidate anchors.
- G3P independent PyMuPDF source PDF anchors when `--source-pdf` is used.
- G4 figure/table/caption anchors.
- I post-render anchor audit and PDF bbox clipping audit.

LLM semantic sampling:

- G5 is intentionally left unconfigured.
- When no LLM API is configured, G5 emits `needs_review`.
- See `references/llm-review-protocol.md` before connecting any model.

## MinerU Remote API

Two remote modes are available. The default `multipart` mode is for self-hosted MinerU-compatible services:

```powershell
$env:MINERU_TOKEN = "..."
python scripts\call_mineru_api.py "source.pdf" --endpoint "https://..." --allow-upload -o mineru_response.json
```

For mineru.net cloud local-file parsing, use the official v4 batch upload flow:

```powershell
$env:MINERU_TOKEN = "..."
python scripts\call_mineru_api.py "source.pdf" --mode mineru-v4-local --allow-upload -o mineru_response.json
```

Useful options:

- `--mode multipart|mineru-v4-local`
- `--base-url https://mineru.net`
- `--model-version vlm|pipeline`
- `--language en`
- `--is-ocr`
- `--file-field FIELD`
- `--param KEY=VALUE`
- `--header KEY=VALUE`
- `--token-env ENV_NAME`

Tokens are read from environment variables and are not written to artifacts.

## Validation

Run fixture smoke tests:

```powershell
python scripts\run_fixture_smoke.py
```

Validate skill structure:

```powershell
python C:\Users\YunHeYang\.codex\skills\.system\skill-creator\scripts\quick_validate.py C:\Users\YunHeYang\.codex\skills\pdf-layout-repair
```

Compile scripts:

```powershell
Get-ChildItem -LiteralPath scripts -Filter *.py | ForEach-Object { python -m py_compile $_.FullName }
```

## Status Semantics

- `final`: no content loss, no post-render loss, no unresolved review findings.
- `draft`: no detected loss, but review items remain.
- `review`: content loss or post-render loss was detected.
- `post_render_audit.json` also includes `render_status`; this isolates renderer loss from upstream parser loss.

Manual review may downgrade noisy findings, but final output should be produced only after hard gates are rerun and pass.

## Privacy

- Do not upload sensitive PDFs unless the user explicitly approves remote processing.
- Prefer local parsing/audit for sensitive documents.
- Do not log full document text or API tokens.
- Treat LLM output as suggestions only; never allow it to invent missing source content.
