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

Generic API call:

```bash
set MINERU_TOKEN=...
python scripts/call_mineru_api.py source.pdf --endpoint https://... --allow-upload -o mineru_response.json
```

The wrapper supports:

- `--file-field` for multipart file field name,
- `--param KEY=VALUE` for extra form fields,
- `--header KEY=VALUE` for extra headers,
- `--token-env` when the token environment variable is not `MINERU_TOKEN`.

It never writes the token to output artifacts.
