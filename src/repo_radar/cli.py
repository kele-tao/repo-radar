"""Command line interface: scan, explain, report, rules.

Exit codes (documented in the README):
  0  success
  1  quality gate failed (--fail-under) or repository unreadable
  2  usage error (bad arguments, missing path, bad output format)
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path

from . import __version__
from .config import load_config
from .explain import explain_file
from .findings import RULES
from .htmlreport import write_html
from .render import render_explain, render_scan
from .scan import collect
from .utils import color_enabled, human_size
from .walker import WalkOptions

PROG = "repo-radar"
DESCRIPTION = "Understand any codebase in 60 seconds: health score, risks, churn hotspots."


class UsageError(Exception):
    """Raised for bad user input; mapped to exit code 2."""


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser. Kept separate so tests can introspect it."""
    parser = argparse.ArgumentParser(
        prog=PROG,
        description=DESCRIPTION,
        epilog="Exit codes: 0 ok, 1 gate failed, 2 usage error.",
    )
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--no-colour", "--no-color", dest="no_colour", action="store_true",
                        default=argparse.SUPPRESS,
                        help="disable ANSI colour (NO_COLOR is honoured too)")
    common.add_argument("--colour", "--color", dest="colour", action="store_true",
                        default=argparse.SUPPRESS,
                        help="force ANSI colour, e.g. when piping into a screenshot")
    parser.add_argument("--no-colour", "--no-color", dest="no_colour", action="store_true",
                        default=False,
                        help="disable ANSI colour (NO_COLOR is honoured too)")
    parser.add_argument("--colour", "--color", dest="colour", action="store_true",
                        default=False,
                        help="force ANSI colour, e.g. when piping into a screenshot")
    sub = parser.add_subparsers(dest="command", metavar="command")

    p_scan = sub.add_parser("scan", parents=[common],
                        help="scan a repository and print the health report")
    p_scan.add_argument("path", nargs="?", default=".", help="directory to scan (default: .)")
    p_scan.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    p_scan.add_argument("--top", type=int, default=10, metavar="N",
                        help="number of findings to print (default: 10)")
    p_scan.add_argument("--fail-under", type=float, default=None, metavar="SCORE",
                        help="exit 1 when the health score is below SCORE")
    p_scan.add_argument("--ignore", action="append", default=[], metavar="PATTERN",
                        help="extra ignore pattern (repeatable), e.g. --ignore '*.min.js'")
    p_scan.add_argument("--no-git", action="store_true", help="skip git history collection")
    p_scan.add_argument("--quiet", action="store_true", help="print only the score line")

    p_explain = sub.add_parser("explain", parents=[common],
                        help="summarise one module's public API")
    p_explain.add_argument("file", help="source file to explain")
    p_explain.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    p_explain.add_argument("--root", default=None, metavar="DIR",
                           help="repository root used to shorten the printed path")

    p_report = sub.add_parser("report", parents=[common],
                        help="write a self-contained HTML dashboard")
    p_report.add_argument("path", nargs="?", default=".", help="directory to scan (default: .)")
    p_report.add_argument("--out", required=True, metavar="FILE.html",
                          help="output HTML path (required)")
    p_report.add_argument("--top", type=int, default=10, metavar="N",
                          help="findings to embed (default: 10)")
    p_report.add_argument("--title", default=None, help="dashboard title")
    p_report.add_argument("--ignore", action="append", default=[], metavar="PATTERN",
                          help="extra ignore pattern (repeatable)")
    p_report.add_argument("--no-git", action="store_true", help="skip git history collection")

    p_rules = sub.add_parser("rules", parents=[common],
                        help="list every rule with its severity and fix")
    p_rules.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    return parser


def configure_io() -> None:
    """Force UTF-8 on stdout/stderr so block characters survive Windows cp936."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        with contextlib.suppress(ValueError, OSError):  # closed or exotic streams
            reconfigure(encoding="utf-8", errors="replace")


_raw_argv: list[str] = []


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns the process exit code; never raises for user error."""
    global _raw_argv
    configure_io()
    argv = list(sys.argv[1:] if argv is None else argv)
    _raw_argv = argv
    parser = build_parser()
    args = parser.parse_args(argv)
    colour = (color_enabled(force=bool(getattr(args, "colour", False)))
              and not bool(getattr(args, "no_colour", False)))
    if not args.command:
        parser.print_help()
        return 2
    try:
        if args.command == "scan":
            return _cmd_scan(args, colour)
        if args.command == "explain":
            return _cmd_explain(args, colour)
        if args.command == "report":
            return _cmd_report(args, colour)
        if args.command == "rules":
            return _cmd_rules(args, colour)
    except UsageError as exc:
        sys.stderr.write(PROG + ": error: " + str(exc) + "\n")
        sys.stderr.write("Try '" + PROG + " --help' for usage.\n")
        return 2
    except FileNotFoundError as exc:
        sys.stderr.write(PROG + ": error: " + str(exc) + "\n")
        return 2
    except IsADirectoryError as exc:
        sys.stderr.write(PROG + ": error: " + str(exc) + "\n")
        return 2
    except KeyboardInterrupt:  # pragma: no cover - interactive only
        sys.stderr.write("\ninterrupted\n")
        return 130
    parser.print_help()
    return 2


