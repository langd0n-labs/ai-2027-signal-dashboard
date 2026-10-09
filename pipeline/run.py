"""Classify every signal for one or more months and update data/signals.json.

    python pipeline/run.py                                  # the last complete month
    python pipeline/run.py --from 2026-04 --to 2026-09      # a range; months before the last complete month are marked backfill
    python pipeline/run.py --period 2026-09 --dry-run      # print the evidence, call no LLM, write nothing

Exit codes: 0 every signal classified; 3 incomplete: some signals failed to classify or had no
source data (the rest were written); 4 nothing was written because no source returned data. Any other non-zero code is a crash.
If RUN_SUMMARY is set, a Markdown summary of the run (including failed sources) is written there.
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
MAX_MONTHS = 12  # a typo like --from 2000-01 would otherwise be ~1,600 LLM calls
EXIT_PARTIAL, EXIT_NO_DATA = 3, 4


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


def summary(periods, written, failed_signals, failed_sources, no_data):
    lines = [f"Months: {periods[0]} to {periods[-1]}. Entries written: {written}."]
    if failed_signals:
        lines.append("\n**Signals that failed to classify:**")
        lines += [f"- {p} {s}: {err}" for p, s, err in failed_signals]
    if no_data:
        lines.append("\n**No reading (every source failed):**")
        lines += [f"- {p} {s}" for p, s in no_data]
    if failed_sources:
        lines.append("\n**Sources that failed or were skipped** (the signal was classified without them):")
        lines += [f"- {p} {s}: {', '.join(srcs)}" for (p, s), srcs in failed_sources.items()]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", type=month)
    ap.add_argument("--from", dest="start", type=month)
    ap.add_argument("--to", dest="end", type=month)
    ap.add_argument("--force", action="store_true", help=f"allow more than {MAX_MONTHS} months")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    latest = last_complete_month(datetime.now(timezone.utc))
    if args.period:
        periods = [args.period]
    else:
        start = args.start or args.end or latest
        periods = months(start, args.end or latest)
    if not periods or periods[-1] > latest:
        ap.error(f"periods must be complete months, the latest is {latest}")
    if len(periods) > MAX_MONTHS and not args.force:
        ap.error(f"{len(periods)} months requested; the limit is {MAX_MONTHS} without --force")

    config = load_config()
    signals, llm = config["signals"], config["llm"]
    new_entries, failed_signals, no_data, failed_sources = [], [], [], {}

    for period in periods:
        run = "backfill" if period < latest else "scheduled"
        evidence_out = {}
        for signal in signals:
            evidence = collect(signal, period)
            prompt = build_prompt(signal, period, evidence)
            evidence_out[signal["id"]] = prompt
            if args.dry_run:
                print(prompt, end="\n\n")
                continue
            failed = [part["source"] for part in evidence if part["status"] == "failed"]
            if len(failed) == len(evidence):
                no_data.append((period, signal["id"]))
                print(f"{period} {signal['id']}: every source failed; leaving it as no reading")
                continue
            if failed:
                failed_sources[(period, signal["id"])] = sorted(set(failed))
            try:
                result, served_by = classify(llm, prompt)
            except Exception as e:  # noqa: BLE001 - keep the other signals; reported in the exit code and summary
                failed_signals.append((period, signal["id"], f"{type(e).__name__}: {e}"))
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

    text = summary(periods, len(new_entries), failed_signals, failed_sources, no_data)
    print(text)
    if os.environ.get("RUN_SUMMARY"):
        Path(os.environ["RUN_SUMMARY"]).write_text(text + "\n")
    if not new_entries:
        return EXIT_NO_DATA
    return EXIT_PARTIAL if failed_signals or no_data else 0


if __name__ == "__main__":
    sys.exit(main())
