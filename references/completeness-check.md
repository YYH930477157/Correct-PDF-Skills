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
- `contextual`: random fixed-seed word shingles. Missing contextual anchors produce `needs_review`.
- `G3P`: when independent PyMuPDF source audit is supplied, required anchors present in the source PDF but absent from repaired output produce `content_loss`.

G4 figure/table audit:

- Count table blocks, figure blocks, captions, embedded images, and vector/drawing evidence.
- Uses table/figure/caption anchors and vector density as evidence, not a hard blocker by itself.

G5 semantic sampling:

- Fixed-seed AI sampling checks whether source paragraphs are represented in output.
- AI returns review findings or suggested operations, never direct text edits.
- Until an LLM API is configured, G5 outputs `needs_review` with `not_configured`.

## Thresholds

- `text_page`: token coverage below `0.92` is reviewed; below the hard floor is `content_loss`.
- `table_page`: missing required table anchors is `content_loss`; text coverage is secondary.
- `toc_page`: missing TOC structural entries is `content_loss`.
- `scan_page`: source PDF audit reports text/image evidence; unavailable OCR means `needs_review` if text coverage is insufficient.
- `figure_heavy_page`: missing required captions is `content_loss`.
