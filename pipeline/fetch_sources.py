"""Collect evidence for one signal and one month from public sources that accept past dates.

Every fetcher returns a dict: {"source", "lines", "links"}. "lines" is plain text for the model,
"links" is [{"title", "url"}] shown on the site. A failed source returns an "unavailable" line
instead of raising, so one outage does not stop the run.
"""

import calendar
import csv
import io
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from functools import lru_cache

USER_AGENT = "ai-2027-signal-dashboard (+https://github.com/langd0n-labs/ai-2027-signal-dashboard)"


def month_bounds(period):
    """'2026-04' -> (date(2026, 4, 1), date(2026, 4, 30))."""
    year, month = map(int, period.split("-"))
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def prev_month(period):
    year, month = map(int, period.split("-"))
    return f"{year - 1}-12" if month == 1 else f"{year}-{month - 1:02d}"


def get(url, retries=4, wait=10):
    """GET with backoff on 429 and 5xx. GDELT throttles hard, so waits grow quickly."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=90) as resp:
                body = resp.read().decode("utf-8")
            # GDELT answers a throttled request with HTTP 200 and a plain-text notice.
            if body.startswith("Please limit requests"):
                raise urllib.error.HTTPError(url, 429, "throttled", None, None)
            return body
        except urllib.error.HTTPError as e:
            if e.code != 429 and e.code < 500 or attempt == retries - 1:
                raise
        except urllib.error.URLError:
            if attempt == retries - 1:
                raise
        time.sleep(wait * 2**attempt)


def safe(source, fn, *args):
    try:
        return fn(*args)
    except Exception as e:  # noqa: BLE001 - one source failing must not stop the others
        return {"source": source, "lines": [f"{source}: unavailable for this period ({type(e).__name__})."], "links": []}


@lru_cache(maxsize=None)
def _fred_rows(sid):
    return list(csv.reader(io.StringIO(get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"))))[1:]


def fred(series, period):
    """Last 13 observations on or before the end of the month, so the model sees the trend."""
    _, end = month_bounds(period)
    sid = series["id"]
    obs = [(d, v) for d, v in _fred_rows(sid) if d <= end.isoformat() and v not in ("", ".")][-13:]
    if not obs:
        return {"source": "FRED", "lines": [f"FRED {sid}: no observations by {end}."], "links": []}
    series_text = ", ".join(f"{d}: {v}" for d, v in obs)
    url = f"https://fred.stlouisfed.org/series/{sid}"
    return {
        "source": "FRED",
        "lines": [f"FRED {sid}, {series['name']}. Observations by date: {series_text}"],
        "links": [{"title": f"FRED: {series['name']}", "url": url}],
    }


def federal_register(term, period):
    """Count of Federal Register documents matching the term this month vs last month, plus top titles."""

    def query(p, per_page):
        start, end = month_bounds(p)
        params = {
            "conditions[term]": term,
            "conditions[publication_date][gte]": start.isoformat(),
            "conditions[publication_date][lte]": end.isoformat(),
            "order": "relevance",
            "per_page": per_page,
            "fields[]": ["title", "html_url", "type", "agencies"],
        }
        return json.loads(get("https://www.federalregister.gov/api/v1/documents.json?" + urllib.parse.urlencode(params, doseq=True)))

    now, before = query(period, 8), query(prev_month(period), 1)
    docs = now.get("results", [])
    lines = [f"Federal Register documents matching {term}: {now.get('count', 0)} this month, {before.get('count', 0)} the month before."]
    lines += [f"- [{d.get('type', '')}] {d['title']} ({', '.join(a.get('name', '') for a in d.get('agencies') or [])})" for d in docs]
    return {"source": "Federal Register", "lines": lines, "links": [{"title": d["title"], "url": d["html_url"]} for d in docs[:3]]}


def hn(query, period):
    """Most-discussed Hacker News stories for the query this month.

    Headlines only: Algolia's per-month story totals swing by an order of magnitude between months
    (368,063 stories indexed for March 2026, 29,607 for April), so counts are not comparable.
    """
    start, end = month_bounds(period)
    lo = calendar.timegm(start.timetuple())
    hi = calendar.timegm(end.timetuple()) + 86400
    params = {"query": query, "tags": "story", "hitsPerPage": 6, "numericFilters": f"created_at_i>={lo},created_at_i<{hi}"}
    hits = json.loads(get("https://hn.algolia.com/api/v1/search?" + urllib.parse.urlencode(params))).get("hits", [])
    hits.sort(key=lambda h: h.get("points") or 0, reverse=True)
    lines = [f"Most-discussed Hacker News stories matching '{query}' this month (headlines, not a measure of volume):"]
    links = []
    for h in hits:
        url = h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}"
        lines.append(f"- {h.get('title')} ({h.get('points') or 0} points, {h.get('created_at', '')[:10]})")
        links.append({"title": h.get("title") or url, "url": url})
    return {"source": "Hacker News", "lines": lines, "links": links[:2]}


def arxiv(query, period):
    """Number of new arXiv submissions in the category this month vs last month."""

    def total(p):
        start, end = month_bounds(p)
        q = f"{query} AND submittedDate:[{start:%Y%m%d}0000 TO {end:%Y%m%d}2359]"
        # max_results=0 makes arXiv return HTTP 500, so ask for one result and read only the total.
        xml = get("https://export.arxiv.org/api/query?" + urllib.parse.urlencode({"search_query": q, "max_results": 1}))
        node = ET.fromstring(xml).find("{http://a9.com/-/spec/opensearch/1.1/}totalResults")
        time.sleep(3)  # arXiv asks for 3 seconds between API calls
        return int(node.text)

    now, before = total(period), total(prev_month(period))
    return {
        "source": "arXiv",
        "lines": [f"arXiv submissions in {query}: {now} this month, {before} the month before."],
        "links": [{"title": f"arXiv listing: {query}", "url": "https://arxiv.org/list/cs.AI/recent"}],
    }


@lru_cache(maxsize=1)
def _epoch_rows():
    return list(csv.DictReader(io.StringIO(get("https://epoch.ai/data/notable_ai_models.csv"))))


def _published_in(row, start, end):
    return start.isoformat() <= (row.get("Publication date") or "")[:10] <= end.isoformat()


def epoch_models(period):
    """Notable AI models Epoch AI records as published this month, with training compute where known."""
    start, end = month_bounds(period)
    pstart, pend = month_bounds(prev_month(period))
    rows = _epoch_rows()
    now = [r for r in rows if _published_in(r, start, end)]
    before = sum(_published_in(r, pstart, pend) for r in rows)
    lines = [f"Epoch AI notable models published: {len(now)} this month, {before} the month before."]
    for r in now[:12]:
        compute = r.get("Training compute (FLOP)") or "unknown"
        lines.append(f"- {r['Model']} ({r.get('Organization', '')}), training compute {compute} FLOP")
    links = [{"title": f"Epoch AI: {r['Model']}", "url": r["Link"]} for r in now[:2] if (r.get("Link") or "").startswith("http")]
    links.append({"title": "Epoch AI: Notable AI Models dataset (CC BY 4.0)", "url": "https://epoch.ai/data/notable-ai-models"})
    return {"source": "Epoch AI", "lines": lines, "links": links}


def _month_avg(points, period):
    values = [p["value"] for p in points if p["date"][:6] == period.replace("-", "")]
    return sum(values) / len(values) if values else None


def _fmt(v):
    return "n/a" if v is None else f"{v:.3f}"


_gdelt_down = False


def gdelt(query, period):
    """Average news tone and share of global coverage for the query, this month vs last month (daily averages).

    GDELT throttles and times out often. After one failure the rest of the run skips it instead of
    stalling every month on backoff.
    """
    global _gdelt_down
    if _gdelt_down:
        raise RuntimeError("GDELT failed earlier in this run")

    def series(mode):
        start, _ = month_bounds(prev_month(period))
        _, end = month_bounds(period)
        params = {
            "query": query, "mode": mode, "format": "json",
            "startdatetime": f"{start:%Y%m%d}000000", "enddatetime": f"{end:%Y%m%d}235959",
        }
        data = json.loads(get("https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode(params), retries=3, wait=20))
        time.sleep(10)  # GDELT allows one request every 5 seconds and throttles bursts
        points = data["timeline"][0]["data"]
        return _month_avg(points, period), _month_avg(points, prev_month(period))

    try:
        tone, tone_before = series("timelinetone")
        vol, vol_before = series("timelinevol")
    except Exception:
        _gdelt_down = True
        raise
    return {
        "source": "GDELT",
        "lines": [
            f"GDELT average tone of worldwide news coverage matching {query} (negative is more negative): {_fmt(tone)} this month, {_fmt(tone_before)} the month before.",
            f"GDELT share of all monitored news coverage matching {query} (percent): {_fmt(vol)} this month, {_fmt(vol_before)} the month before.",
        ],
        "links": [{"title": "GDELT DOC 2.0 API", "url": "https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/"}],
    }


def collect(signal, period):
    """All evidence for one signal and month, in the order the config lists the sources."""
    parts = []
    if "federal_register" in signal:
        parts.append(safe("Federal Register", federal_register, signal["federal_register"], period))
    for series in signal.get("fred", []):
        parts.append(safe("FRED", fred, series, period))
    if signal.get("epoch_models"):
        parts.append(safe("Epoch AI", epoch_models, period))
    if "arxiv" in signal:
        parts.append(safe("arXiv", arxiv, signal["arxiv"], period))
    if "gdelt" in signal:
        parts.append(safe("GDELT", gdelt, signal["gdelt"], period))
    for q in signal.get("hn_queries", []):
        parts.append(safe("Hacker News", hn, q, period))
    return parts
