"""Log line parsers for LogLens.

Supported formats (auto-detected per line, or forced with --input-format):
JSON lines, Python logging, syslog-ish, and Nginx/Apache combined access
logs. Anything else becomes an unparsed entry whose level is inferred from
ERROR / WARN / CRITICAL keywords, or UNKNOWN. Multi-line continuations
(indented lines and traceback lines) attach to the previous entry.

Standard library only.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime

LEVEL_ALIASES = {
    "DEBUG": "DEBUG",
    "INFO": "INFO",
    "INFORMATION": "INFO",
    "WARN": "WARNING",
    "WARNING": "WARNING",
    "ERR": "ERROR",
    "ERROR": "ERROR",
    "CRIT": "CRITICAL",
    "CRITICAL": "CRITICAL",
    "FATAL": "CRITICAL",
}

_PYTHON_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:,\d+)?)\s+"
    r"(\w+)\s+([\w.\-]+):\s*(.*)$"
)
_SYSLOG_RE = re.compile(
    r"^([A-Z][a-z]{2})\s+(\d{1,2})\s+(\d{2}:\d{2}:\d{2})\s+"
    r"(\S+)\s+([\w\-./]+)(?:\[(\d+)\])?:\s*(.*)$"
)
_ACCESS_RE = re.compile(
    r'^(\S+) \S+ \S+ \[([^\]]+)\] "(\w+) ([^"]*?)(?: HTTP/[^"]*)?" (\d{3}) (\d+|-)'
)
_MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}

_TRACEBACK_START = re.compile(r"^Traceback \(most recent call last\):")
_EXCEPTION_LINE = re.compile(r"^\w+(Error|Exception|Warning):")


@dataclass
class LogEntry:
    """One logical log entry (possibly spanning several physical lines)."""

    message: str
    level: str = "UNKNOWN"
    timestamp: object = None  # datetime or None
    logger: str = ""
    request_id: str = ""
    path: str = ""
    status: int = 0
    ip: str = ""
    fmt: str = "unparsed"
    raw: str = ""
    parsed: bool = False


def normalise_level(raw):
    """Map a raw level token to a canonical level, or None if unknown."""
    if raw is None:
        return None
    return LEVEL_ALIASES.get(str(raw).strip().upper())


# American-spelling alias.
normalize_level = normalise_level


def infer_level(text):
    """Best-effort level for an unparsed line."""
    upper = text.upper()
    if "CRITICAL" in upper or "FATAL" in upper:
        return "CRITICAL"
    if "ERROR" in upper or "ERR " in upper:
        return "ERROR"
    if "WARN" in upper:
        return "WARNING"
    return "UNKNOWN"


def _parse_python_time(text):
    for fmt in ("%Y-%m-%d %H:%M:%S,%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def parse_json_line(line):
    try:
        obj = json.loads(line)
    except (ValueError, TypeError):
        return None
    if not isinstance(obj, dict):
        return None
    level = None
    for key in ("level", "levelname", "severity"):
        if key in obj:
            level = normalise_level(obj[key])
            break
    timestamp = None
    for key in ("timestamp", "ts", "time", "@timestamp"):
        if key in obj:
            raw = obj[key]
            if isinstance(raw, (int, float)):
                try:
                    timestamp = datetime.fromtimestamp(raw)
                except (ValueError, OverflowError, OSError):
                    timestamp = None
            elif isinstance(raw, str):
                text = raw.replace("Z", "+00:00")
                try:
                    parsed = datetime.fromisoformat(text)
                    timestamp = parsed.replace(tzinfo=None)
                except ValueError:
                    for fmt in ("%Y-%m-%d %H:%M:%S,%f",
                                "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                        try:
                            timestamp = datetime.strptime(raw, fmt)
                            break
                        except ValueError:
                            continue
            break
    message = ""
    for key in ("message", "msg", "log"):
        if key in obj:
            message = str(obj[key])
            break
    logger = str(obj.get("logger", obj.get("name", "")))
    request_id = ""
    for key in ("request_id", "requestId", "correlation_id",
                "correlationId", "trace_id"):
        if key in obj:
            request_id = str(obj[key])
            break
    if level is None:
        level = "INFO"
    return LogEntry(message=message, level=level, timestamp=timestamp,
                    logger=logger, request_id=request_id, fmt="json",
                    raw=line, parsed=True)


def parse_python_line(line):
    match = _PYTHON_RE.match(line)
    if not match:
        return None
    ts_text, level_raw, logger, message = match.groups()
    level = normalise_level(level_raw) or "UNKNOWN"
    return LogEntry(message=message, level=level,
                    timestamp=_parse_python_time(ts_text),
                    logger=logger, fmt="python", raw=line, parsed=True)


def parse_syslog_line(line):
    match = _SYSLOG_RE.match(line)
    if not match:
        return None
    month, day, time_text, host, service, _pid, message = match.groups()
    year = datetime.now().year
    try:
        timestamp = datetime.strptime(
            "%s %s %d %s" % (day, month, year, time_text),
            "%d %b %Y %H:%M:%S")
    except ValueError:
        timestamp = None
    return LogEntry(message=message, level=infer_level(message)
                    if infer_level(message) != "UNKNOWN" else "INFO",
                    timestamp=timestamp, logger=service, fmt="syslog",
                    raw=line, parsed=True)


def parse_access_line(line):
    match = _ACCESS_RE.match(line)
    if not match:
        return None
    ip, ts_text, method, raw_path, status_text, _bytes = match.groups()
    try:
        timestamp = datetime.strptime(ts_text, "%d/%b/%Y:%H:%M:%S %z")
        timestamp = timestamp.replace(tzinfo=None)
    except ValueError:
        timestamp = None
    status = int(status_text)
    if status >= 500:
        level = "ERROR"
    elif status >= 400:
        level = "WARNING"
    else:
        level = "INFO"
    path = raw_path.split("?")[0]
    message = "%s %s -> %d" % (method, path, status)
    return LogEntry(message=message, level=level, timestamp=timestamp,
                    path=path, status=status, ip=ip, fmt="access",
                    raw=line, parsed=True)


_PARSERS = {
    "json": parse_json_line,
    "python": parse_python_line,
    "syslog": parse_syslog_line,
    "access": parse_access_line,
}

_AUTO_ORDER = ("json", "python", "access", "syslog")


def parse_line(line, input_format="auto"):
    """Parse one physical line into an entry (or an unparsed entry).

    Never raises on bad input: unparseable lines become unparsed entries.
    """
    stripped = line.rstrip("\n")
    if input_format and input_format != "auto":
        parser = _PARSERS[input_format]
        entry = parser(stripped)
        if entry is not None:
            return entry
    else:
        if stripped.lstrip().startswith("{"):
            entry = parse_json_line(stripped)
            if entry is not None:
                return entry
        for name in ("python", "access", "syslog"):
            entry = _PARSERS[name](stripped)
            if entry is not None:
                return entry
    return LogEntry(message=stripped, level=infer_level(stripped),
                    fmt="unparsed", raw=stripped, parsed=False)


def _is_continuation(line, previous):
    """True when this physical line belongs to the previous entry."""
    if previous is None:
        return False
    if line[:1] in (" ", "\t"):
        return True
    if _TRACEBACK_START.match(line):
        return True
    if previous.message and "Traceback" in previous.message:
        if line.startswith('File "') or _EXCEPTION_LINE.match(line):
            return True
    if previous.message and "Traceback" in previous.raw:
        if line.startswith('File "') or _EXCEPTION_LINE.match(line):
            return True
    return False


def parse_lines(lines, input_format="auto"):
    """Parse an iterable of lines into a list of LogEntry objects."""
    entries = []
    for line in lines:
        text = line.rstrip("\n")
        if text == "":
            continue
        previous = entries[-1] if entries else None
        if _is_continuation(text, previous):
            previous.message += "\n" + text
            previous.raw += "\n" + text
            continue
        entries.append(parse_line(text, input_format))
    return entries
