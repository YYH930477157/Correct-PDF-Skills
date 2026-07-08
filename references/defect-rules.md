# Defect Rules

Every rule has `rule_id`, `risk`, `default_action`, `phase`, and fixture coverage.

No negative fixture means no `auto_fix`.

## MVP

| Rule | Risk | Default | Notes |
| --- | --- | --- | --- |
| A1 isolated section number merge | low | auto_fix | Merge left/aside section number with same-baseline heading. Requires positive and negative fixture. |
| A2 numbering jump | high | needs_review | Detect same-level section jumps. |
| A3 heading swallowed body | medium | needs_review | Detect title blocks containing requirement/body language. |
| B1 adjacent paragraph fragment join | medium | auto_fix | Join same-left, close vertical-gap fragments when first line lacks terminal punctuation and next starts lowercase. |
| C3 foreign-language contamination | high | needs_review | Detect likely Italian contamination in translated English documents. |
| D0 TOC three-column repair | low | auto_fix | Rebuild number/title/page table from coordinates or explicit `toc_*` dtypes. |
| D1 bullet normalization | low | auto_fix | Normalize bullet-like symbols to `- ` without changing content text. |
| D3 table converted to prose | high | needs_review | Detect pipe/table-like text in non-table blocks. |
| E1 explicit symbol repair | low | auto_fix | Apply only whitelisted mappings such as `ŷ -> <=`; unknown symbols remain review items. |
| E2 unit inconsistency | high | needs_review | Detect unknown units after numbers. |
| E3 formula corruption | high | needs_review | Detect obvious formula/encoding corruption markers. |
| F1 section sequence integrity | high | needs_review | Report section sequence gaps. |
| F2 table/figure sequence | high | needs_review | Report table/figure sequence gaps. |
| G1 page coverage | high | audit | Missing page content is content loss unless explicitly empty/noise. |
| G2 text amount | high | audit | Page character coverage below threshold is content loss. |
| G3 anchors basic | high | audit | Required anchor missing is content loss. Candidate/contextual missing is review. |
| G4 figure/table basic | high | audit | Captions and table/figure blocks are audited. Vector density is evidence in MVP. |
| G5 semantic sampling | high | needs_review | Placeholder until an LLM API is configured; never invents content. |

## Review/Suggest Rules Without Auto-Fix

| Rule | Risk | Default |
| --- | --- | --- |
| A4 heading hyphen truncation | low | auto_fix after negative fixture |
| A5 consecutive headings | medium | suggest_patch |
| B2 over-fragmented paragraph | medium | suggest_patch |
| B3 cross-page paragraph | medium | suggest_patch |
| C1 footnote contamination | medium | suggest_patch |
| C2 header/footer drift | medium | suggest_patch |
| C4 cross-column semantic pollution | high | needs_review |
| D2 missing bullet | high | needs_review |
| D4 caption displacement | medium | suggest_patch |
| F3 term definition order | medium | needs_review |

## AI Patch Protocol

LLM output must be structured as `suggested_operations`.

Program must verify:

- referenced source units exist,
- bbox spaces are compatible,
- operation does not reduce coverage,
- affected audits rerun cleanly.
