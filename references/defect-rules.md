# Defect Rules

Every rule has `rule_id`, `risk`, `default_action`, `phase`, and fixture coverage.

No negative fixture means no `auto_fix`.

## MVP

| Rule | Risk | Default | Notes |
| --- | --- | --- | --- |
| A1 isolated section number merge | low | auto_fix | Merge left/aside section number with same-baseline heading. Requires positive and negative fixture. |
| B1 adjacent paragraph fragment join | medium | auto_fix | Join same-left, close vertical-gap fragments when first line lacks terminal punctuation and next starts lowercase. |
| D0 TOC three-column repair | low | auto_fix | Rebuild number/title/page table from coordinates or explicit `toc_*` dtypes. |
| D1 bullet normalization | low | auto_fix | Normalize bullet-like symbols to `- ` without changing content text. |
| E1 explicit symbol repair | low | auto_fix | Apply only whitelisted mappings such as `ŷ -> <=`; unknown symbols remain review items. |
| G1 page coverage | high | audit | Missing page content is content loss unless explicitly empty/noise. |
| G2 text amount | high | audit | Page character coverage below threshold is content loss. |
| G3 anchors basic | high | audit | Required anchor missing is content loss. Candidate/contextual missing is review. |
| G4 figure/table basic | high | audit | Captions and table/figure blocks are audited. Vector density is evidence in MVP. |
| G5 semantic sampling | high | needs_review | Placeholder until an LLM API is configured; never invents content. |

## Phase 2

| Rule | Risk | Default |
| --- | --- | --- |
| A2 numbering jump | high | needs_review |
| A3 heading swallowed body | medium | suggest_patch |
| A4 heading hyphen truncation | low | auto_fix after negative fixture |
| A5 consecutive headings | medium | suggest_patch |
| B2 over-fragmented paragraph | medium | suggest_patch |
| B3 cross-page paragraph | medium | suggest_patch |
| C1 footnote contamination | medium | suggest_patch |
| C2 header/footer drift | medium | suggest_patch |
| C3 foreign-language contamination | high | needs_review |
| C4 cross-column semantic pollution | high | needs_review |
| D2 missing bullet | high | needs_review |
| D3 table converted to prose | high | needs_review |
| D4 caption displacement | medium | suggest_patch |
| E1 special-symbol corruption | low | auto_fix with explicit mapping |
| E2 unit inconsistency | high | needs_review |
| E3 formula corruption | high | needs_review |
| F1 section sequence integrity | high | needs_review |
| F2 table/figure sequence | high | needs_review |
| F3 term definition order | medium | needs_review |

## AI Patch Protocol

LLM output must be structured as `suggested_operations`.

Program must verify:

- referenced source units exist,
- bbox spaces are compatible,
- operation does not reduce coverage,
- affected audits rerun cleanly.
