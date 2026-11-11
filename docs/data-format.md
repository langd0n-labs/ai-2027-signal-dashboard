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

# `data/weekly.json` format

The weekly developments (`pipeline/weekly.py`). A separate file, so a weekly run never touches the monthly readings. Each run replaces it with the latest complete week. The site shows it in its own section and handles the file being absent.

```json
{
  "schema": 1,
  "window": { "week": "2026-W43", "start": "2026-10-19", "end": "2026-10-25" },
  "comparison": { "week": "2026-W42", "start": "2026-10-12", "end": "2026-10-18" },
  "published": "2026-10-26T14:05:00Z",
  "provider": "anthropic",
  "model": "claude-opus-5",
  "signals": [
    {
      "id": "policy",
      "name": "Policy",
      "state": "developments",
      "developments": [{ "summary": "One sentence.", "sources": [{ "title": "...", "url": "https://..." }] }],
      "failed_sources": ["GDELT"]
    }
  ]
}
```

| Field | Meaning |
| --- | --- |
| `window` | The evidence window: one ISO week, Monday to Sunday, UTC. |
| `comparison` | The week before, which the evidence is compared with. |
| `published` | When the pipeline wrote the file (UTC). |
| `provider`, `model` | Which LLM wrote the summaries. |
| `signals[].state` | `developments`: at least one development. `none`: the sources worked and nothing notable happened. `no_data`: every source failed. `failed`: the sources worked but the summary could not be made. |
| `signals[].developments` | At most three. Each `sources` list is non-empty: the model cites links by number and the pipeline fills in the links, so every URL comes from a source on the allowed hosts. |
| `signals[].failed_sources` | Sources that failed this week. The summary was made without them. |

The evidence sent to the model for each week is in `data/evidence/YYYY-Www.json`. `check_data.py` checks this file too.
