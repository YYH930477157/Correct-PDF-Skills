# MinerU API Guide

Use MinerU remote API when local deployment is unavailable and the document is not sensitive.

Required metadata to record in provenance:

- `input_sha256`
- `api_endpoint`
- `mineru_version`
- `model_version`
- request options
- timestamp
- response task id

Token rules:

- Read token from `MINERU_TOKEN`.
- Never write token into artifacts.
- Never log full document text.

If document sensitivity is unknown, ask before upload.

Two API modes are supported.

Generic multipart mode for self-hosted MinerU-compatible services:

```bash
set MINERU_TOKEN=...
python scripts/call_mineru_api.py source.pdf --mode multipart --endpoint https://... --allow-upload -o mineru_response.json
```

mineru.net cloud local-file mode:

```bash
set MINERU_TOKEN=...
python scripts/call_mineru_api.py source.pdf --mode mineru-v4-local --allow-upload -o mineru_response.json
```

`mineru-v4-local` follows the official v4 batch upload pattern: request a signed upload URL, upload the PDF with PUT, then poll the batch extraction result.

The wrapper supports:

- `--mode multipart|mineru-v4-local`,
- `--base-url` for the mineru.net-compatible host,
- `--model-version`,
- `--language`,
- `--is-ocr`,
- `--file-field` for multipart file field name,
- `--param KEY=VALUE` for extra form fields,
- `--header KEY=VALUE` for extra headers,
- `--token-env` when the token environment variable is not `MINERU_TOKEN`.

It never writes the token to output artifacts.
