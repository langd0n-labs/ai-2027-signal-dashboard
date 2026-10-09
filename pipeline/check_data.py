"""Check data/signals.json against docs/data-format.md. This is the required check on data PRs.

    python pipeline/check_data.py [path]      # exit 0 if valid, 1 with a list of problems if not
"""

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

from classify_signals import MAX_JUSTIFICATION, STATUSES
from fetch_sources import ALLOWED_HOSTS

PERIOD = re.compile(r"\d{4}-(0[1-9]|1[0-2])")
ENTRY_KEYS = {"signal", "period", "status", "justification", "confidence", "sources", "provider", "model", "run", "classified_at"}


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
            url = link.get("url", "")
            if urlsplit(url).scheme != "https" or urlsplit(url).hostname not in ALLOWED_HOSTS:
                out.append(f"{where}: source link not on an allowed host: {url!r}")
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    path = Path(argv[0]) if argv else Path(__file__).resolve().parent.parent / "data" / "signals.json"
    try:
        doc = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        print(f"cannot read {path}: {e}")
        return 1
    found = problems(doc)
    for p in found:
        print(p)
    print(f"{path}: {'OK' if not found else f'{len(found)} problem(s)'}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
