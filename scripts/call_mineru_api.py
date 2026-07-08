#!/usr/bin/env python3
"""Call a configurable MinerU-compatible remote parsing API."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
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


def api_json(response: Any) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {"raw_response": response.text}
    return payload if isinstance(payload, dict) else {"response": payload}


def require_ok(response: Any, payload: dict[str, Any], label: str) -> None:
    if not response.ok or payload.get("code", 0) not in (0, "0"):
        raise SystemExit(f"{label} failed with HTTP {response.status_code}: {payload.get('msg') or payload}")


def mineru_v4_local_batch(args: argparse.Namespace, headers: dict[str, str], requests: Any, metadata: dict[str, Any]) -> dict[str, Any]:
    base_url = args.base_url.rstrip("/")
    data_id = args.data_id or sha256(args.pdf)[:16]
    submit_body: dict[str, Any] = {
        "files": [{"name": args.pdf.name, "data_id": data_id}],
        "model_version": args.model_version,
        "enable_formula": not args.disable_formula,
        "enable_table": not args.disable_table,
    }
    if args.language:
        submit_body["language"] = args.language
    if args.is_ocr:
        submit_body["is_ocr"] = True
    if args.extra_format:
        submit_body["extra_formats"] = args.extra_format
    submit_body.update(parse_kv(args.param))

    upload_endpoint = f"{base_url}/api/v4/file-urls/batch"
    submit_response = requests.post(upload_endpoint, headers=headers, json=submit_body, timeout=args.timeout)
    submit_payload = api_json(submit_response)
    require_ok(submit_response, submit_payload, "MinerU v4 file-url request")

    data = submit_payload.get("data", {})
    batch_id = data.get("batch_id")
    file_urls = data.get("file_urls") or []
    if not batch_id or not file_urls:
        raise SystemExit(f"MinerU v4 file-url response missing batch_id/file_urls: {submit_payload}")

    with args.pdf.open("rb") as handle:
        upload_response = requests.put(file_urls[0], data=handle, timeout=args.timeout)
    if not upload_response.ok:
        raise SystemExit(f"MinerU v4 upload failed with HTTP {upload_response.status_code}: {upload_response.text[:500]}")

    metadata.update({"batch_id": batch_id, "upload_endpoint": upload_endpoint, "result_endpoint": f"{base_url}/api/v4/extract-results/batch/{batch_id}"})
    result_endpoint = metadata["result_endpoint"]
    last_payload: dict[str, Any] = {}
    for poll_index in range(args.max_polls):
        result_response = requests.get(result_endpoint, headers=headers, timeout=args.timeout)
        last_payload = api_json(result_response)
        require_ok(result_response, last_payload, "MinerU v4 result poll")
        results = last_payload.get("data", {}).get("extract_result", [])
        states = {item.get("state") for item in results if isinstance(item, dict)}
        metadata["poll_count"] = poll_index + 1
        metadata["states"] = sorted(state for state in states if state)
        if states and states.issubset({"done", "failed"}):
            return last_payload
        if poll_index < args.max_polls - 1:
            time.sleep(args.poll_interval)
    metadata["status"] = "timeout"
    return last_payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Call a MinerU-compatible remote parsing API.")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=Path("mineru_response.json"))
    parser.add_argument("--metadata-output", type=Path, default=Path("mineru_request_metadata.json"))
    parser.add_argument("--mode", choices=["multipart", "mineru-v4-local"], default="multipart")
    parser.add_argument("--base-url", default=os.environ.get("MINERU_BASE_URL", "https://mineru.net"))
    parser.add_argument("--endpoint", default=os.environ.get("MINERU_ENDPOINT", ""))
    parser.add_argument("--token-env", default="MINERU_TOKEN")
    parser.add_argument("--auth-header", default="Authorization")
    parser.add_argument("--auth-scheme", default="Bearer")
    parser.add_argument("--file-field", default="file")
    parser.add_argument("--model-version", default="vlm")
    parser.add_argument("--language", default="")
    parser.add_argument("--is-ocr", action="store_true")
    parser.add_argument("--disable-formula", action="store_true")
    parser.add_argument("--disable-table", action="store_true")
    parser.add_argument("--extra-format", action="append", default=[])
    parser.add_argument("--data-id", default="")
    parser.add_argument("--poll-interval", type=int, default=10)
    parser.add_argument("--max-polls", type=int, default=60)
    parser.add_argument("--param", action="append", default=[], help="Extra multipart field as KEY=VALUE.")
    parser.add_argument("--header", action="append", default=[], help="Extra HTTP header as KEY=VALUE.")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--allow-upload", action="store_true", help="Acknowledge that remote upload is allowed.")
    args = parser.parse_args()

    token = os.environ.get(args.token_env, "")
    metadata = {
        "input": str(args.pdf),
        "input_sha256": sha256(args.pdf),
        "mode": args.mode,
        "api_endpoint": args.endpoint if args.mode == "multipart" else args.base_url,
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
    if args.mode == "multipart" and not args.endpoint:
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
    if args.mode == "mineru-v4-local":
        headers.setdefault("Content-Type", "application/json")
        payload = mineru_v4_local_batch(args, headers, requests, metadata)
        metadata.update({"status": "completed" if metadata.get("status") != "timeout" else "timeout"})
        write_json(args.metadata_output, metadata)
        write_json(args.output, payload)
        print(args.output)
        return 0 if metadata["status"] == "completed" else 3

    fields = parse_kv(args.param)
    with args.pdf.open("rb") as handle:
        files = {args.file_field: (args.pdf.name, handle, "application/pdf")}
        response = requests.post(args.endpoint, headers=headers, data=fields, files=files, timeout=args.timeout)
    metadata.update({"status_code": response.status_code, "status": "completed" if response.ok else "failed"})
    write_json(args.metadata_output, metadata)
    payload = api_json(response)
    write_json(args.output, payload if isinstance(payload, dict) else {"response": payload})
    if not response.ok:
        raise SystemExit(f"MinerU API request failed with HTTP {response.status_code}; see {args.output}")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
