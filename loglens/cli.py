"""LogLens command line interface (argparse, standard library only).

Exit codes: 0 ok (or --fail-on threshold not met), 1 --fail-on gate
tripped, 2 usage error (bad flag, missing file, bad time value).
Bad log lines never crash the run: they are counted as unparsed.
"""

import argparse
import gzip
import re
import sys
from datetime import datetime, time as dtime

from .analyze import (SEVERITY, filter_entries, summarize, trace_entries)
from .parser import parse_lines
from .report import render_html, render_json, render_text

VERSION = "1.0.0"


def read_input_lines(paths):
    """Yield lines from files, '-' (stdin), or transparently from .gz."""
    lines = []
    for path in paths:
        if path == "-":
            lines.extend(sys.stdin.readlines())
        elif path.endswith(".gz"):
            try:
                with gzip.open(path, "rt", errors="replace") as handle:
                    lines.extend(handle.readlines())
            except (OSError, EOFError) as exc:
                raise CliError("cannot read %s: %s" % (path, exc))
        else:
            try:
                with open(path, "r", errors="replace") as handle:
                    lines.extend(handle.readlines())
            except OSError as exc:
                raise CliError("cannot read %s: %s" % (path, exc))
    return lines


class CliError(Exception):
    """Usage-level error: reported cleanly, exits 2, no traceback."""


_HHMM_RE = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")


def parse_time_value(value, base_date):
    """Parse an ISO datetime or an HH:MM time on the log's date."""
    match = _HHMM_RE.match(value)
    if match:
        hour, minute, second = match.groups()
        return datetime.combine(
            base_date, dtime(int(hour), int(minute), int(second or 0)))
    text = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
        return parsed.replace(tzinfo=None)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise CliError("bad time value: %r (use ISO datetime or HH:MM)" % value)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="loglens",
        description="LogLens: what broke, how often, when it spiked, "
                    "and the full story for one ID.")
    parser.add_argument("inputs", nargs="+",
                        help="log file(s); use - for stdin")
    parser.add_argument("--input-format", default="auto",
                        choices=["auto", "json", "python", "syslog", "access"],
                        help="force one input format (default: auto-detect)")
    parser.add_argument("--output", default="text",
                        choices=["text", "json", "html"],
                        help="report format (default: text)")
    parser.add_argument("--no-color", action="store_true",
                        help="disable coloured text output")
    parser.add_argument("--level",
                        help="only entries at this level (comma-separated)")
    parser.add_argument("--since",
                        help="only entries at/after this ISO datetime or HH:MM")
    parser.add_argument("--until",
                        help="only entries at/before this ISO datetime or HH:MM")
    parser.add_argument("--grep", help="only entries matching this regex")
    parser.add_argument("--trace",
                        help="show every entry mentioning this request ID")
    parser.add_argument("--burst-window", type=int, default=60,
                        help="burst window in seconds (default: 60)")
    parser.add_argument("--top", type=int, default=10,
                        help="how many top items to show (default: 10)")
    parser.add_argument("--fail-on", choices=["warning", "error", "critical"],
                        help="exit 1 if this level (or worse) is present")
    parser.add_argument("--version", action="version", version=VERSION)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except CliError as exc:
        print("loglens: error: %s" % exc, file=sys.stderr)
        return 2


def run(args):
    if args.burst_window <= 0:
        raise CliError("--burst-window must be positive")
    if args.top <= 0:
        raise CliError("--top must be positive")
    if args.grep:
        try:
            re.compile(args.grep)
        except re.error as exc:
            raise CliError("bad --grep regex: %s" % exc)
    lines = read_input_lines(args.inputs)
    entries = parse_lines(lines, args.input_format)

    base_date = None
    for entry in entries:
        if entry.timestamp is not None:
            base_date = entry.timestamp.date()
            break
    if base_date is None:
        base_date = datetime.now().date()
    since = parse_time_value(args.since, base_date) if args.since else None
    until = parse_time_value(args.until, base_date) if args.until else None

    filtered = filter_entries(entries, args.level, since, until, args.grep)
    summary = summarize(filtered, top_n=args.top,
                        burst_window=args.burst_window)
    trace = trace_entries(filtered, args.trace) if args.trace else None

    if args.output == "json":
        sys.stdout.write(render_json(summary, trace))
        sys.stdout.write("\n")
    elif args.output == "html":
        sys.stdout.write(render_html(summary, filtered, trace))
    else:
        sys.stdout.write(render_text(summary, trace,
                                     color=not args.no_color))

    if args.fail_on:
        threshold = SEVERITY[args.fail_on.upper()]
        worst = max((SEVERITY.get(e.level, 0) for e in filtered), default=0)
        if worst >= threshold:
            return 1
    return 0
