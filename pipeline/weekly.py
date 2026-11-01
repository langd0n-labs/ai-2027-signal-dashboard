"""Summarize material developments for every signal over the last complete ISO week and write data/weekly.json.

    python pipeline/weekly.py                         # the last complete week (Monday to Sunday, UTC)
    python pipeline/weekly.py --week 2026-W43         # a given week
    python pipeline/weekly.py --week 2026-W43 --dry-run   # print the prompts, call no LLM, write nothing

The weekly update sits beside the monthly readings: it never touches data/signals.json. It uses only
sources that can be queried for a single week (see collect() in fetch_sources.py), and compares each
week with the week before.

Exit codes as in run.py: 0 every signal summarized; 3 incomplete (the rest were written); 4 nothing
was written. If RUN_SUMMARY is set, a Markdown summary goes there.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from classify_signals import classify
from fetch_sources import bounds, collect, prev_period
from run import EXIT_NO_DATA, EXIT_PARTIAL, EVIDENCE, ROOT, load_config

WEEKLY = ROOT / "data" / "weekly.json"
MAX_DEVELOPMENTS = 3
MAX_SUMMARY = 400  # characters; the prompt asks for at most 250
STATES = ("developments", "none", "no_data", "failed")

SCHEMA = {
    "type": "object",
    "properties": {
        "developments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "sources": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["summary", "sources"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["developments"],
    "additionalProperties": False,
}

SYSTEM = f"""You write the weekly developments note for a public dashboard that tracks whether the world is moving toward the "AI 2027" scenario (Kokotajlo et al., AI Futures Project, 2025).

You get the evidence for one signal for one week (Monday to Sunday) and the week before. The dashboard's monthly readings are made separately; you do not classify the signal.

Rules:
- Report at most {MAX_DEVELOPMENTS} developments in this week that matter for the signal as defined. Return an empty list if nothing does; a quiet week is a valid answer.
- Use only the evidence provided. Do not use anything you know about events after the week.
- Counts of stories, papers and documents, and news tone, reflect attention, not outcomes. Report a change from the week before only if it is large.
- Some sources may be marked unavailable. Do not guess what they would have shown.
- summary: one plain sentence, at most 250 characters, that a general reader can follow.
- sources: the numbers of the links below that support the development. At least one. Cite only links that support it directly."""


def week(value):
    """'2026-W43' -> itself, if it names a real ISO week."""
    m = re.fullmatch(r"(\d{4})-W(\d{2})", value or "")
    try:
        if m:
            datetime.fromisocalendar(int(m[1]), int(m[2]), 1)
            return value
    except ValueError:
        pass
    raise argparse.ArgumentTypeError(f"expected an ISO week like 2026-W43, got {value!r}")


def last_complete_week(today):
    year, num, _ = (today - timedelta(days=today.isoweekday())).isocalendar()
    return f"{year}-W{num:02d}"


def window(period):
    start, end = bounds(period)
    return {"week": period, "start": start.isoformat(), "end": end.isoformat()}


def build_prompt(signal, period, evidence, links):
    w, c = window(period), window(prev_period(period))
    lines = [
        f"Signal: {signal['name']}",
        f"Week: {w['start']} to {w['end']}. The week before: {c['start']} to {c['end']}.",
        f"Accelerating means: {signal['accelerating']}",
        f"Stabilizing means: {signal['stabilizing']}",
        "",
        "Evidence:",
    ]
    for part in evidence:
        lines += part["lines"]
    lines += ["", "Links you can cite:"]
    lines += [f"[{i}] {link['title']}" for i, link in enumerate(links, 1)]
    return "\n".join(lines)


def checker(links):
    """Check the model's answer and swap its link numbers for the pipeline's own links."""

    def check(result):
        devs = result.get("developments")
        if not isinstance(devs, list) or len(devs) > MAX_DEVELOPMENTS:
            raise ValueError(f"expected at most {MAX_DEVELOPMENTS} developments")
        out = []
        for d in devs:
            summary, nums = d.get("summary"), d.get("sources")
            if not isinstance(summary, str) or not summary.strip() or len(summary) > MAX_SUMMARY:
                raise ValueError(f"summary empty or longer than {MAX_SUMMARY} characters")
            if not nums or not isinstance(nums, list) or any(type(n) is not int or not 1 <= n <= len(links) for n in nums):
                raise ValueError(f"bad source numbers {nums!r}")
            out.append({"summary": summary.strip(), "sources": [links[n - 1] for n in dict.fromkeys(nums)]})
        return out

    return check


def summary(doc):
    lines = [f"Week: {doc['window']['start']} to {doc['window']['end']}."]
    for s in doc["signals"]:
        line = f"- {s['name']}: {s['state']}"
        if s["developments"]:
            line += f" ({len(s['developments'])})"
        if s["failed_sources"]:
            line += f"; sources that failed: {', '.join(s['failed_sources'])}"
        lines.append(line)
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=week)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    latest = last_complete_week(datetime.now(timezone.utc).date())
    period = args.week or latest
    if bounds(period)[1] > bounds(latest)[1]:
        ap.error(f"the week must be complete, the latest is {latest}")

    config = load_config()
    llm = config["llm"]
    signals, evidence_out, model = [], {}, None
    for signal in config["signals"]:
        evidence = collect(signal, period)
        links = list({link["url"]: link for part in evidence for link in part["links"]}.values())
        prompt = build_prompt(signal, period, evidence, links)
        if args.dry_run:
            print(prompt, end="\n\n")
            continue
        failed = sorted({part["source"] for part in evidence if part["status"] == "failed"})
        row = {"id": signal["id"], "name": signal["name"], "state": "no_data", "developments": [], "failed_sources": failed}
        signals.append(row)
        if len(failed) == len({part["source"] for part in evidence}):
            print(f"{signal['id']}: every source failed")
            continue
        try:
            row["developments"], model = classify(llm, prompt, SYSTEM, SCHEMA, checker(links))
        except Exception as e:  # noqa: BLE001 - keep the other signals; shown on the site and in the exit code
            row["state"] = "failed"
            print(f"{signal['id']}: FAILED {type(e).__name__}: {e}", file=sys.stderr)
            continue
        row["state"] = "developments" if row["developments"] else "none"
        evidence_out[signal["id"]] = prompt
        print(f"{signal['id']}: {len(row['developments'])} development(s)")

    if args.dry_run:
        return 0
    doc = {
        "schema": 1,
        "window": window(period),
        "comparison": window(prev_period(period)),
        "published": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "provider": llm["provider"],
        "model": model or llm["model"],
        "signals": signals,
    }
    text = summary(doc)
    print(text)
    if os.environ.get("RUN_SUMMARY"):
        Path(os.environ["RUN_SUMMARY"]).write_text(text + "\n")
    if not evidence_out:
        return EXIT_NO_DATA
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / f"{period}.json").write_text(json.dumps(evidence_out, indent=2, ensure_ascii=False) + "\n")
    WEEKLY.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    return EXIT_PARTIAL if any(s["state"] in ("no_data", "failed") for s in signals) else 0


if __name__ == "__main__":
    sys.exit(main())
