"""Self-contained HTML dashboard: inline CSS, inline SVG, no network, no CDN."""

from __future__ import annotations

import html
from datetime import datetime, timezone

from .findings import RULES, rule_frequency, severity_counts
from .scan import ScanResult
from .scoring import SCORE_WEIGHTS, SUBSCORE_HINTS
from .utils import human_int, human_size, pct

SEVERITY_COLOURS = {
    "high": "#f87171",
    "medium": "#fbbf24",
    "low": "#38bdf8",
    "info": "#94a3b8",
}

LANGUAGE_COLOURS = {
    "Python": "#4ade80", "TypeScript": "#60a5fa", "JavaScript": "#facc15",
    "Go": "#22d3ee", "Rust": "#fb923c", "Java": "#f472b6", "C": "#a78bfa",
    "C++": "#c084fc", "Shell": "#fbbf24", "HTML": "#fb7185", "CSS": "#818cf8",
    "Markdown": "#e2e8f0", "JSON": "#38bdf8", "YAML": "#94a3b8",
}

CSS = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body { margin:0; background:#0b0f17; color:#d7dee9;
  font:14px/1.55 ui-sans-serif,-apple-system,'Segoe UI',Roboto,sans-serif; }
.wrap { max-width:1040px; margin:0 auto; padding:40px 32px 64px; }
header { display:flex; align-items:flex-start; justify-content:space-between; gap:24px; }
h1 { font-size:26px; margin:0 0 4px; letter-spacing:-.01em; }
h1 span { color:#4ade80; }
h2 { font-size:13px; text-transform:uppercase; letter-spacing:.12em;
  color:#7c8ba1; margin:36px 0 12px; font-weight:600; }
.sub { color:#8b9bb4; font-size:13px; }
.scorebox { text-align:right; min-width:190px; }
.score { font-size:52px; font-weight:700; line-height:1; letter-spacing:-.03em; }
.grade { display:inline-block; margin-top:6px; padding:3px 10px; border-radius:999px;
  font-size:12px; font-weight:700; letter-spacing:.06em; }
.grid { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin-top:26px; }
.card { background:#111827; border:1px solid #1f2937; border-radius:12px; padding:14px 16px; }
.card .k { color:#8b9bb4; font-size:11px; text-transform:uppercase; letter-spacing:.1em; }
.card .v { font-size:22px; font-weight:600; margin-top:4px; }
.card .m { color:#6b7280; font-size:12px; margin-top:2px; }
table { width:100%; border-collapse:collapse; font-size:13.5px; }
th { text-align:left; color:#7c8ba1; font-weight:600; font-size:11px;
  text-transform:uppercase; letter-spacing:.09em; padding:6px 10px 6px 0;
  border-bottom:1px solid #1f2937; }
td { padding:7px 10px 7px 0; border-bottom:1px solid #151d2b; vertical-align:top; }
tr:last-child td { border-bottom:none; }
.mono { font-family:ui-monospace,'Cascadia Mono',Consolas,monospace; }
.num { text-align:right; font-variant-numeric:tabular-nums; }
.pill { display:inline-block; padding:1px 7px; border-radius:999px; font-size:11px;
  font-weight:700; letter-spacing:.04em; }
.rule { color:#6b7280; font-family:ui-monospace,Consolas,monospace; font-size:12px; }
.path { color:#93c5fd; font-family:ui-monospace,Consolas,monospace; font-size:12px; }
.legend { display:flex; gap:14px; flex-wrap:wrap; color:#8b9bb4; font-size:12px; margin-top:8px; }
.dot { display:inline-block; width:9px; height:9px; border-radius:2px; margin-right:6px; }
footer { margin-top:40px; color:#4b5563; font-size:12px; }
"""


def _esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def _svg_bar(value: float, width: int = 160, height: int = 8,
             colour: str = "#4ade80") -> str:
    filled = max(0.0, min(100.0, value)) / 100.0 * width
    return (
        '<svg width="%d" height="%d" viewBox="0 0 %d %d" role="img" aria-label="%.0f out of 100">'
        '<rect x="0" y="0" width="%d" height="%d" rx="%d" fill="#1f2937"/>'
        '<rect x="0" y="0" width="%.1f" height="%d" rx="%d" fill="%s"/>'
        "</svg>" % (width, height, width, height, value, width, height,
                    height // 2, filled, height, height // 2, colour))


def _svg_donut(items: list[tuple[str, float]], size: int = 132,
               stroke: int = 16) -> str:
    """Language mix as a donut. Items are (label, value) with value in percent."""
    radius = (size - stroke) / 2.0
    circumference = 2 * 3.141592653589793 * radius
    parts = []
    offset = 0.0
    for label, value in items:
        fraction = max(0.0, min(100.0, value)) / 100.0
        dash = fraction * circumference
        colour = LANGUAGE_COLOURS.get(label, "#64748b")
        parts.append(
            '<circle r="%.2f" cx="%.2f" cy="%.2f" fill="none" stroke="%s" stroke-width="%d" '
            'stroke-dasharray="%.2f %.2f" stroke-dashoffset="%.2f" transform="rotate(-90 %.2f %.2f)"/>'
            % (radius, size / 2, size / 2, colour, stroke, dash,
               circumference - dash, -offset, size / 2, size / 2))
        offset += dash
    return ('<svg width="%d" height="%d" viewBox="0 0 %d %d" role="img" aria-label="language mix">'
            '<circle r="%.2f" cx="%.2f" cy="%.2f" fill="none" stroke="#1f2937" stroke-width="%d"/>'
            "%s</svg>" % (size, size, size, size, radius, size / 2, size / 2, stroke,
                          "".join(parts)))


def _svg_histogram(values: list[float], width: int = 320, height: int = 72) -> str:
    """Commit-churn histogram: one bar per hotspot, height relative to max."""
    if not values:
        return _svg_bar(0, width, height, "#334155")
    peak = max(values) or 1.0
    slot = width / max(1, len(values))
    bars = []
    for index, value in enumerate(values):
        h = max(2.0, (value / peak) * (height - 12))
        x = index * slot + slot * 0.18
        bars.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="2" fill="#38bdf8" opacity="%.2f"/>'
                    % (x, height - h, slot * 0.64, h, 0.45 + 0.55 * (value / peak)))
    return ('<svg width="%d" height="%d" viewBox="0 0 %d %d" role="img" aria-label="churn distribution">'
            '<line x1="0" y1="%d" x2="%d" y2="%d" stroke="#1f2937"/>%s</svg>'
            % (width, height, width, height, height - 1, width, height - 1, "".join(bars)))


def _grade_colour(score: float) -> str:
    if score >= 80:
        return "#4ade80"
    if score >= 60:
        return "#fbbf24"
    return "#f87171"


def build_html(result: ScanResult, top: int = 10, title: str | None = None) -> str:
    """Render the whole dashboard as one self-contained HTML document."""
    eco = result.ecosystem
    sev = severity_counts(result.findings)
    langs = sorted((s for s in result.languages.values() if s.code > 0),
                   key=lambda s: (-s.code, s.name))
    heading = title or "repo-radar"
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out: list[str] = []
    out.append("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">")
    out.append('<meta name="viewport" content="width=device-width,initial-scale=1">')
    out.append("<title>%s · %s</title><style>%s</style></head><body><div class=\"wrap\">"
               % (_esc(heading), _esc(result.root.name), CSS))
    out.append("<header><div><h1>%s</h1>" % _esc(heading))
    out.append('<div class="sub mono">%s</div>' % _esc(result.root))
    out.append('<div class="sub">%s files · %s · %s code lines · scanned in %.0f ms</div>'
               % (human_int(result.total_files), human_size(result.total_bytes),
                  human_int(result.code_lines), result.duration_ms))
    out.append("</div><div class=\"scorebox\">")
    colour = _grade_colour(result.score)
    out.append('<div class="score" style="color:%s">%d<span style="font-size:20px;color:#4b5563">/100</span></div>'
               % (colour, int(result.score)))
    out.append('<div class="grade" style="background:%s22;color:%s;border:1px solid %s55">GRADE %s</div>'
               % (colour, colour, colour, _esc(result.grade)))
    out.append('<div class="sub" style="margin-top:10px">%s</div></div></header>'
               % _esc(_verdict(result)))

    out.append('<div class="grid">')
    out.append(_card("code lines", human_int(result.code_lines),
                     "%s comment" % ("%.0f%%" % pct(result.comment_lines, result.code_lines))))
    out.append(_card("files", human_int(result.total_files), human_size(result.total_bytes)))
    out.append(_card("languages", str(len(langs)), " · ".join(s.name for s in langs[:3])))
    out.append(_card("entry points", str(len(eco.entry_points) if eco else 0),
                     (", ".join(eco.test_frameworks) if eco else "none detected") or "none"))
    out.append(_card("dependencies", str(eco.dependency_total if eco else 0),
                     "%.0f%% pinned" % (eco.pin_ratio if eco else 0.0)))
    commits = result.git.commits if result.git and result.git.available else 0
    authors = result.git.author_count if result.git and result.git.available else 0
    out.append(_card("git history", human_int(commits),
                     "%d authors · %d days" % (authors, result.git.days_span if result.git else 0)))
    out.append("</div>")

    out.append("<h2>Sub-scores</h2><table>")
    for name in SCORE_WEIGHTS:
        value = result.scores.get(name, 0.0)
        out.append('<tr><td style="width:150px" class="mono">%s</td><td style="width:180px">%s</td>'
                   '<td class="num" style="width:60px">%.1f</td><td class="num" style="width:70px;color:#6b7280">%d%% weight</td>'
                   '<td style="color:#6b7280;font-size:12px">%s</td></tr>'
                   % (_esc(name), _svg_bar(value, 160, 9, _grade_colour(value)),
                      value, SCORE_WEIGHTS[name], _esc(SUBSCORE_HINTS.get(name, ""))))
    out.append("</table>")

    out.append("<h2>Language mix</h2><div style=\"display:flex;gap:28px;align-items:center\">")
    top_langs = langs[:6]
    mix = [(s.name, pct(s.code, result.code_lines)) for s in top_langs]
    out.append(_svg_donut(mix))
    out.append('<table style="flex:1">')
    for stat in top_langs:
        out.append('<tr><td><span class="dot" style="background:%s"></span>%s</td>'
                   '<td class="num mono">%s</td><td class="num" style="color:#6b7280">%.1f%%</td>'
                   '<td class="num" style="color:#6b7280">%d files</td></tr>'
                   % (LANGUAGE_COLOURS.get(stat.name, "#64748b"), _esc(stat.name),
                      human_int(stat.code), pct(stat.code, result.code_lines), stat.files))
    out.append("</table></div>")

    out.append("<h2>Top findings</h2>")
    out.append('<div class="legend">')
    for level in ("high", "medium", "low", "info"):
        out.append('<span><span class="dot" style="background:%s"></span>%d %s</span>'
                   % (SEVERITY_COLOURS[level], sev[level], level))
    out.append("</div><table style=\"margin-top:10px\"><tr><th>sev</th><th>rule</th><th>finding</th>"
               "<th>location</th></tr>")
    for finding in result.findings[:top]:
        colour = SEVERITY_COLOURS.get(finding.severity, "#94a3b8")
        out.append('<tr><td><span class="pill" style="background:%s22;color:%s">%s</span></td>'
                   '<td class="rule">%s</td><td>%s<div style="color:#6b7280;font-size:12px">%s</div></td>'
                   '<td class="path">%s</td></tr>'
                   % (colour, colour, _esc(finding.severity.upper()), _esc(finding.rule),
                      _esc(finding.title), _esc(finding.detail),
                      _esc((finding.path or "-") + (":" + str(finding.line) if finding.line else ""))))
    out.append("</table>")
    if len(result.findings) > top:
        out.append('<div class="sub" style="margin-top:8px">%d more findings across %d rules</div>'
                   % (len(result.findings) - top, len(rule_frequency(result.findings))))

    out.append("<h2>Most frequent rules</h2><table><tr><th>rule</th><th>count</th><th>title</th></tr>")
    for rule_id, count, rule_title in rule_frequency(result.findings)[:8]:
        rule = RULES.get(rule_id)
        colour = SEVERITY_COLOURS.get(rule.severity if rule else "info", "#94a3b8")
        out.append('<tr><td class="rule">%s</td><td class="num"><span class="pill" style="background:%s22;color:%s">%d</span></td>'
                   '<td>%s</td></tr>' % (_esc(rule_id), colour, colour, count, _esc(rule_title)))
    out.append("</table>")

    if result.git and result.git.available and result.git.hotspots:
        git = result.git
        out.append("<h2>Churn hotspots</h2>")
        out.append('<div class="sub">commit count x file size · %d commits · %s to %s</div>'
                   % (git.commits, _esc(git.first_commit_date or "?"),
                      _esc(git.last_commit_date or "?")))
        out.append(_svg_histogram([c.commits for c in git.hotspots]) + "<table>")
        out.append("<tr><th>file</th><th>commits</th><th>LOC</th><th>churn score</th></tr>")
        for item in git.hotspots[:8]:
            out.append('<tr><td class="path">%s</td><td class="num">%d</td>'
                       '<td class="num">%s</td><td class="num">%.1f</td></tr>'
                       % (_esc(item.rel), item.commits, human_int(item.loc), item.score))
        out.append("</table>")

    if result.dead_files or result.cycles:
        out.append("<h2>Dependency graph</h2>")
        graph = result.graph
        if graph is not None:
            out.append('<div class="sub">%d modules parsed · %d internal imports · %d parse failures</div>'
                       % (graph.parsed, sum(len(v) for v in graph.edges.values()), graph.failed))
        if result.dead_files:
            out.append('<div style="margin-top:10px">Never imported (%d):</div><table>' % len(result.dead_files))
            for rel in result.dead_files[:8]:
                out.append('<tr><td class="path">%s</td></tr>' % _esc(rel))
            out.append("</table>")
        for cycle in result.cycles[:2]:
            out.append('<div class="path" style="margin-top:8px">cycle: %s</div>'
                       % _esc(" -> ".join(cycle)))

    out.append('<footer>Generated by repo-radar · %s · every number above was measured by this scan. '
               "</footer></div></body></html>" % _esc(stamp))
    return "\n".join(out)


def _card(key: str, value: str, meta: str) -> str:
    return ('<div class="card"><div class="k">%s</div><div class="v">%s</div>'
            '<div class="m">%s</div></div>' % (_esc(key), _esc(value), _esc(meta)))


def _verdict(result: ScanResult) -> str:
    sev = severity_counts(result.findings)
    if result.score >= 90:
        return "Production-ready: no high-severity findings."
    if result.score >= 80:
        return "Healthy with %d high-severity findings to tidy." % sev["high"]
    if result.score >= 70:
        return "Usable but under-documented: %d high-severity findings." % sev["high"]
    if result.score >= 60:
        return "Fragile: %d high-severity findings." % sev["high"]
    return "Risky: fix the high-severity findings before adding features."


def write_html(result: ScanResult, path, top: int = 10,
               title: str | None = None) -> int:
    """Write the dashboard and return its size in bytes."""
    from .utils import write_text
    payload = build_html(result, top=top, title=title)
    write_text(path, payload)
    return len(payload.encode("utf-8"))