def _resolve_dir(raw: str) -> Path:
    path = Path(raw).expanduser()
    if not path.exists():
        raise UsageError("no such directory: " + raw)
    if not path.is_dir():
        raise UsageError("expected a directory, got a file: " + raw
                         + " (did you mean 'explain " + raw + "'?)")
    return path


def _cmd_scan(args, colour: bool) -> int:
    root = _resolve_dir(args.path)
    configuration = load_config(root, tuple(args.ignore), args.fail_under,
                                args.top if "--top" in _raw_argv else None)
    if args.top < 0:
        raise UsageError("--top must be >= 0")
    options = WalkOptions(ignore=configuration.ignore)
    result = collect(root, options, with_git=not args.no_git, top=args.top)
    if not configuration.sources:
        configuration.sources.append("defaults")
    for warning in configuration.warnings:
        sys.stderr.write(PROG + ": config: " + warning + "\n")
    if args.json:
        payload = result.as_dict(top=args.top)
        payload["config"] = configuration.as_dict()
        sys.stdout.write(json.dumps(payload, indent=2, sort_keys=False) + "\n")
    elif args.quiet:
        sys.stdout.write("%.1f %s\n" % (result.score, result.grade))
    else:
        sys.stdout.write(render_scan(result, top=args.top,
                                     show_git=not args.no_git, colour=colour) + "\n")
    gate = configuration.fail_under
    if gate is not None and result.score < gate:
        sys.stderr.write(PROG + ": score %.1f is below --fail-under %.1f\n"
                         % (result.score, gate))
        return 1
    return 0


def _cmd_explain(args, colour: bool) -> int:
    path = Path(args.file).expanduser()
    if not path.exists():
        raise UsageError("no such file: " + args.file)
    root = Path(args.root).expanduser() if args.root else None
    if root is not None and not root.is_dir():
        raise UsageError("--root must be an existing directory: " + args.root)
    explanation = explain_file(path, root)
    if args.json:
        sys.stdout.write(json.dumps(explanation.as_dict(), indent=2) + "\n")
    else:
        sys.stdout.write(render_explain(explanation, colour=colour) + "\n")
    return 0


def _cmd_report(args, colour: bool) -> int:
    root = _resolve_dir(args.path)
    out = Path(args.out).expanduser()
    if out.suffix.lower() not in {".html", ".htm"}:
        raise UsageError("--out must end in .html or .htm (got '" + out.suffix + "')")
    if out.exists() and out.is_dir():
        raise UsageError("--out points at a directory: " + str(out))
    configuration = load_config(root, tuple(args.ignore), None,
                                args.top if "--top" in _raw_argv else None)
    options = WalkOptions(ignore=configuration.ignore)
    result = collect(root, options, with_git=not args.no_git, top=args.top)
    size = write_html(result, out, top=args.top, title=args.title)
    sys.stdout.write(render_scan(result, top=min(args.top, 5),
                                 show_git=not args.no_git, colour=colour) + "\n")
    sys.stdout.write("\n" + PROG + ": wrote " + str(out) + " (" + human_size(size) + ")\n")
    return 0


def _cmd_rules(args, colour: bool) -> int:
    if args.json:
        payload = [{"id": r.id, "severity": r.severity, "title": r.title, "fix": r.fix}
                   for r in sorted(RULES.values(), key=lambda r: r.id)]
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        return 0
    use = colour
    for rule in sorted(RULES.values(), key=lambda r: r.id):
        head = rule.id + "  " + rule.severity.upper().ljust(6) + "  " + rule.title
        if use:
            colour_code = {"high": "31", "medium": "33", "low": "34", "info": "2"}[rule.severity]
            head = "\x1b[" + colour_code + "m" + head + "\x1b[0m"
        sys.stdout.write(head + "\n  -> " + rule.fix + "\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
