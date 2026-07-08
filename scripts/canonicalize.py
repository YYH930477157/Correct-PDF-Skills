#!/usr/bin/env python3
"""Audit-text canonicalization for pdf-layout-repair."""

from __future__ import annotations

import argparse
import html
import re
import sys
import unicodedata


BULLET_LIKE = ("\u2022", "\u25aa", "\u25cf", "\u2212", "\u2010", "\u2011", "\u2012", "\u2013", "\u2014")


def normalize_for_audit(text: str, *, lowercase: bool = True) -> str:
    """Return an audit-only normalized view. Do not use this as output text."""
    text = html.unescape(text or "")
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"([A-Za-z])-\n([A-Za-z])", r"\1\2", text)
    text = text.replace("\n", " ")
    for bullet in BULLET_LIKE:
        text = text.replace(bullet, "-")
    text = re.sub(r"\s+", " ", text).strip()
    return text.lower() if lowercase else text


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize text for audit comparisons.")
    parser.add_argument("text", nargs="*", help="Text to normalize. Reads stdin if omitted.")
    parser.add_argument("--keep-case", action="store_true", help="Do not lowercase output.")
    args = parser.parse_args()
    text = " ".join(args.text) if args.text else sys.stdin.read()
    print(normalize_for_audit(text, lowercase=not args.keep_case))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
