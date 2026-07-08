# Confidence Policy

## Status

Statuses:

- `final`: all hard gates pass, no content loss, no applicable needs-review findings.
- `draft`: no content loss, but applicable `needs_review` remains.
- `review`: content loss, post-render loss, missing artifacts, status mismatch, or sensitive-upload uncertainty.

## Hard Gates

Pre-render gate:

- `content_loss` present: no final.
- Missing `source_inventory.json` or `repair_manifest.json`: no final.
- Unmapped source units excluding approved discards: `content_loss`.

Post-render gate:

- Missing `post_render_audit.json`: no final.
- Missing required anchors in generated PDF: `post_render_loss`.
- Rendered status disagreement with completeness report: no final.

## Not Implemented

`not_implemented` becomes `needs_review` only when the rule applies to the current document. If the rule does not apply, mark `not_applicable`.

## Manual Override

Override can resolve false positives for draft output. Final output still requires all hard gates to pass after rerun.

## Artifact Rule

No final artifact may be emitted unless these exist and agree:

- `source_inventory.json`
- `repair_manifest.json`
- `completeness_report.json`
- `post_render_audit.json`
