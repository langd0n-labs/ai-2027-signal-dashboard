"""Run with: python pipeline/test_pipeline.py"""

import unittest

from check_data import problems
from classify_signals import validate
from fetch_sources import _month_avg, allowed, month_bounds, prev_month, safe
from run import last_complete_month, merge, month, months

SIGNALS = [{"id": i, "name": i, "accelerating": "a", "stabilizing": "s"} for i in ("policy", "labor")]


def entry(signal, period, status="unclear"):
    return {"signal": signal, "period": period, "status": status}


class Periods(unittest.TestCase):
    def test_month_math(self):
        self.assertEqual(prev_month("2026-01"), "2025-12")
        self.assertEqual(months("2025-11", "2026-02"), ["2025-11", "2025-12", "2026-01", "2026-02"])
        self.assertEqual(month_bounds("2028-02")[1].day, 29)

    def test_last_complete_month(self):
        from datetime import date
        self.assertEqual(last_complete_month(date(2026, 1, 3)), "2025-12")

    def test_month_rejects_bad_input(self):
        for bad in ("2026-13", "2026-1", "26-01", "2026-01; rm -rf /", None):
            with self.assertRaises(Exception):
                month(bad)


class Merge(unittest.TestCase):
    def test_replaces_same_key_and_keeps_others(self):
        doc = {"entries": [entry("policy", "2026-04"), entry("labor", "2026-04")]}
        out = merge(doc, [entry("policy", "2026-04", "accelerating")], SIGNALS, "now")
        self.assertEqual([(e["signal"], e["status"]) for e in out["entries"]], [("policy", "accelerating"), ("labor", "unclear")])

    def test_drops_sample_entries(self):
        doc = {"sample": True, "entries": [entry("labor", "2026-04")]}
        out = merge(doc, [entry("policy", "2026-05")], SIGNALS, "now")
        self.assertFalse(out["sample"])
        self.assertEqual(len(out["entries"]), 1)

    def test_sorted_by_period_then_config_order(self):
        out = merge({}, [entry("labor", "2026-05"), entry("policy", "2026-05"), entry("labor", "2026-04")], SIGNALS, "now")
        self.assertEqual([(e["period"], e["signal"]) for e in out["entries"]], [("2026-04", "labor"), ("2026-05", "policy"), ("2026-05", "labor")])


class Validate(unittest.TestCase):
    def test_accepts_good(self):
        self.assertEqual(validate({"status": "stabilizing", "justification": " ok ", "confidence": 3})["justification"], "ok")

    def test_rejects_bad(self):
        for bad in ({"status": "up", "justification": "x", "confidence": 3},
                    {"status": "unclear", "justification": "x", "confidence": 9},
                    {"status": "unclear", "justification": " ", "confidence": 2}):
            with self.assertRaises(ValueError):
                validate(bad)


class Gdelt(unittest.TestCase):
    def test_month_avg(self):
        pts = [{"date": "20260401T000000Z", "value": 1.0}, {"date": "20260402T000000Z", "value": 3.0}, {"date": "20260301T000000Z", "value": 9}]
        self.assertEqual(_month_avg(pts, "2026-04"), 2.0)
        self.assertIsNone(_month_avg(pts, "2026-05"))


class Sources(unittest.TestCase):
    def test_failed_source_is_marked_failed(self):
        def boom(period):
            raise TimeoutError
        self.assertEqual(safe("X", boom, "2026-04")["status"], "failed")

    def test_links_off_the_allowlist_are_dropped(self):
        out = safe("X", lambda p: {"source": "X", "status": "ok", "lines": [], "links": [
            {"title": "ok", "url": "https://news.ycombinator.com/item?id=1"},
            {"title": "bad", "url": "https://evil.example/x"}]}, "2026-04")
        self.assertEqual([link["title"] for link in out["links"]], ["ok"])
        self.assertFalse(allowed({"url": "https://fred.stlouisfed.org.evil.example/"}))


