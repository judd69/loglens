"""Output renderers for LogLens: coloured text, JSON, self-contained HTML.

The HTML renderer inlines all CSS and JavaScript and escapes all log
content, so the report is a single file with no external assets.
Standard library only.
"""

import html
import json

COLORS = {
    "DEBUG": "\033[36m",     # cyan
    "INFO": "\033[32m",      # green
    "WARNING": "\033[33m",   # yellow
    "ERROR": "\033[31m",     # red
    "CRITICAL": "\033[35m",  # magenta
    "UNKNOWN": "\033[90m",   # grey
}
RESET = "\033[0m"


def _fmt_time(value):
    return value.strftime("%Y-%m-%d %H:%M:%S") if value is not None else "-"


def _jsonable(value):
    if hasattr(value, "strftime"):
        return _fmt_time(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def summary_to_json_dict(summary, trace=None):
    """Summary dict with datetimes and tuples converted to JSON values."""
    data = _jsonable(summary)
    if trace is not None:
        data["trace"] = [
            {"timestamp": _fmt_time(e.timestamp), "level": e.level,
             "message": e.message, "logger": e.logger,
             "request_id": e.request_id}
            for e in trace
        ]
    return data


def render_json(summary, trace=None):
    return json.dumps(summary_to_json_dict(summary, trace), indent=2)


def render_text(summary, trace=None, color=True):
    """Human-readable coloured summary."""
    lines = []
    lines.append("LogLens report")
    lines.append("=" * 40)
    lines.append("Entries: %d  (parsed: %d, unparsed: %d)" % (
        summary["total"], summary["parsed"], summary["unparsed"]))
    tr = summary["time_range"]
    lines.append("Time range: %s .. %s" % (_fmt_time(tr["start"]),
                                            _fmt_time(tr["end"])))
    lines.append("")
    lines.append("By level:")
    for level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "UNKNOWN"):
        count = summary["by_level"].get(level, 0)
        if count:
            label = level
            if color:
                label = COLORS.get(level, "") + level + RESET
            lines.append("  %-10s %d" % (label, count))
    if summary["top_errors"]:
        lines.append("")
        lines.append("Top errors:")
        for message, count in summary["top_errors"]:
            lines.append("  %4d x %s" % (count, message))
    if summary["top_paths"]:
        lines.append("")
        lines.append("Top paths:")
        for path, count in summary["top_paths"]:
            lines.append("  %4d x %s" % (count, path))
    if summary["top_statuses"]:
        lines.append("")
        lines.append("Top status codes:")
        for status, count in summary["top_statuses"]:
            lines.append("  %4d x %s" % (count, status))
    if summary["top_ips"]:
        lines.append("")
        lines.append("Top IPs:")
        for ip, count in summary["top_ips"]:
            lines.append("  %4d x %s" % (count, ip))
    if summary["per_hour"]:
        lines.append("")
        lines.append("Per-hour timeline:")
        for hour in sorted(summary["per_hour"]):
            bucket = summary["per_hour"][hour]
            lines.append("  %s  total=%d errors=%d" % (
                hour, bucket["total"], bucket["errors"]))
    for title, key in (("Busiest windows", "bursts_busiest"),
                       ("Highest error-rate windows", "bursts_error_rate")):
        if summary[key]:
            lines.append("")
            lines.append("%s (%ss windows):" % (title, summary["burst_window"]))
            for burst in summary[key]:
                lines.append("  %s .. %s  n=%d errors=%d (%.0f%%)" % (
                    _fmt_time(burst["start"]), _fmt_time(burst["end"]),
                    burst["count"], burst["error_count"],
                    burst["error_rate"] * 100))
    if trace is not None:
        lines.append("")
        lines.append("Trace (%d entries):" % len(trace))
        for e in trace:
            lines.append("  [%s] %-8s %s" % (
                _fmt_time(e.timestamp), e.level, e.message.split("\n", 1)[0]))
    return "\n".join(lines) + "\n"


def _burst_rows(bursts):
    rows = []
    for burst in bursts:
        rows.append("<tr><td>%s</td><td>%s</td><td>%d</td><td>%d</td>"
                    "<td>%.0f%%</td></tr>" % (
                        html.escape(_fmt_time(burst["start"])),
                        html.escape(_fmt_time(burst["end"])),
                        burst["count"], burst["error_count"],
                        burst["error_rate"] * 100))
    return "\n".join(rows)


def _top_rows(pairs):
    return "\n".join(
        "<tr><td>%d</td><td>%s</td></tr>" % (count, html.escape(str(item)))
        for item, count in pairs)


