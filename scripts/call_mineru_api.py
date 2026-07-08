#!/usr/bin/env python3
"""Call a configurable MinerU-compatible remote parsing API."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_kv(values: list[str]) -> dict[str, str]:
    parsed = {}
    for value in values:
        if "=" not in value:
            raise SystemExit(f"Expected KEY=VALUE, got: {value}")
        key, val = value.split("=", 1)
        parsed[key] = val
    return parsed


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Call a MinerU-compatible remote parsing API.")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=Path("mineru_response.json"))
    parser.add_argument("--metadata-output", type=Path, default=Path("mineru_request_metadata.json"))
    parser.add_argument("--endpoint", default=os.environ.get("MINERU_ENDPOINT", ""))
    parser.add_argument("--token-env", default="MINERU_TOKEN")
    parser.add_argument("--auth-header", default="Authorization")
    parser.add_argument("--auth-scheme", default="Bearer")
    parser.add_argument("--file-field", default="file")
    parser.add_argument("--param", action="append", default=[], help="Extra multipart field as KEY=VALUE.")
    parser.add_argument("--header", action="append", default=[], help="Extra HTTP header as KEY=VALUE.")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--allow-upload", action="store_true", help="Acknowledge that remote upload is allowed.")
    args = parser.parse_args()

    token = os.environ.get(args.token_env, "")
    metadata = {
        "input": str(args.pdf),
        "input_sha256": sha256(args.pdf),
        "api_endpoint": args.endpoint,
        "token_env": args.token_env if token else "",
        "allow_upload": args.allow_upload,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "prepared",
    }
    if not args.allow_upload:
        metadata.update({"status": "blocked", "reason": "remote upload not explicitly allowed"})
        write_json(args.metadata_output, metadata)
        print(args.metadata_output)
        return 2
    if not args.endpoint:
        metadata.update({"status": "blocked", "reason": "MINERU_ENDPOINT or --endpoint is required"})
        write_json(args.metadata_output, metadata)
        print(args.metadata_output)
        return 2
    if not token:
        metadata.update({"status": "blocked", "reason": f"{args.token_env} is not set"})
        write_json(args.metadata_output, metadata)
        print(args.metadata_output)
        return 2

    try:
        import requests
    except Exception as exc:  # pragma: no cover
        raise SystemExit(f"requests is required for remote API calls: {exc}")

    headers = parse_kv(args.header)
    headers[args.auth_header] = f"{args.auth_scheme} {token}".strip()
    fields = parse_kv(args.param)
    with args.pdf.open("rb") as handle:
        files = {args.file_field: (args.pdf.name, handle, "application/pdf")}
        response = requests.post(args.endpoint, headers=headers, data=fields, files=files, timeout=args.timeout)
    metadata.update({"status_code": response.status_code, "status": "completed" if response.ok else "failed"})
    write_json(args.metadata_output, metadata)
    try:
        payload = response.json()
    except ValueError:
        payload = {"raw_response": response.text}
    write_json(args.output, payload if isinstance(payload, dict) else {"response": payload})
    if not response.ok:
        raise SystemExit(f"MinerU API request failed with HTTP {response.status_code}; see {args.output}")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
