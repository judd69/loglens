"""Analysis for LogLens: counts, top lists, timelines, bursts, traces.

Standard library only. All functions are pure over lists of LogEntry
objects, which keeps them easy to test.
"""

import re
from collections import Counter
from datetime import timedelta

SEVERITY = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}

_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_HEX_RE = re.compile(r"\b0x[0-9a-fA-F]+\b|\b[0-9a-fA-F]{16,}\b")
_QUOTED_RE = re.compile(r'"[^"]*"|\'[^\']*\'')
_NUMBER_RE = re.compile(r"\d[\d,.]*")


def normalize_message(message):
    """Collapse variable parts so repeated errors group together.

    UUIDs, IPs, hex IDs and quoted strings become placeholders, then any
    remaining number becomes '#'. The first line of a multi-line message
    is used, so tracebacks group by their headline.
    """
    first = message.split("\n", 1)[0]
    text = _UUID_RE.sub("<uuid>", first)
    text = _IP_RE.sub("<ip>", text)
    text = _HEX_RE.sub("<hex>", text)
    text = _QUOTED_RE.sub("<str>", text)
    text = _NUMBER_RE.sub("#", text)
    return " ".join(text.split())


def _top(counter, limit):
    return counter.most_common(limit)


def _windows(entries, window_seconds):
    """Candidate windows: one per entry, starting at that entry's time."""
    timed = sorted((e for e in entries if e.timestamp is not None),
                   key=lambda e: e.timestamp)
    out = []
    for i, start_entry in enumerate(timed):
        start = start_entry.timestamp
        end = start + timedelta(seconds=window_seconds)
        window = [e for e in timed[i:] if e.timestamp < end]
        errors = sum(1 for e in window if SEVERITY.get(e.level, 0) >= 3)
        out.append({
            "start": start,
            "end": end,
            "count": len(window),
            "error_count": errors,
            "error_rate": (errors / len(window)) if window else 0.0,
        })
    return out


def _pick_windows(candidates, key, limit):
    """Top windows by key, greedily skipping windows that overlap a pick."""
    picked = []
    for cand in sorted(candidates, key=key, reverse=True):
        if all(cand["end"] <= p["start"] or cand["start"] >= p["end"]
               for p in picked):
            picked.append(cand)
        if len(picked) >= limit:
            break
    return picked


def summarize(entries, top_n=10, burst_window=60, burst_count=3):
    """Build the full analysis dict for a list of entries."""
    timed = [e.timestamp for e in entries if e.timestamp is not None]
    by_level = Counter(e.level for e in entries)
    error_messages = Counter(
        normalize_message(e.message)
        for e in entries if e.level in ("ERROR", "CRITICAL"))
    paths = Counter(e.path for e in entries if e.path)
    statuses = Counter(e.status for e in entries if e.status)
    ips = Counter(e.ip for e in entries if e.ip)

    per_hour = {}
    for e in entries:
        if e.timestamp is None:
            continue
        hour = e.timestamp.strftime("%Y-%m-%d %H:00")
        bucket = per_hour.setdefault(hour, {"total": 0, "errors": 0})
        bucket["total"] += 1
        if SEVERITY.get(e.level, 0) >= 3:
            bucket["errors"] += 1

    candidates = _windows(entries, burst_window)
    busiest = _pick_windows(candidates, lambda c: c["count"], burst_count)
    rated = [c for c in candidates if c["count"] >= 3] or candidates
    worst_rate = _pick_windows(
        rated, lambda c: (c["error_rate"], c["count"]), burst_count)

    return {
        "total": len(entries),
        "parsed": sum(1 for e in entries if e.parsed),
        "unparsed": sum(1 for e in entries if not e.parsed),
        "time_range": {
            "start": min(timed) if timed else None,
            "end": max(timed) if timed else None,
        },
        "by_level": dict(by_level),
        "top_errors": _top(error_messages, top_n),
        "top_paths": _top(paths, top_n),
        "top_statuses": _top(statuses, top_n),
        "top_ips": _top(ips, top_n),
        "per_hour": per_hour,
        "bursts_busiest": busiest,
        "bursts_error_rate": worst_rate,
        "burst_window": burst_window,
    }


def trace_entries(entries, trace_id):
    """Every entry mentioning trace_id, in original order."""
    needle = trace_id
    out = []
    for e in entries:
        if e.request_id and e.request_id == needle:
            out.append(e)
        elif needle in e.message or needle in e.raw:
            out.append(e)
    return out


def filter_entries(entries, level=None, since=None, until=None, grep=None):
    """Apply --level / --since / --until / --grep filters, in order."""
    import re as _re
    out = list(entries)
    if level:
        wanted = {lvl.strip().upper() for lvl in level.split(",")}
        out = [e for e in out if e.level in wanted]
    if since is not None:
        out = [e for e in out
               if e.timestamp is None or e.timestamp >= since]
    if until is not None:
        out = [e for e in out
               if e.timestamp is None or e.timestamp <= until]
    if grep:
        pattern = _re.compile(grep)
        out = [e for e in out
               if pattern.search(e.message) or pattern.search(e.raw)]
    return out
