# PDF Generation

PDF generation consumes `repaired_blocks.json`. It must not repair or invent content.

Built-in path:

```bash
python scripts/run_pipeline.py source.json -o out
```

Outputs:

- `repaired.html` is always created.
- Table blocks that contain complete `<table>...</table>` HTML are preserved as table markup; unsafe or partial tags are escaped as text.
- `repaired.pdf` is created only when a headless Chrome-compatible binary is available and `--no-pdf` is not set.
- `post_render_audit.json` must be generated after HTML/PDF output.

Preferred external handoff:

- If a document/PDF skill is available, pass `repaired_blocks.json`, `repair_manifest.json`, `completeness_report.json`, and source metadata.
- The external generator must preserve section anchors, table/figure captions, lists, tables, and paragraph order.
- Run `post_render_audit.py` against the final PDF afterward.

Renderer failures:

- Fix renderer or layout CSS.
- Do not reparse the source PDF as a rendering workaround.
- Missing anchors after render are `post_render_loss`.
