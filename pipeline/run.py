"""Classify every signal for one or more months and update data/signals.json.

    python pipeline/run.py                                  # the last complete month
    python pipeline/run.py --from 2026-04 --to 2026-09 --backfill
    python pipeline/run.py --period 2026-09 --dry-run      # print the evidence, call no LLM, write nothing
"""

import argparse
import json
import os
import re
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from classify_signals import build_prompt, classify
from fetch_sources import collect, prev_month

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "signals.json"
EVIDENCE = ROOT / "data" / "evidence"
MAX_LINKS = 6


def load_config():
    with open(Path(__file__).with_name("config.toml"), "rb") as f:
        config = tomllib.load(f)
    llm = config["llm"]
    for key in ("provider", "model", "effort"):
        llm[key] = os.environ.get(f"SIGNALS_LLM_{key.upper()}") or llm[key]
    return config


def month(value):
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value or ""):
        raise argparse.ArgumentTypeError(f"expected YYYY-MM, got {value!r}")
    return value


def months(start, end):
    out, p = [], end
    while p >= start:
        out.append(p)
        p = prev_month(p)
    return out[::-1]


def last_complete_month(today):
    return prev_month(f"{today.year}-{today.month:02d}")


def merge(doc, new_entries, signals, now):
    """Replace entries with the same (signal, period); drop sample entries once real data arrives."""
    old = [] if doc.get("sample") else doc.get("entries", [])
    keys = {(e["signal"], e["period"]) for e in new_entries}
    order = {s["id"]: i for i, s in enumerate(signals)}
    entries = [e for e in old if (e["signal"], e["period"]) not in keys] + new_entries
    entries.sort(key=lambda e: (e["period"], order.get(e["signal"], 99)))
    return {
        "schema": 1,
        "updated": now,
        "sample": False,
        "period": "month",
        "overall": doc.get("overall"),
        "signals": [{k: s[k] for k in ("id", "name", "accelerating", "stabilizing")} for s in signals],
        "entries": entries,
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", type=month)
    ap.add_argument("--from", dest="start", type=month)
    ap.add_argument("--to", dest="end", type=month)
    ap.add_argument("--backfill", action="store_true", help="mark entries as backfilled, not scheduled")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    default = last_complete_month(datetime.now(timezone.utc))
    if args.period:
        periods = [args.period]
    else:
        start = args.start or args.end or default
        periods = months(start, args.end or default)
    if not periods or periods[-1] > default:
        ap.error(f"periods must be complete months, the latest is {default}")

    config = load_config()
    signals, llm = config["signals"], config["llm"]
    run = "backfill" if args.backfill else "scheduled"
    new_entries, failures = [], 0

    for period in periods:
        evidence_out = {}
        for signal in signals:
            evidence = collect(signal, period)
            prompt = build_prompt(signal, period, evidence)
            evidence_out[signal["id"]] = prompt
            if args.dry_run:
                print(prompt, end="\n\n")
                continue
            if not any(part["links"] for part in evidence):
                print(f"{period} {signal['id']}: no source returned data; leaving it as no reading")
                continue
            try:
                result, served_by = classify(llm, prompt)
            except Exception as e:  # noqa: BLE001 - keep the other signals; the run exits non-zero below
                failures += 1
                print(f"{period} {signal['id']}: FAILED {type(e).__name__}: {e}", file=sys.stderr)
                continue
            links = [link for part in evidence for link in part["links"]][:MAX_LINKS]
            new_entries.append({
                "signal": signal["id"],
                "period": period,
                **result,
                "sources": links,
                "provider": llm["provider"],
                "model": served_by,
                "run": run,
                "classified_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            })
            print(f"{period} {signal['id']}: {result['status']} ({result['confidence']}/5)")
        if not args.dry_run:
            EVIDENCE.mkdir(parents=True, exist_ok=True)
            (EVIDENCE / f"{period}.json").write_text(json.dumps(evidence_out, indent=2, ensure_ascii=False) + "\n")

    if args.dry_run:
        return 0
    if new_entries:
        doc = json.loads(DATA.read_text()) if DATA.exists() else {}
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        DATA.write_text(json.dumps(merge(doc, new_entries, signals, now), indent=2, ensure_ascii=False) + "\n")
    print(f"{len(new_entries)} entries written, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
