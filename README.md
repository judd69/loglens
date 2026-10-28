# LogLens — what broke, how often, when it spiked

> Day 10 of the daily-build series. AIGuard audits your code, JarLens audits
> your jars, CinderLens audits your speed, RepoScope audits any repo,
> VulnLens audits your supply chain, CommitLens audits your history, NetLens
> audits any address, ThreadLens audits your threads — **LogLens audits your
> logs.**

## The problem

Developers sift 50,000-line log files with `grep`. Narrowing to the failure
window, chasing one request ID across services, and reading JSON lines as
plain text are all slow and error-prone. LogLens answers in one command:
what broke, how often, when it spiked, and the full story for one ID.

## What it does

- **Parses four formats, auto-detected per line** (or forced with
  `--input-format auto|json|python|syslog|access`):
  JSON lines, Python logging, syslog-ish lines, and Nginx/Apache combined
  access logs (level derived from status: 5xx = ERROR, 4xx = WARNING).
  Unparseable lines are counted as unparsed, never crashed on.
- **Multi-line entries**: indented lines and tracebacks attach to the
  previous entry instead of polluting the counts.
- **Inputs**: one or more files, `-` for stdin, transparent `.gz` reading.
- **Analysis**: totals, parsed/unparsed counts, time range, counts by level,
  top error messages (numbers, IPs, UUIDs, hex IDs and quoted strings are
  collapsed so repeats group together), top paths, status codes and IPs,
  per-hour timeline, burst detection (busiest windows and highest
  error-rate windows, `--burst-window` seconds), and `--trace ID` mode.
- **Filters**: `--level`, `--since`, `--until` (ISO datetimes or `HH:MM` on
  the log's date), `--grep` regex.
- **Outputs**: coloured text (default), JSON (`--output json`), or a
  self-contained HTML report (`--output html`, inline CSS/JS only, with a
  search box, level filter chips, timeline bars, top-errors and bursts
  tables, and a trace section).
- **CI gate**: `--fail-on error|critical|warning` exits 1 when that level
  (or worse) is present, 0 otherwise; usage errors (missing file, bad
  flag) exit 2.

Zero shipped dependencies — Python 3.8+ standard library only.

## Install and run

```bash
# No install step: clone and run from the repo root.
python3 -m loglens examples/app.log
python3 -m loglens --output json examples/access.log
python3 -m loglens --output html examples/app.log examples/access.log > report.html
python3 -m loglens --trace req-2001 examples/app.log
cat examples/app.log | python3 -m loglens -
python3 -m loglens --fail-on error examples/app.log; echo "exit: $?"
```

## Flags

| Flag | Meaning |
|---|---|
| `--input-format auto\|json\|python\|syslog\|access` | Force one format (default: auto-detect) |
| `--output text\|json\|html` | Report format (default: text) |
| `--no-color` | Disable coloured text output |
| `--level LEVEL[,LEVEL...]` | Only entries at these levels |
| `--since / --until` | ISO datetime or `HH:MM` on the log's date |
| `--grep REGEX` | Only entries matching the regex |
| `--trace ID` | Show every entry mentioning this request ID |
| `--burst-window SECONDS` | Burst window size (default: 60) |
| `--top N` | How many top items to show (default: 10) |
| `--fail-on warning\|error\|critical` | Exit 1 if that level (or worse) is present |

## Example output (real run)

`python3 -m loglens --no-color examples/app.log`:

```
LogLens report
========================================
Entries: 53  (parsed: 51, unparsed: 2)
Time range: 2026-10-28 10:00:01 .. 2026-10-28 11:00:00

By level:
  INFO       28
  WARNING    5
  ERROR      17
  CRITICAL   2
  UNKNOWN    1

Top errors:
     8 x Database connection failed to <ip>:# after # retries
     4 x Timeout waiting for upstream service <str> after #s (request_id=req-#)
     2 x Order processing failed for order #: payment declined
     1 x GET /api/orders -> # in #ms (request_id=req-#)
     1 x Traceback follows for request req-#
     1 x GET /api/checkout -> # in #ms (request_id=req-#)
     1 x Database pool exhausted, rejecting new connections
     1 x CRITICAL disk usage above # percent on /dev/sda#

Per-hour timeline:
  2026-10-28 10:00  total=50 errors=18
  2026-10-28 11:00  total=1 errors=0

Busiest windows (60s windows):
  2026-10-28 10:00:01 .. 2026-10-28 10:01:01  n=5 errors=0 (0%)
  2026-10-28 10:20:01 .. 2026-10-28 10:21:01  n=5 errors=5 (100%)
  2026-10-28 10:21:19 .. 2026-10-28 10:22:19  n=5 errors=5 (100%)

Highest error-rate windows (60s windows):
  2026-10-28 10:20:01 .. 2026-10-28 10:21:01  n=5 errors=5 (100%)
  2026-10-28 10:21:19 .. 2026-10-28 10:22:19  n=5 errors=5 (100%)
  2026-10-28 10:22:31 .. 2026-10-28 10:23:31  n=3 errors=3 (100%)
```

The same command on `examples/access.log` (40 combined-access lines) finds
28 INFO, 4 WARNING and 8 ERROR entries; top path `/api/orders` (13 hits),
top status `200` (24 hits, with six `500`s), top IP `203.0.113.7`
(15 hits), and its worst burst is 10:20:04–10:21:04 (3 entries, 100%
errors). Running both files together gives 93 entries (91 parsed,
2 unparsed) — that combined run is what generated `docs/sample-report.html`.

Tracing one request tells the whole story:

```
$ python3 -m loglens --no-color --trace req-2001 examples/app.log
Trace (4 entries):
  [2026-10-28 10:20:41] ERROR    Timeout waiting for upstream service "payments" after 30s (request_id=req-2001)
  [2026-10-28 10:21:50] ERROR    GET /api/orders -> 500 in 3012ms (request_id=req-2001)
  [2026-10-28 10:22:44] ERROR    Traceback follows for request req-2001
  [2026-10-28 10:23:10] ERROR    GET /api/checkout -> 500 in 2988ms (request_id=req-2001)
```

## Exit codes (verified)

| Case | Exit code |
|---|---|
| `--fail-on error` on `examples/app.log` (contains errors) | 1 |
| `--fail-on error` on an error-free file | 0 |
| Missing input file | 2 |
| Unknown flag | 2 |

## Tests

```bash
python3 -m unittest discover -s tests -v
```

29 tests, all passing: parser formats and fallbacks, message
normalisation, analysis/bursts/traces, report rendering and HTML
self-containment, and CLI end-to-end runs with real exit codes.

## Design reference

Landing page and report styling follow a Linear/Vercel developer-dark
reference: base `#0F172A`, surfaces `#1E293B`, primary text `#F1F5F9`,
muted text `#94A3B8`, indigo accent `#6366F1`.

## License

MIT — see [LICENSE](LICENSE).
