"""Tests for loglens.report."""

import json
import unittest

from loglens.analyze import summarize
from loglens.parser import LogEntry
from loglens.report import render_html, render_json, render_text


def sample_summary():
    entries = [
        LogEntry(message="boom <script>", level="ERROR",
                 timestamp=None, parsed=True),
        LogEntry(message="ok", level="INFO", timestamp=None, parsed=True),
    ]
    return summarize(entries), entries


class TestReports(unittest.TestCase):
    def test_text_contains_counts(self):
        summary, _ = sample_summary()
        text = render_text(summary, color=False)
        self.assertIn("Entries: 2", text)
        self.assertIn("ERROR", text)

    def test_json_is_valid(self):
        summary, _ = sample_summary()
        data = json.loads(render_json(summary))
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["by_level"]["ERROR"], 1)

    def test_html_escapes_and_is_self_contained(self):
        summary, entries = sample_summary()
        html_text = render_html(summary, entries)
        self.assertIn("&lt;script&gt;", html_text)
        self.assertNotIn("<script>alert", html_text)
        self.assertNotIn("http://", html_text)
        self.assertNotIn("https://", html_text)
        self.assertIn('id="search"', html_text)
        self.assertIn('class="chip"', html_text)

    def test_html_trace_section(self):
        summary, entries = sample_summary()
        html_text = render_html(summary, entries, trace=entries[:1])
        self.assertIn("<h2>Trace</h2>", html_text)


if __name__ == "__main__":
    unittest.main()
