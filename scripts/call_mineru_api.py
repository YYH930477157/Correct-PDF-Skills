#!/usr/bin/env python3
"""Minimal MinerU API wrapper placeholder.

The MVP supports metadata capture and refuses to upload without explicit inputs.
Extend this script with the current MinerU endpoint details before production use.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare MinerU API metadata and optionally call remote parsing.")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=Path("mineru_request_metadata.json"))
    parser.add_argument("--endpoint", default="https://mineru.net/api/v4")
    parser.add_argument("--model-version", default="vlm")
    parser.add_argument("--allow-upload", action="store_true", help="Acknowledge that remote upload is allowed.")
    args = parser.parse_args()

    token_present = bool(os.environ.get("MINERU_TOKEN"))
    metadata = {
        "input": str(args.pdf),
        "input_sha256": sha256(args.pdf),
        "api_endpoint": args.endpoint,
        "model_version": args.model_version,
        "token_env": "MINERU_TOKEN" if token_present else "",
        "allow_upload": args.allow_upload,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "prepared",
    }
    if not args.allow_upload:
        metadata["status"] = "blocked"
        metadata["reason"] = "remote upload not explicitly allowed"
    elif not token_present:
        metadata["status"] = "blocked"
        metadata["reason"] = "MINERU_TOKEN is not set"
    else:
        metadata["status"] = "ready_for_api_integration"
        metadata["reason"] = "endpoint-specific upload implementation is intentionally not hardcoded in MVP"
    args.output.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
