# Defect Rules

Every rule has `rule_id`, `risk`, `default_action`, status, and fixture coverage.

No negative fixture means no `auto_fix`.

## Implemented Deterministic Rules

| Rule | Risk | Default | Notes |
| --- | --- | --- | --- |
| A1 isolated section number merge | low | auto_fix | Merge left/aside section number with same-baseline heading. Requires positive and negative fixture. |
| A2 numbering jump | high | needs_review | Detect same-level section jumps. |
| A3 heading swallowed body | medium | needs_review | Detect title blocks containing requirement/body language. |
| A4 heading hyphen truncation | low | needs_review | Detect headings ending with a dangling hyphen. |
| A5 consecutive headings | medium | needs_review | Detect adjacent heading blocks without body between them. |
| B1 adjacent paragraph fragment join | medium | auto_fix | Join same-left, close vertical-gap fragments when first line lacks terminal punctuation and next starts lowercase. Requires positive and negative fixture. |
| B2 over-fragmented paragraph | medium | needs_review | Detect runs of very short paragraph blocks. |
| B3 cross-page paragraph | medium | needs_review | Detect unfinished bottom-of-page text continuing at the top of next page. |
| C1 footnote contamination | medium | needs_review | Detect footnote-like text near page footer. |
| C2 header/footer drift | medium | needs_review | Detect header/footer-like text at page edges. |
| C3 foreign-language contamination | high | needs_review | Detect likely foreign-language contamination. Defaults to an Italian lexicon for Italian-to-English standards; override with `PDF_LAYOUT_REPAIR_FOREIGN_TERMS` or `PDF_LAYOUT_REPAIR_FOREIGN_TERMS_FILE`. |
| C4 cross-column semantic pollution | high | needs_review | Detect same-baseline separated text blocks that may have been merged semantically. |
| D0 TOC three-column repair | low | auto_fix | Rebuild number/title/page table from coordinates or explicit `toc_*` dtypes. |
| D1 bullet normalization | low | auto_fix | Normalize bullet-like symbols to `- ` without changing content text. Requires positive and negative fixture. |
| D2 missing bullet | high | needs_review | Detect list blocks without a visible bullet or enumerator. |
| D3 table converted to prose | high | needs_review | Detect pipe/table-like text in non-table blocks. |
| D4 caption displacement | medium | needs_review | Detect captions near page edges where figure/table association is doubtful. |
| E1 explicit symbol repair | low | auto_fix | Apply only whitelisted or context-gated mappings such as corrupted less-than-or-equal symbols to `<=`; unknown symbols remain review items. Requires positive and negative fixture. |
| E2 unit inconsistency | high | needs_review | Detect unknown units after numbers. |
| E3 formula corruption | high | needs_review | Detect obvious formula/encoding corruption markers. |
| F1 section sequence integrity | high | needs_review | Report section sequence gaps. |
| F2 table/figure sequence | high | needs_review | Report table/figure sequence gaps. |
| F3 term definition order | medium | needs_review | Detect term-use/definition-order risks. |
| G1 page coverage | high | audit | Missing page content is content loss unless explicitly empty/noise. |
| G2 text amount | high | audit | Page token coverage below hard floor is content loss; review band becomes needs_review. |
| G3 anchors basic | high | audit | Required anchor missing is content loss. Candidate/contextual missing is review. G3P adds independent source-PDF required-anchor loss when available. |
| G4 figure/table basic | high | audit | Captions and table/figure blocks are audited. Vector density is supporting evidence. |
| G5 semantic sampling | high | audit | Local deterministic sampling runs by default; failures become needs_review. Optional LLM review may add findings but never invent content. |

## AI Patch Protocol

LLM output must be structured as `suggested_operations`.

Program must verify:

- referenced source units exist,
- bbox spaces are compatible,
- operation does not reduce coverage,
- affected audits rerun cleanly.