def good_doc():
    return {"schema": 1, "sample": False, "period": "month", "signals": [{"id": "policy"}], "entries": [{
        "signal": "policy", "period": "2026-04", "status": "unclear", "justification": "Mixed.", "confidence": 2,
        "sources": [{"title": "t", "url": "https://www.federalregister.gov/d/1"}], "provider": "anthropic",
        "model": "m", "run": "backfill", "classified_at": "2026-10-09T00:00:00Z"}]}


class Ollama(unittest.TestCase):
    def call(self, content, **reply):
        import io, json
        from unittest import mock
        from classify_signals import classify
        sent = {}

        def fake_urlopen(request, timeout):
            sent.update(json.loads(request.data))
            body = {"model": "qwen2.5:7b", "done_reason": "stop", "prompt_eval_count": 1500, "message": {"content": content}}
            return io.BytesIO(json.dumps({**body, **reply}).encode())

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            return classify({"provider": "ollama", "model": "qwen2.5:7b", "max_tokens": 100}, "prompt"), sent

    def test_sends_schema_and_validates_reply(self):
        import json
        from classify_signals import SCHEMA
        (result, model), sent = self.call(json.dumps({"status": "unclear", "justification": "Thin evidence.", "confidence": 2}))
        self.assertEqual(sent["format"], SCHEMA)
        self.assertEqual(sent["options"]["num_predict"], 100)
        self.assertEqual((result["status"], model), ("unclear", "qwen2.5:7b"))

    def test_rejects_bad_replies(self):
        import json
        good = json.dumps({"status": "unclear", "justification": "x", "confidence": 2})
        for content, reply in ((json.dumps({"status": "bogus", "justification": "x", "confidence": 2}), {}),
                               ("not json", {}),
                               (good, {"done_reason": "length"}),
                               (good, {"prompt_eval_count": 8150})):
            with self.assertRaises((ValueError, RuntimeError)):
                self.call(content, **reply)


class CheckData(unittest.TestCase):
    def test_good_document_passes(self):
        self.assertEqual(problems(good_doc()), [])

    def test_catches_bad_data(self):
        doc = good_doc()
        doc["entries"][0].update(period="2026-13", status="up", sources=[{"url": "http://evil.example"}])
        doc["entries"].append(dict(doc["entries"][0]))
        found = " ".join(problems(doc))
        for needle in ("bad period", "bad status", "allowed host", "duplicate"):
            self.assertIn(needle, found)

    def test_total_failure_and_sample_fail(self):
        doc = good_doc()
        doc.update(sample=True, entries=[])
        found = " ".join(problems(doc))
        self.assertIn("sample", found)
        self.assertIn("no entries", found)


class ExitCodes(unittest.TestCase):
    def run_with(self, collect, classify=None):
        import tempfile
        from pathlib import Path

        import run
        tmp = Path(tempfile.mkdtemp())
        saved = run.DATA, run.EVIDENCE, run.collect, run.classify
        run.DATA, run.EVIDENCE, run.collect = tmp / "signals.json", tmp / "evidence", collect
        run.classify = classify or (lambda llm, prompt: ({"status": "unclear", "justification": "Mixed.", "confidence": 2}, "m"))
        try:
            return run.main(["--period", "2026-04"])
        finally:
            run.DATA, run.EVIDENCE, run.collect, run.classify = saved

    def test_one_signal_without_data_is_partial(self):
        ok = {"source": "FRED", "status": "ok", "lines": ["x"], "links": []}
        bad = {"source": "GDELT", "status": "failed", "lines": ["x"], "links": []}
        self.assertEqual(self.run_with(lambda s, p: [bad] if s["id"] == "opinion" else [ok]), 3)

    def test_all_good_is_zero_and_all_failed_is_four(self):
        ok = {"source": "FRED", "status": "ok", "lines": ["x"], "links": []}
        bad = {"source": "GDELT", "status": "failed", "lines": ["x"], "links": []}
        self.assertEqual(self.run_with(lambda s, p: [ok]), 0)
        self.assertEqual(self.run_with(lambda s, p: [bad]), 4)


