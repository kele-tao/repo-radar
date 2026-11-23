"""Terminal renderer for the scan and explain commands.

The renderer is pure: it takes a ScanResult and returns a string. Numeric output
is stable across runs, so the README transcript and the screenshot agree.
"""

from __future__ import annotations

from .explain import Explanation
from .findings import Finding
from .scan import ScanResult
from .scoring import SCORE_WEIGHTS
from .utils import Style, bar, human_int, human_size, pad, pct, truncate

WIDTH = 74


def _header(text: str, style: Style) -> str:
    return style.bold(text) + "\n" + style.dim("-" * WIDTH)


def _verdict(result: ScanResult) -> str:
    sev = result.severity
    if result.score >= 90:
        base = "Production-ready. Nothing here would block a first PR."
    elif result.score >= 80:
        base = "Healthy. A couple of small fixes and it is production-ready."
    elif result.score >= 70:
        base = "Usable but under-documented. Fix the top findings below."
    elif result.score >= 60:
        base = "Fragile: a new contributor will need a guide."
    else:
        base = "Risky. The top findings should be fixed before adding features."
    if sev["high"]:
        base += " %d high-severity finding%s." % (sev["high"], "" if sev["high"] == 1 else "s")
    return base


def render_scan(result: ScanResult, top: int = 10, show_git: bool = True,
                colour: bool = True) -> str:
    """Render the full terminal report for a scan."""
    style = Style(colour)
    out: list[str] = []
    eco = result.ecosystem
    shown = result.display_root or str(result.root)
    if shown in {".", ""}:
        shown = "."
    out.append(style.bold("repo-radar") + "  " + style.cyan(shown))
    out.append("")

    out.append(_header("REPO HEALTH", style))
    out.append("  " + style.bold("%d/100" % round(result.score))
               + "  grade " + style.bold(result.grade) + "   "
               + style.green(bar(result.score, 28)))
    out.append("  " + style.dim(_verdict(result)))
    out.append("")

    for name in SCORE_WEIGHTS:
        value = result.scores.get(name, 0.0)
        out.append("  " + pad(name, 13) + style.green(bar(value, 18)) + " "
                   + style.bold("%5.1f" % value)
                   + style.dim("   weight %2d%%" % SCORE_WEIGHTS[name]))
    out.append("")

    sev = result.severity
    out.append(_header("FINDINGS", style))
    out.append("  " + style.red("%d high" % sev["high"]) + style.dim(" · ")
               + style.yellow("%d medium" % sev["medium"]) + style.dim(" · ")
               + style.cyan("%d low" % sev["low"]) + style.dim(" · ")
               + style.dim("%d info" % sev["info"])
               + style.dim("   (%d total)" % len(result.findings)))
    shown = result.top_findings(top)
    for finding in shown:
        out.append("  " + _format_finding(finding, style))
    if len(result.findings) > len(shown):
        out.append(style.dim("  ... %d more findings (use --top N to widen)"
                             % (len(result.findings) - len(shown))))
    out.append("")

    out.append(_header("CODEBASE", style))
    langs = sorted(result.languages.values(), key=lambda s: (-s.code, s.name))
    top_langs = [s for s in langs if s.code > 0][:6]
    for stat in top_langs:
        share = pct(stat.code, result.code_lines)
        out.append("  " + pad(stat.name, 14) + style.bold("%7s" % human_int(stat.code))
                   + style.dim(" code  %5.1f%%  %s" % (share, bar(share, 14))))
    other = len([s for s in langs if s.code > 0]) - len(top_langs)
    if other > 0:
        out.append(style.dim("  + %d more languages" % other))
    out.append("  " + style.dim("%s files · %s · %s code lines · %s comment lines" % (
        human_int(result.total_files), human_size(result.total_bytes),
        human_int(result.code_lines), human_int(result.comment_lines))))

    if eco:
        bits: list[str] = []
        if eco.entry_points:
            bits.append("entry: " + ", ".join(sorted({k for _, k in eco.entry_points})[:3]))
        if eco.test_frameworks:
            bits.append("tests: " + ", ".join(eco.test_frameworks))
        if eco.ci_systems:
            bits.append("ci: " + ", ".join(sorted(set(eco.ci_systems))))
        if eco.manifests:
            bits.append("deps: %d (%s pinned)"
                        % (eco.dependency_total, "%.0f%%" % eco.pin_ratio))
        if bits:
            out.append("  " + style.dim(" · ".join(bits)))
    out.append("")

    if show_git and result.git and result.git.available:
        out.append(_header("HISTORY", style))
        git = result.git
        out.append("  " + style.dim("%s commits · %s authors · %s -> %s (%s days) · branch %s"
                   % (human_int(git.commits), git.author_count,
                      git.first_commit_date or "?", git.last_commit_date or "?",
                      human_int(git.days_span), git.branch or "?")))
        if git.authors:
            top_authors = ", ".join("%s (%d)" % (name, count) for name, count in git.authors[:3])
            out.append("  " + style.dim("top authors: " + top_authors))
        churn = [c for c in git.hotspots if c.commits > 0][:5]
        if churn:
            out.append("  " + style.bold("churn hotspots") + style.dim("  (commits x size)"))
            for item in churn:
                out.append("  " + pad(truncate(item.rel, 40), 42) + style.bold("%4d" % item.commits)
                           + style.dim(" commits  %5d LOC  score %.1f"
                                       % (item.loc, item.score)))
        out.append("")

    graph = result.graph
    if graph is not None:
        out.append(_header("GRAPH", style))
        nodes = len(set(graph.edges) | set(graph.reverse))
        edges = sum(len(v) for v in graph.edges.values())
        out.append("  " + style.dim("%d modules in graph · %d internal imports · %d dead-code smells · %d cycle(s)"
                   % (nodes, edges, len(result.dead_files), len(result.cycles))))
        for rel in result.dead_files[:3]:
            out.append("  " + style.yellow("never imported") + "  " + rel)
        if result.cycles:
            out.append("  " + style.yellow("import cycle") + "  "
                       + " -> ".join(result.cycles[0][:4]))
        out.append("")

    out.append(style.dim("scan finished in %.0f ms · %d files read, %d skipped"
                         % (result.duration_ms, result.total_files, len(result.skipped))))
    return "\n".join(out)


