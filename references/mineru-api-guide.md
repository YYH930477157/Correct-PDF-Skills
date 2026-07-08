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
