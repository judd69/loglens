"""Tests for loglens.parser."""

import unittest
from datetime import datetime

from loglens.parser import (infer_level, normalize_level, parse_lines,
                            parse_line)


def norm(level):
    return normalize_level(level)


class TestJsonLines(unittest.TestCase):
    def test_common_key_names(self):
        entry = parse_line(
            '{"ts": "2026-10-28T10:15:00", "level": "error", "msg": "boom", '
            '"request_id": "req-9"}')
        self.assertTrue(entry.parsed)
        self.assertEqual(entry.level, "ERROR")
        self.assertEqual(entry.message, "boom")
        self.assertEqual(entry.request_id, "req-9")
        self.assertEqual(entry.timestamp, datetime(2026, 10, 28, 10, 15, 0))

    def test_warn_alias_and_correlation_id(self):
        entry = parse_line(
            '{"time": "2026-10-28 10:15:00", "severity": "WARN", '
            '"message": "slow", "correlation_id": "c-1"}')
        self.assertEqual(entry.level, "WARNING")
        self.assertEqual(entry.request_id, "c-1")


class TestPythonLogging(unittest.TestCase):
    def test_basic(self):
        entry = parse_line(
            "2026-10-28 10:15:23,456 INFO app.api: hello world")
        self.assertTrue(entry.parsed)
        self.assertEqual(entry.level, "INFO")
        self.assertEqual(entry.logger, "app.api")
        self.assertEqual(entry.message, "hello world")
        self.assertEqual(entry.timestamp, datetime(2026, 10, 28, 10, 15, 23, 456000))


class TestSyslog(unittest.TestCase):
    def test_basic(self):
        entry = parse_line("Oct 28 10:15:23 myhost myservice[123]: hello")
        self.assertTrue(entry.parsed)
        self.assertEqual(entry.logger, "myservice")
        self.assertEqual(entry.message, "hello")
        self.assertEqual(entry.timestamp.month, 10)
        self.assertEqual(entry.timestamp.day, 28)


class TestAccessLog(unittest.TestCase):
    def test_levels_derived_from_status(self):
        ok = parse_line('1.2.3.4 - - [28/Oct/2026:10:15:23 +0000] '
                        '"GET /api/users HTTP/1.1" 200 123')
        self.assertEqual(ok.level, "INFO")
        self.assertEqual(ok.path, "/api/users")
        self.assertEqual(ok.status, 200)
        self.assertEqual(ok.ip, "1.2.3.4")
        self.assertEqual(ok.message, "GET /api/users -> 200")
        warn = parse_line('1.2.3.4 - - [28/Oct/2026:10:15:23 +0000] '
                          '"GET /nope HTTP/1.1" 404 123')
        self.assertEqual(warn.level, "WARNING")
        err = parse_line('1.2.3.4 - - [28/Oct/2026:10:15:23 +0000] '
                         '"GET /api/x HTTP/1.1" 500 123')
        self.assertEqual(err.level, "ERROR")

    def test_query_string_stripped_from_path(self):
        entry = parse_line('1.2.3.4 - - [28/Oct/2026:10:15:23 +0000] '
                           '"GET /api/users?page=2 HTTP/1.1" 200 123')
        self.assertEqual(entry.path, "/api/users")


class TestFallbackAndContinuations(unittest.TestCase):
    def test_unparsed_line_counted_and_level_inferred(self):
        entry = parse_line("something about an ERROR happened")
        self.assertFalse(entry.parsed)
        self.assertEqual(entry.level, "ERROR")

    def test_unknown_when_no_keyword(self):
        entry = parse_line("!!! no format here")
        self.assertFalse(entry.parsed)
        self.assertEqual(entry.level, "UNKNOWN")

    def test_traceback_attaches_to_previous_entry(self):
        entries = parse_lines([
            "2026-10-28 10:15:23,000 ERROR app: boom\n",
            "Traceback (most recent call last):\n",
            '  File "/srv/app.py", line 1, in main\n',
            "ValueError: bad value\n",
            "2026-10-28 10:16:00,000 INFO app: recovered\n",
        ])
        self.assertEqual(len(entries), 2)
        self.assertIn("ValueError: bad value", entries[0].message)
        self.assertEqual(entries[1].message, "recovered")

    def test_forced_format_rejects_other_formats(self):
        entry = parse_line(
            "2026-10-28 10:15:23,000 INFO app: hello", input_format="json")
        self.assertFalse(entry.parsed)

    def test_bad_input_never_raises(self):
        for line in ["{not json", "\x00\x01 garbage", "2026-13-99 99:99:99 INFO x: y"]:
            entry = parse_line(line)  # must not raise
            self.assertIsNotNone(entry)


if __name__ == "__main__":
    unittest.main()
