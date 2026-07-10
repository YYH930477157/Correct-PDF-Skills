# Completeness Checks

## Canonicalization

Use `normalize_for_audit(text)` for diff/search only. Never replace raw source text with normalized text.

Required behavior:

- Unicode NFKC.
- Optional lowercase.
- Collapse whitespace.
- Normalize bullets.
- Normalize HTML entities.
- Normalize only line-end hyphenation: `word-\nword -> wordword`.
- Preserve semantic hyphenated terms such as `point-to-point` and `non-essential`.
- Remove only approved header/footer/page-number discard units from audit comparisons.

## Page Profiles

`detect_pdf_type.py` creates an initial page profile. Update after MinerU parsing with block/table/image/vector evidence.

Profiles:

- `text_page`
- `table_page`
- `scan_page`
- `toc_page`
- `figure_heavy_page`

## G Checks

G1 page coverage:

- Every source page has source units and output disposition.
- Empty pages require explicit `empty_or_noise` or review.

G2 text amount:

- Compare source inventory block text to repaired output text per page using token coverage.
- Coverage below the hard floor is `content_loss`.
- Coverage between hard floor and threshold is `needs_review`.
- Character ratio is retained as supporting evidence, not the hard decision metric.
- `source_pdf_audit.py` provides independent PyMuPDF text/image/vector evidence when the source PDF is available.
- OCR, when added by the operator, is audit evidence only; it must not overwrite content.
- `ocr_unavailable`, `ocr_low_confidence`, and `ocr_timeout` become `needs_review`.

G3 anchor audit:

- `required`: section numbers, table numbers, figure numbers, appendix identifiers. Missing required anchors produce `content_loss`.
- `candidate`: standard references, dates, numeric values, units, percentages, ranges. Missing candidate anchors produce `needs_review`.
- Candidate anchors filter short standard-prefix noise such as `UNI 5`, `EN 4`, or `ISO 9`. These are often line fragments or index artifacts, not meaningful completeness probes.
- `contextual`: random fixed-seed word shingles. Missing contextual anchors produce `needs_review`.
- `G3P`: when independent PyMuPDF source audit is supplied, required anchors present in the source PDF but absent from repaired output produce `content_loss`.
- Anchor comparisons must canonicalize whitespace and case before set comparison. Examples: `Table\n9`, `Table  9`, and `table 9` are the same anchor.
- Before emitting `content_loss`, re-check the canonical missing anchor against the repaired output audit text. This prevents parser/list-shape differences from becoming false loss reports.
- G3P findings should include source-page location evidence when available: anchor, page index, and a short source snippet. Missing content must be recoverable by a human reviewer without re-hunting through the whole PDF.

G4 figure/table audit:

- Count table blocks, figure blocks, captions, embedded images, and vector/drawing evidence.
- Uses table/figure/caption anchors and vector density as evidence, not a hard blocker by itself.
- Manifest F2 table/figure sequence gaps are cross-checked with independent source-PDF anchors when available. If every missing intermediate table/figure is absent from the source PDF audit, the gap is retained under `audits.sequence_gap_suppressed` and not emitted as `needs_review`; if any missing intermediate anchor exists in the source PDF, the F2 review remains.

G5 semantic sampling:

- Local deterministic sampling checks whether fixed source block samples are represented in output using normalized token coverage.
- Samples below the coverage floor emit `needs_review` with source page and sample metadata.
- Remote LLM review is optional and may add review findings or suggested operations, never direct text edits.

## Thresholds

- `text_page`: token coverage below `0.92` is reviewed; below the hard floor is `content_loss`.
- `table_page`: missing required table anchors is `content_loss`; text coverage is secondary.
- `toc_page`: missing TOC structural entries is `content_loss`.
- `scan_page`: source PDF audit reports text/image evidence; unavailable OCR means `needs_review` if text coverage is insufficient.
- `figure_heavy_page`: missing required captions is `content_loss`.

## Fail-Closed Details

- G1P consumes `source_pdf_audit.pages` so textless scan/image pages are not invisible to inventory-based G1.
- G4M uses significant image/drawing area evidence and emits one aggregated review item for pages without emitted media provenance.
- G2 never treats equal character counts as proof of semantic preservation.
- G5 samples are checked against only mapped output blocks. Text duplicated elsewhere cannot satisfy the sampled source unit.
- Recovery candidates without complete line bbox evidence remain evidence-only. Section lines additionally require heading-like typography; watermark and truncated-body candidates are rejected.
- Review decisions use stable review item IDs, exact refs, timestamps, and current inventory/manifest/source-PDF audit/source-PDF SHA-256 values.
