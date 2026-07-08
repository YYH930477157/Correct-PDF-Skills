# Local Deployment

Use local deployment when documents are sensitive or remote upload is disallowed.

Options:

- MinerU local deployment when hardware permits.
- PyMuPDF4LLM for lightweight fallback.
- Tesseract/pytesseract for OCR audit evidence.

If local capability is insufficient for a sensitive document:

- abort,
- ask for explicit upload approval,
- or run a degraded local parser and mark `needs_review`.