def render_html(summary, entries, trace=None):
    """Self-contained HTML report: inline CSS/JS only, no external assets."""
    max_hour = max((b["total"] for b in summary["per_hour"].values()),
                   default=0)
    timeline = []
    for hour in sorted(summary["per_hour"]):
        bucket = summary["per_hour"][hour]
        width = int(bucket["total"] / max_hour * 100) if max_hour else 0
        timeline.append(
            '<div class="bar-row"><span class="bar-label">%s</span>'
            '<span class="bar-track"><span class="bar-fill" style="width:%d%%">'
            "</span></span><span class=\"bar-num\">%d total, %d errors</span></div>"
            % (html.escape(hour), width, bucket["total"], bucket["errors"]))
    chips = "".join(
        '<button class="chip" data-level="%s">%s (%d)</button>' % (
            html.escape(level), html.escape(level),
            summary["by_level"].get(level, 0))
        for level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "UNKNOWN")
        if summary["by_level"].get(level, 0))
    entry_rows = []
    for e in entries:
        entry_rows.append(
            '<tr data-level="%s"><td>%s</td><td>%s</td><td>%s</td></tr>' % (
                html.escape(e.level), html.escape(_fmt_time(e.timestamp)),
                html.escape(e.level), html.escape(e.message)))
    trace_section = ""
    if trace is not None:
        items = "".join(
            "<li>[%s] %s — %s</li>" % (
                html.escape(_fmt_time(e.timestamp)), html.escape(e.level),
                html.escape(e.message.split("\n", 1)[0]))
            for e in trace)
        trace_section = ("<h2>Trace</h2><p>%d entries match.</p><ul>%s</ul>"
                         % (len(trace), items))
    tr = summary["time_range"]
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>LogLens report</title>
<style>
body{font-family:system-ui,sans-serif;background:#0F172A;color:#F1F5F9;margin:0 auto;max-width:960px;padding:24px}
h1{font-size:2rem}h2{margin-top:2rem;color:#C7D2FE}
.card{background:#1E293B;border-radius:12px;padding:16px 20px;margin:12px 0}
.muted{color:#94A3B8}
table{width:100%%;border-collapse:collapse}
td,th{padding:6px 10px;border-bottom:1px solid #334155;text-align:left}
input{width:100%%;padding:10px;border-radius:8px;border:1px solid #334155;background:#0F172A;color:#F1F5F9}
.chip{margin:4px;padding:6px 12px;border-radius:999px;border:1px solid #6366F1;background:transparent;color:#F1F5F9;cursor:pointer}
.chip.active{background:#6366F1}
.bar-row{display:flex;align-items:center;gap:10px;margin:6px 0}
.bar-label{width:130px;color:#94A3B8;font-size:.9rem}
.bar-track{flex:1;background:#1E293B;border-radius:6px;height:16px}
.bar-fill{display:block;background:#6366F1;height:16px;border-radius:6px}
.bar-num{width:150px;font-size:.9rem;color:#94A3B8}
</style>
</head>
<body>
<h1>LogLens report</h1>
<div class="card"><p>Entries: <strong>%d</strong> (parsed: %d, unparsed: %d)</p>
<p class="muted">Time range: %s .. %s</p></div>
<div class="card"><h2>Timeline</h2>%s</div>
<div class="card"><h2>Top errors</h2><table><tr><th>Count</th><th>Message</th></tr>%s</table></div>
<div class="card"><h2>Bursts (busiest %ss windows)</h2><table><tr><th>Start</th><th>End</th><th>Entries</th><th>Errors</th><th>Error rate</th></tr>%s</table></div>
<div class="card"><h2>Highest error-rate windows</h2><table><tr><th>Start</th><th>End</th><th>Entries</th><th>Errors</th><th>Error rate</th></tr>%s</table></div>
%s
<div class="card"><h2>Entries</h2>
<input id="search" type="text" placeholder="Search entries...">
<div id="chips">%s <button class="chip active" data-level="ALL">ALL</button></div>
<table id="entries"><tr><th>Time</th><th>Level</th><th>Message</th></tr>%s</table></div>
<script>
var search=document.getElementById('search');
var active='ALL';
function apply(){var q=search.value.toLowerCase();var rows=document.querySelectorAll('#entries tr[data-level]');rows.forEach(function(r){var ok=(active==='ALL'||r.dataset.level===active)&&r.textContent.toLowerCase().indexOf(q)>=0;r.style.display=ok?'':'none';});}
search.addEventListener('input',apply);
document.querySelectorAll('.chip').forEach(function(c){c.addEventListener('click',function(){document.querySelectorAll('.chip').forEach(function(x){x.classList.remove('active');});c.classList.add('active');active=c.dataset.level;apply();});});
</script>
</body>
</html>""" % (
        summary["total"], summary["parsed"], summary["unparsed"],
        html.escape(_fmt_time(tr["start"])), html.escape(_fmt_time(tr["end"])),
        "\n".join(timeline),
        _top_rows(summary["top_errors"]),
        summary["burst_window"], _burst_rows(summary["bursts_busiest"]),
        _burst_rows(summary["bursts_error_rate"]),
        trace_section, chips, "\n".join(entry_rows))
