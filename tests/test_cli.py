"""End-to-end CLI tests: real subprocess runs, real exit codes."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES = os.path.join(ROOT, "examples")


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "loglens", *args],
        cwd=ROOT, capture_output=True, text=True)


class TestCli(unittest.TestCase):
    def test_text_output_on_app_log(self):
        result = run_cli("--no-color", os.path.join(EXAMPLES, "app.log"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Entries:", result.stdout)
        self.assertIn("Top errors:", result.stdout)

    def test_json_output_parses(self):
        result = run_cli("--output", "json",
                         os.path.join(EXAMPLES, "app.log"))
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertGreater(data["total"], 0)
        self.assertEqual(data["total"],
                         data["parsed"] + data["unparsed"])

    def test_html_output_self_contained(self):
        result = run_cli("--output", "html",
                         os.path.join(EXAMPLES, "app.log"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("<!DOCTYPE html>", result.stdout)
        self.assertNotIn("http://", result.stdout)
        self.assertNotIn("https://", result.stdout)

    def test_multiple_inputs_and_trace(self):
        result = run_cli("--no-color", "--trace", "req-2001",
                         os.path.join(EXAMPLES, "app.log"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Trace", result.stdout)

    def test_fail_on_error_exits_1_on_error_log(self):
        result = run_cli("--fail-on", "error",
                         os.path.join(EXAMPLES, "app.log"))
        self.assertEqual(result.returncode, 1)

    def test_fail_on_exits_0_on_clean_file(self):
        with tempfile.NamedTemporaryFile(
                "w", suffix=".log", delete=False) as handle:
            handle.write("2026-10-28 10:00:00,000 INFO app: all good\n")
            path = handle.name
        try:
            result = run_cli("--fail-on", "error", path)
            self.assertEqual(result.returncode, 0, result.stderr)
        finally:
            os.unlink(path)

    def test_missing_file_exits_2_without_traceback(self):
        result = run_cli(os.path.join(EXAMPLES, "does-not-exist.log"))
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)

    def test_bad_flag_exits_2(self):
        result = run_cli("--no-such-flag",
                         os.path.join(EXAMPLES, "app.log"))
        self.assertEqual(result.returncode, 2)

    def test_bad_lines_never_crash(self):
        with tempfile.NamedTemporaryFile(
                "w", suffix=".log", delete=False) as handle:
            handle.write("{broken json\n!!! garbage\n"
                         "2026-10-28 10:00:00,000 INFO app: fine\n")
            path = handle.name
        try:
            result = run_cli("--no-color", path)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("unparsed: 2", result.stdout)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
