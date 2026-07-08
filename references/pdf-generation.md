# PDF Generation

PDF generation consumes structured Markdown/JSON only. It must not repair content.

Preferred:

- Use `document-skills:pdf` or available report/PDF skill with ReportLab/report brief.

Fallback:

- Render print-friendly HTML.
- Use Chrome/Edge headless print to PDF.
- Run `post_render_audit.py` afterward.

Renderer failures:

- Fix renderer or layout CSS.
- Do not reparse the source PDF as a rendering workaround.

Final/draft/review status must be visible in:

- PDF first page,
- report header,
- output filename.
