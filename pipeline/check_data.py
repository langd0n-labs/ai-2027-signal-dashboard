"""Check data/signals.json and data/weekly.json against docs/data-format.md. This is the required check on data PRs.

    python pipeline/check_data.py [path]      # exit 0 if valid, 1 with a list of problems if not
                                              # no path: signals.json, and weekly.json if it exists
"""

import json
import re
import sys
from pathlib import Path
from datetime import date
from urllib.parse import urlsplit

from classify_signals import MAX_JUSTIFICATION, STATUSES
from fetch_sources import ALLOWED_HOSTS

PERIOD = re.compile(r"\d{4}-(0[1-9]|1[0-2])")
ENTRY_KEYS = {"signal", "period", "status", "justification", "confidence", "sources", "provider", "model", "run", "classified_at"}


def bad_link(link):
    url = link.get("url", "") if isinstance(link, dict) else ""
    return urlsplit(url).scheme != "https" or urlsplit(url).hostname not in ALLOWED_HOSTS


def problems(doc):
    out = []
    if doc.get("schema") != 1:
        out.append(f"schema is {doc.get('schema')!r}, expected 1")
    if doc.get("sample") is not False:
        out.append("sample must be false for pipeline output")
    if doc.get("period") != "month":
        out.append("period must be 'month'")
    signal_ids = {s.get("id") for s in doc.get("signals", [])}
    if not signal_ids:
        out.append("no signals")
    entries = doc.get("entries", [])
    if not entries:
        out.append("no entries: the run produced nothing")
    seen = set()
    for i, e in enumerate(entries):
        where = f"entries[{i}]"
        missing = ENTRY_KEYS - e.keys()
        if missing:
            out.append(f"{where}: missing {sorted(missing)}")
            continue
        if e["signal"] not in signal_ids:
            out.append(f"{where}: unknown signal {e['signal']!r}")
        if not isinstance(e["period"], str) or not PERIOD.fullmatch(e["period"]):
            out.append(f"{where}: bad period {e['period']!r}")
        if (e["signal"], e["period"]) in seen:
            out.append(f"{where}: duplicate {e['signal']} {e['period']}")
        seen.add((e["signal"], e["period"]))
        if e["status"] not in STATUSES:
            out.append(f"{where}: bad status {e['status']!r}")
        if e["confidence"] not in (1, 2, 3, 4, 5):
            out.append(f"{where}: bad confidence {e['confidence']!r}")
        if not isinstance(e["justification"], str) or not e["justification"].strip() or len(e["justification"]) > MAX_JUSTIFICATION:
            out.append(f"{where}: justification empty or longer than {MAX_JUSTIFICATION} characters")
        if e["run"] not in ("backfill", "scheduled"):
            out.append(f"{where}: bad run {e['run']!r}")
        for link in e["sources"]:
            if bad_link(link):
                out.append(f"{where}: source link not on an allowed host: {link.get('url', '')!r}")
    return out


def weekly_problems(doc):
    out = []
    if doc.get("schema") != 1:
        out.append(f"schema is {doc.get('schema')!r}, expected 1")
    weeks = []
    for key in ("window", "comparison"):
        w = doc.get(key) or {}
        try:
            start, end = date.fromisoformat(w["start"]), date.fromisoformat(w["end"])
            year, num, day = start.isocalendar()
            if day != 1 or (end - start).days != 6 or w["week"] != f"{year}-W{num:02d}":
                raise ValueError
            weeks.append(start)
        except (KeyError, TypeError, ValueError):
            out.append(f"{key} is not one ISO week, Monday to Sunday: {w!r}")
    if len(weeks) == 2 and (weeks[0] - weeks[1]).days != 7:
        out.append("comparison is not the week before the window")
    if not isinstance(doc.get("published"), str):
        out.append("no published date")
    signals = doc.get("signals") or []
    if not signals:
        out.append("no signals")
    for i, s in enumerate(signals):
        where = f"signals[{i}]"
        devs = s.get("developments")
        if s.get("state") not in ("developments", "none", "no_data", "failed") or not isinstance(devs, list):
            out.append(f"{where}: bad state {s.get('state')!r} or no developments list")
            continue
        if (s["state"] == "developments") != bool(devs):
            out.append(f"{where}: state {s['state']!r} does not match {len(devs)} development(s)")
        if not isinstance(s.get("failed_sources"), list):
            out.append(f"{where}: failed_sources must be a list")
        for j, d in enumerate(devs):
            if not isinstance(d.get("summary"), str) or not d["summary"].strip():
                out.append(f"{where}.developments[{j}]: empty summary")
            if not d.get("sources") or any(bad_link(link) for link in d["sources"]):
                out.append(f"{where}.developments[{j}]: no sources, or a source link not on an allowed host")
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    data = Path(__file__).resolve().parent.parent / "data"
    paths = [Path(argv[0])] if argv else [data / "signals.json"] + [p for p in [data / "weekly.json"] if p.exists()]
    failed = False
    for path in paths:
        try:
            doc = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as e:
            print(f"cannot read {path}: {e}")
            failed = True
            continue
        found = (weekly_problems if path.name == "weekly.json" else problems)(doc)
        for p in found:
            print(p)
        print(f"{path}: {'OK' if not found else f'{len(found)} problem(s)'}")
        failed |= bool(found)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
