# Contributing to LogLens

Thanks for helping improve LogLens — the log auditor that answers, in one
command, what broke, how often, and when it spiked.

## Ground rules

- **Standard library only.** LogLens ships zero dependencies and supports
  Python 3.8+. Do not add a third-party dependency.
- **Bad lines never crash a run.** An unparseable line is counted as
  unparsed, never an exception. Any change to parsing must keep that
  guarantee, with a test proving it.
- **Keep the exit codes honest:** `0` = ok (or a `--fail-on` threshold not
  met), `1` = `--fail-on` gate tripped, `2` = usage error (missing file,
  bad flag, bad time value). CLI tests assert these, so do not renumber
  them casually.

## Setup

There is no install step and no build step. Clone the repo and run from
the repo root:

```bash
git clone https://github.com/judd69/loglens.git
cd loglens
python3 -m loglens examples/app.log
```

## Layout

| Path | What lives there |
|---|---|
| `loglens/__main__.py` | `python3 -m loglens` entry point |
| `loglens/parser.py` | Per-line format detection and parsing (JSON, Python logging, syslog-ish, Nginx/Apache combined access) |
| `loglens/analyze.py` | Filtering, summaries, bursts, traces, message normalisation |
| `loglens/report.py` | Text, JSON and self-contained HTML rendering |
| `loglens/cli.py` | argparse wiring, input reading (files, `-` for stdin, transparent `.gz`), exit codes |
| `tests/` | `unittest` suite, one file per module area |
| `examples/` | Sample logs: `app.log`, `app.jsonl`, `access.log` |
| `docs/` | Generated sample report output — regenerate it, never hand-edit it |

## How parsing and analysis are expected to behave

- Formats are auto-detected per line, or forced with
  `--input-format auto|json|python|syslog|access`.
- Multi-line entries (indented lines, tracebacks) attach to the previous
  entry instead of polluting the counts.
- Access-log levels are derived from status: 5xx = ERROR, 4xx = WARNING.
- Top-error grouping collapses numbers, IPs, UUIDs, hex IDs and quoted
  strings, so repeats of the same failure group together. If you change
  normalisation, say so in the PR and update the affected tests.
- `--trace ID` shows every entry mentioning that request ID, in order.

## Running the tests

```bash
python3 -m unittest discover -s tests -v
```

All tests must pass before you open a PR. Add a test for every behaviour
change or bug fix, using the sample logs in `examples/` where possible
(or a small inline fixture in the test itself). Good places to look for
existing coverage: parser formats and fallbacks, message normalisation,
analysis/bursts/traces, report rendering and HTML self-containment, and
CLI end-to-end runs with real exit codes.

## Trying a change out

```bash
python3 -m loglens --no-color examples/app.log
python3 -m loglens --output json examples/access.log
python3 -m loglens --output html examples/app.log examples/access.log > /tmp/report.html
python3 -m loglens --trace req-2001 examples/app.log
cat examples/app.log | python3 -m loglens -
python3 -m loglens --fail-on error examples/app.log; echo "exit: $?"
```

If your change alters output, update the README's example output and
flag it in the PR description so reviewers can check it against a real
run, not a guess.

## Opening a PR

1. Work on a branch, not `main`.
2. Keep the PR to one change: one fix, one feature, or one docs page.
3. In the description, state what you changed, how you tested it
   (command + result), and any output or exit-code behaviour that moved.
4. One maintainer review is enough for docs; code changes should also
   show the full test suite passing.

## Reporting a bug

Open an issue with the smallest log snippet that reproduces it (redact
real IPs, tokens and user data first), the exact command you ran, and
the output or exit code you got versus what you expected.
