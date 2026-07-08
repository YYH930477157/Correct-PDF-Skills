#!/usr/bin/env python3
"""Render repaired blocks to a clean HTML document."""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any


SECTION_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)\s+(.+)")


def block_html(block: dict[str, Any]) -> str:
    text = block.get("raw_text", "")
    escaped = html.escape(text)
    operation = block.get("operation", "emit")
    if operation == "TOC_three_column_repair":
        parts = text.rsplit(" ", 1)
        title = parts[0]
        page = parts[1] if len(parts) == 2 else ""
        return f'<div class="toc-row"><span>{html.escape(title)}</span><span>{html.escape(page)}</span></div>'
    if text.startswith("- "):
        return f"<li>{html.escape(text[2:].strip())}</li>"
    match = SECTION_RE.match(text)
    if match:
        level = min(match.group(1).count(".") + 1, 4)
        return f"<h{level}>{escaped}</h{level}>"
    return f"<p>{escaped}</p>"


def main() -> int:
    parser = argparse.ArgumentParser(description="Render repaired_blocks.json to HTML.")
    parser.add_argument("repaired_blocks", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=Path("repaired.html"))
    parser.add_argument("--title", default="Repaired PDF")
    args = parser.parse_args()
    data = json.loads(args.repaired_blocks.read_text(encoding="utf-8-sig"))
    body = "\n".join(block_html(block) for block in data.get("output_blocks", []))
    doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{html.escape(args.title)}</title>
  <style>
    @page {{ margin: 24mm 20mm; }}
    body {{ font-family: Arial, sans-serif; color: #111; line-height: 1.42; font-size: 10.5pt; }}
    h1, h2, h3, h4 {{ page-break-after: avoid; margin: 1.2em 0 0.45em; line-height: 1.2; }}
    h1 {{ font-size: 17pt; }}
    h2 {{ font-size: 14pt; }}
    h3 {{ font-size: 12pt; }}
    h4 {{ font-size: 11pt; }}
    p {{ margin: 0 0 0.72em; orphans: 2; widows: 2; }}
    li {{ margin: 0 0 0.35em 1.2em; }}
    .toc-row {{ display: grid; grid-template-columns: 1fr auto; gap: 12mm; margin: 0 0 0.25em; }}
    .toc-row span:first-child::after {{ content: ""; border-bottom: 1px dotted #999; display: inline-block; width: 100%; transform: translateY(-0.25em); }}
    table {{ border-collapse: collapse; width: 100%; margin: 0.8em 0; }}
    th, td {{ border: 1px solid #999; padding: 4px 6px; vertical-align: top; }}
  </style>
</head>
<body>
{body}
</body>
</html>
"""
    args.output.write_text(doc, encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
