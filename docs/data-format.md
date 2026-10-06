# `data/signals.json` format

The pipeline writes this file and the site reads it. Change the format only in a pull request that also updates the site (see `OPS.md`).

```json
{
  "schema": 1,
  "updated": "2026-10-05T12:00:00Z",
  "sample": false,
  "period": "month",
  "overall": null,
  "signals": [
    { "id": "policy", "name": "Policy", "accelerating": "...", "stabilizing": "..." }
  ],
  "entries": [
    {
      "signal": "policy",
      "period": "2026-09",
      "status": "accelerating",
      "justification": "One or two sentences.",
      "confidence": 4,
      "sources": [{ "title": "...", "url": "https://..." }],
      "provider": "anthropic",
      "model": "claude-opus-5",
      "run": "scheduled",
      "classified_at": "2026-10-05T12:00:00Z"
    }
  ]
}
```

| Field | Meaning |
| --- | --- |
| `schema` | Format version. Increase it when a change would break the site. |
| `updated` | When the pipeline last wrote the file (UTC). |
| `sample` | `true` while the file holds hand-written sample data. The site shows a banner. The first real run removes all sample entries. |
| `period` | Length of one period. Only `"month"` is used. |
| `overall` | The overall reading. `null` until its definition is decided. |
| `signals` | The signals and their definitions, copied from `pipeline/config.toml` on every run. |
| `entries[].period` | The month classified, `YYYY-MM`. A signal can have no entry for a month: the site shows "no reading". |
| `entries[].status` | `accelerating`, `stabilizing` or `unclear`. |
| `entries[].confidence` | 1 (a guess) to 5 (strong, consistent evidence). |
| `entries[].sources` | Links to the evidence the model saw, chosen by the pipeline, not by the model. |
| `entries[].provider`, `model` | Which LLM classified the entry. `model` is the model that served the request. |
| `entries[].run` | `backfill` for months classified after the fact, `scheduled` for the monthly run. |

The full evidence sent to the model for each month is in `data/evidence/YYYY-MM.json`.
