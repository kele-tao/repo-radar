"""repo-radar: understand any codebase in 60 seconds, from the terminal.

Public API::

    from repo_radar import scan, explain_file, build_html

    result = scan(".")
    print(result.score, result.grade)  # radar:ignore
"""

from __future__ import annotations

from .explain import Explanation, explain_file, explain_python
from .findings import RULES, Finding, Rule, scan_text
from .htmlreport import build_html, write_html
from .render import render_explain, render_scan
from .scan import ScanResult, collect, compute_scores
from .scoring import grade_for, weighted_score

__version__ = "1.0.0"

__all__ = [
    "RULES",
    "Explanation",
    "Finding",
    "Rule",
    "ScanResult",
    "build_html",
    "collect",
    "compute_scores",
    "explain_file",
    "explain_python",
    "grade_for",
    "render_explain",
    "render_scan",
    "scan",
    "scan_text",
    "weighted_score",
    "write_html",
]


def scan(path=".", ignore=(), with_git: bool = True, top: int = 10) -> ScanResult:
    """Scan a directory and return the full result. The library entry point."""
    from pathlib import Path

    from .walker import WalkOptions

    root = Path(path)
    options = WalkOptions(ignore=tuple(ignore))
    return collect(root, options, with_git=with_git, top=top)