def _format_finding(finding: Finding, style: Style) -> str:
    colour = {"high": style.red, "medium": style.yellow, "low": style.cyan,
              "info": style.dim}.get(finding.severity, style.dim)
    label = colour("%-6s" % finding.severity.upper())
    location = finding.path or "-"
    if finding.line:
        location += ":" + str(finding.line)
    title = truncate(finding.title, 56)
    return (label + " " + style.dim(finding.rule) + "  " + title + "\n"
            + style.dim("        " + truncate(location, 28).ljust(29)
                        + truncate(finding.detail, 40)))


def render_explain(exp: Explanation, colour: bool = True) -> str:
    """Render the explain command's report for one module."""
    style = Style(colour)
    out: list[str] = []
    out.append(style.bold("repo-radar") + "  explain  " + style.cyan(exp.path))
    out.append("")
    out.append(_header("MODULE", style))
    out.append("  " + exp.summary)
    if exp.parse_error:
        out.append("  " + style.red("parse error: " + exp.parse_error))
    out.append("  " + style.dim("%s · %s lines · %s code · %s comments · %s blank"
                                % (exp.language, human_int(exp.lines), human_int(exp.code),
                                   human_int(exp.comments), human_int(exp.blanks))))
    out.append("  " + style.dim("complexity %d · hardest %s (%d branch points) · docstring coverage %.0f%%"
                                % (exp.complexity, exp.hardest_function or "-",
                                   exp.max_function_branches, exp.docstring_coverage)))
    if exp.docstring:
        first = exp.docstring.strip().splitlines()[0]
        out.append("  " + style.dim("docstring: " + truncate(first, 58)))
    out.append("")

    out.append(_header("PUBLIC API", style))
    if not exp.symbols:
        out.append("  " + style.dim("no public symbols detected"))
    for symbol in exp.symbols:
        marker = style.green("*") if not symbol.name.startswith("_") else style.dim("-")
        kind = style.dim("%-9s" % symbol.kind)
        doc = " ".join(symbol.doc.split())[:60]
        out.append("  " + marker + " " + kind + pad(symbol.name, 22)
                   + style.dim(("L%d" % symbol.line).rjust(6)) + "  " + doc)
    if exp.imports:
        out.append("")
        out.append(_header("IMPORTS", style))
        out.append("  " + style.dim(truncate(", ".join(exp.imports), 68)))
    return "\n".join(out)
