# LLM Review Protocol

LLM integration is optional and intentionally unconfigured by default.

Environment placeholders:

- `PDF_LAYOUT_REPAIR_LLM_PROVIDER`
- `PDF_LAYOUT_REPAIR_LLM_ENDPOINT`
- `PDF_LAYOUT_REPAIR_LLM_API_KEY`
- `PDF_LAYOUT_REPAIR_LLM_MODEL`

Rules:

- Never send source text to a remote LLM unless the user has approved remote processing.
- LLM output must be structured JSON with `suggested_operations`.
- Suggested operations may reference existing `source_refs` only.
- The program must verify every referenced source unit exists.
- LLM suggestions can become `suggest_patch` or `needs_review`; they do not become `auto_fixed` until deterministic checks pass.
- LLMs must not invent missing source content. If content appears missing, report `content_loss` or `needs_review`.

Suggested operation shape:

```json
{
  "rule_id": "G5",
  "action": "suggest_patch",
  "source_refs": ["mineru:p4:para_blocks2"],
  "reason": "output paragraph appears split mid-sentence",
  "proposed_text": "..."
}
```

When no API is configured, G5 falls back to local deterministic semantic sampling. Remote LLM review is optional and must never be the only completeness signal.
