"""Tests for loglens.analyze."""

import unittest
from datetime import datetime

from loglens.analyze import (filter_entries, normalize_message, summarize,
                             trace_entries)
from loglens.parser import LogEntry


def entry(message, level="INFO", ts=None, request_id=""):
    return LogEntry(message=message, level=level, timestamp=ts,
                    request_id=request_id, parsed=True)


class TestNormalize(unittest.TestCase):
    def test_collapses_numbers_ips_uuids_quoted(self):
        self.assertEqual(
            normalize_message('Failed for user 42 at 10.0.0.5 id '
                              '550e8400-e29b-41d4-a716-446655440000 after "30s"'),
            'Failed for user # at <ip> id <uuid> after <str>')
        self.assertEqual(
            normalize_message("Timeout after 30s for order 991"),
            "Timeout after #s for order #")
        self.assertEqual(
            normalize_message("Error 0xDEADBEEF in module"),
            "Error <hex> in module")


class TestSummarize(unittest.TestCase):
    def setUp(self):
        base = datetime(2026, 10, 28, 10, 20, 0)
        self.entries = [
            entry("Database failed to 10.0.0.1 after 3 retries", "ERROR",
                  datetime(2026, 10, 28, 10, 20, 1)),
            entry("Database failed to 10.0.0.2 after 5 retries", "ERROR",
                  datetime(2026, 10, 28, 10, 20, 20)),
            entry("ok", "INFO", datetime(2026, 10, 28, 10, 20, 40)),
            entry("ok", "INFO", datetime(2026, 10, 28, 11, 5, 0)),
        ]

    def test_counts_and_top_errors_grouped(self):
        summary = summarize(self.entries)
        self.assertEqual(summary["total"], 4)
        self.assertEqual(summary["by_level"]["ERROR"], 2)
        self.assertEqual(summary["top_errors"][0],
                         ("Database failed to <ip> after # retries", 2))

    def test_per_hour_and_bursts(self):
        summary = summarize(self.entries, burst_window=60)
        self.assertEqual(summary["per_hour"]["2026-10-28 10:00"]["total"], 3)
        self.assertEqual(summary["per_hour"]["2026-10-28 10:00"]["errors"], 2)
        self.assertTrue(summary["bursts_busiest"])
        self.assertEqual(summary["bursts_busiest"][0]["count"], 3)

    def test_trace_finds_by_id_and_by_message(self):
        entries = [
            entry("start", "INFO", request_id="req-7"),
            entry("saw req-7 again", "INFO"),
            entry("unrelated", "INFO"),
        ]
        traced = trace_entries(entries, "req-7")
        self.assertEqual(len(traced), 2)

    def test_filters(self):
        filtered = filter_entries(self.entries, level="ERROR")
        self.assertEqual(len(filtered), 2)
        since = filter_entries(
            self.entries, since=datetime(2026, 10, 28, 11, 0, 0))
        self.assertEqual(len(since), 1)
        grepped = filter_entries(self.entries, grep="Database")
        self.assertEqual(len(grepped), 2)


if __name__ == "__main__":
    unittest.main()
