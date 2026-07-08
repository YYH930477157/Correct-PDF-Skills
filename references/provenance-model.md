# Provenance Model

## Files

`source_inventory.json` records source evidence before repair.

`repair_manifest.json` records how source units map to output blocks after repair.

Always keep both `raw_text` and `audit_text`. `raw_text` is never normalized in place. `audit_text` is produced by `normalize_for_audit()` and used for diff/search/audit only.

The MVP inventory is MinerU-primary. Multi-engine fields are retained so later engines can attach evidence without changing schema, but PyMuPDF evidence currently enters the quality gate through `source_pdf_audit.json` and the G3P independent-anchor audit rather than full block-level dedupe.

## Source Unit

```json
{
  "unit_id": "mineru:p5:b15",
  "canonical_unit_id": "cu:sha256...",
  "engine_unit_id": "p5:b15",
  "dedupe_group_id": "dg:sha256...",
  "primary_engine": "mineru",
  "supporting_evidence": ["pymupdf:p5:line42"],
  "granularity": "page|block|text",
  "page": 5,
  "dtype": "title|paragraph|table|figure|discarded|anchor|shingle",
  "raw_text": "3.3 APP",
  "audit_text": "3.3 app",
  "bbox": [133, 537, 153, 548],
  "bbox_space": "pdf_points|image_pixels|mineru_normalized",
  "page_width": 595,
  "page_height": 842,
  "scale": 1.0,
  "metadata": {}
}
```

## Output Block

```json
{
  "output_id": "out:p6:sec3_3",
  "source_refs": ["mineru:p5:b15", "mineru:p5:discarded3"],
  "operation": "merge_section_number",
  "confidence": 0.94,
  "disposition": "merged",
  "raw_text": "3.3 APP",
  "audit_text": "3.3 app"
}
```

## Dispositions

Every source unit must end as one of:

- `emitted`: output unchanged or represented directly.
- `merged`: output represented through another block.
- `discarded`: ignored for an approved reason.
- `escalated`: requires review.

Approved automatic discard reasons:

- `repeated_header`
- `repeated_footer`
- `page_number`
- `duplicate_overlay_text`
- `watermark`
- `empty_or_noise`

Any other discard reason is `needs_review`.

## Override Record

```json
{
  "override_id": "ovr:...",
  "rule_id": "G3",
  "reviewer": "user",
  "decision": "accepted_false_positive",
  "reason": "anchor only appears in original table of contents",
  "timestamp": "2026-07-08T00:00:00Z"
}
```

Override can move `review` to `draft`. It cannot create `final`; hard gates must rerun and pass.