class EvidenceKept(unittest.TestCase):
    def test_failed_rerun_keeps_old_evidence_and_success_replaces_it(self):
        import json
        import tempfile
        from pathlib import Path

        import run
        tmp = Path(tempfile.mkdtemp())
        ok = {"source": "FRED", "status": "ok", "lines": ["new"], "links": []}
        good = lambda llm, prompt: ({"status": "unclear", "justification": "Mixed.", "confidence": 2}, "m")  # noqa: E731

        def boom(llm, prompt):
            raise RuntimeError("down")

        saved = run.DATA, run.EVIDENCE, run.collect, run.classify
        run.DATA, run.EVIDENCE, run.collect = tmp / "signals.json", tmp / "evidence", lambda s, p: [ok]
        try:
            run.EVIDENCE.mkdir()
            (run.EVIDENCE / "2026-04.json").write_text(json.dumps({"policy": "OLD", "labor": "OLD"}))
            run.classify = boom
            self.assertEqual(run.main(["--period", "2026-04"]), 4)
            self.assertEqual(set(json.loads((run.EVIDENCE / "2026-04.json").read_text()).values()), {"OLD"})
            run.classify = good
            self.assertEqual(run.main(["--period", "2026-04"]), 0)
            self.assertNotIn("OLD", json.loads((run.EVIDENCE / "2026-04.json").read_text()).values())
        finally:
            run.DATA, run.EVIDENCE, run.collect, run.classify = saved


class Summary(unittest.TestCase):
    def test_no_data_signals_are_not_listed_as_classified(self):
        from run import summary
        text = summary(["2026-09"], 0, [], {}, [("2026-09", "policy")])
        self.assertIn("No reading", text)
        self.assertNotIn("classified without them", text)


class WorkflowPreflight(unittest.TestCase):
    """Exercise the workflow preflight shell without GitHub access."""

    @classmethod
    def setUpClass(cls):
        from pathlib import Path
        cls.root = Path(__file__).resolve().parents[1]
        cls.workflow = (cls.root / ".github/workflows/update_signals.yml").read_text()

    def step(self, name):
        import re
        start = self.workflow.index("      - name: " + name + "\n")
        rest = self.workflow[start:]
        return re.split(r"(?=^      - (?:name:|uses:))", rest, flags=re.M)[1]


    def test_preflight_reports_missing_names_without_values(self):
        import os
        import subprocess
        import textwrap
        preflight = self.step("Check App configuration")
        self.assertIn("SIGNALS_APP_CLIENT_ID: ${{ vars.SIGNALS_APP_CLIENT_ID }}", preflight)
        self.assertIn("SIGNALS_APP_PRIVATE_KEY: ${{ secrets.SIGNALS_APP_PRIVATE_KEY }}", preflight)
        script = textwrap.dedent(preflight.split("        run: |\n", 1)[1])
        names = ("SIGNALS_APP_CLIENT_ID", "SIGNALS_APP_PRIVATE_KEY")
        for client, key in (("", ""), ("client-sentinel", ""), ("", "pem-sentinel"),
                            ("client-sentinel", "pem-sentinel")):
            with self.subTest(client=bool(client), key=bool(key)):
                result = subprocess.run(["bash", "-e", "-o", "pipefail", "-c", script],
                                        env={**os.environ, **dict(zip(names, (client, key)))},
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, int(not client or not key))
                output = result.stdout + result.stderr
                for name, value in zip(names, (client, key)):
                    self.assertEqual(name in output, not bool(value))
                self.assertNotIn("client-sentinel", output)
                self.assertNotIn("pem-sentinel", output)

if __name__ == "__main__":
    unittest.main()
