"""Benchmark: repo-radar against generated trees of 500, 2000 and 5000 files.

Writes benchmarks/results.json and refreshes the README performance table
between the <!-- BENCH:START --> / <!-- BENCH:END --> markers. The tree is
rebuilt in a temporary directory on every run, so the numbers are reproducible
anywhere and nothing large is committed.

    python benchmarks/run.py            # sizes 500, 2000, 5000
    python benchmarks/run.py --quick    # a single 2000-file run
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from repo_radar.scan import collect  # noqa: E402
from repo_radar.walker import WalkOptions  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results.json"
README = ROOT / "README.md"
START = "<!-- BENCH:START -->"
END = "<!-- BENCH:END -->"

MODULE = '"""Module {index}: generated for the repo-radar benchmark."""' + chr(10) + chr(10) +     "from __future__ import annotations" + chr(10) + chr(10) +     "from .mod_{previous:04d} import helper_{previous:04d}" + chr(10) + chr(10) + chr(10) +     "class Service{index}:" + chr(10) +     '    """A tiny generated service."""' + chr(10) + chr(10) +     "    def __init__(self, value: int = {index}) -> None:" + chr(10) +     "        self.value = value" + chr(10) + chr(10) +     "    def compute(self) -> int:" + chr(10) +     "        if self.value % 2 == 0:" + chr(10) +     "            return self.value * 2" + chr(10) +     "        return self.value + 1" + chr(10) + chr(10) + chr(10) +     "def helper_{index:04d}(value: int) -> int:" + chr(10) +     '    """Add one, used by the next module in the chain."""' + chr(10) +     "    return value + 1" + chr(10)

TEST = '"""Generated test module {index}."""' + chr(10) + chr(10) + chr(10) +     "def test_helper_{index:04d}() -> None:" + chr(10) +     "    assert {index} + 1 == {index} + 1" + chr(10)


def build_tree(target: Path, files: int) -> None:
    """Create a synthetic repository with an import chain and a realistic mix."""
    package = target / "src" / "generated"
    package.mkdir(parents=True, exist_ok=True)
    (target / "README.md").write_text("# generated" + chr(10) * 2 +
                                      "Benchmark fixture." + chr(10), encoding="utf-8")
    (target / "LICENSE").write_text("MIT License" + chr(10), encoding="utf-8")
    (target / "pyproject.toml").write_text(
        '[project]' + chr(10) + 'name = "generated"' + chr(10) + 'version = "1.0"' + chr(10) +
        'dependencies = ["requests==2.31.0"]' + chr(10), encoding="utf-8")
    (package / "__init__.py").write_text("", encoding="utf-8")
    modules = max(1, files - 5)
    for index in range(modules):
        previous = max(0, index - 1)
        body = MODULE.format(index=index, previous=previous)
        if index % 5 == 0:
            body += (chr(10) * 2 + "def unused_%04d() -> None:" % index +
                     chr(10) + "    return None" + chr(10))
        (package / ("mod_%04d.py" % index)).write_text(body, encoding="utf-8")
    tests = target / "tests"
    tests.mkdir(exist_ok=True)
    for index in range(min(50, modules)):
        (tests / ("test_mod_%04d.py" % index)).write_text(TEST.format(index=index),
                                                          encoding="utf-8")


def measure(target: Path, repeats: int) -> dict:
    """Scan the tree *repeats* times and keep both median and best timings."""
    samples = []
    result = None
    for _ in range(max(1, repeats)):
        started = time.perf_counter()
        result = collect(target, WalkOptions(), with_git=False)
        samples.append((time.perf_counter() - started) * 1000.0)
    if result is None:  # pragma: no cover - measure() always scans at least once
        raise RuntimeError("measure() produced no result")
    return {
        "files": result.total_files,
        "code_lines": result.code_lines,
        "median_ms": round(statistics.median(samples), 1),
        "best_ms": round(min(samples), 1),
        "score": result.score,
        "findings": len(result.findings),
    }


def table(rows: list[dict]) -> str:
    """Markdown performance table, in the exact shape the README quotes."""
    lines = [
        "| Files | Code lines | Median scan | Best scan | Files/s | Findings |",
        "| ----: | ---------: | ----------: | --------: | ------: | -------: |",
    ]
    for row in rows:
        per_second = row["files"] / (row["median_ms"] / 1000.0) if row["median_ms"] else 0.0
        lines.append("| %d | %s | %s ms | %s ms | %s | %d |" % (
            row["files"], format(row["code_lines"], ","), row["median_ms"],
            row["best_ms"], format(round(per_second), ","), row["findings"]))
    return chr(10).join(lines)


def update_readme(rows: list[dict]) -> None:
    """Refresh the table between the README markers, if they exist."""
    if not README.exists():
        return
    text = README.read_text(encoding="utf-8")
    if START not in text or END not in text:
        return
    head, _, rest = text.partition(START)
    _, _, tail = rest.partition(END)
    note = (chr(10) * 2 + "Measured with `python benchmarks/run.py` on " +
            (platform.system() or "unknown") + ", Python " +
            platform.python_version() + ". Every row scans a tree generated in a "
            "temporary directory with git history disabled and reports the median "
            "of repeated scans (three by default). The last row is a single 5 MB "
            "corpus of unusually large modules: the worst case for the per-file rules.")
    README.write_text(head + START + chr(10) + table(rows) + note + chr(10) + END + tail,
                      encoding="utf-8")


LARGE_BODY = '"""Large generated module."""' + chr(10) * 2 + chr(10).join(
    "def fn_%d(x):" % i + chr(10) + "    return x + %d" % i for i in range(200))


def measure_corpus(target_mb: float, repeats: int) -> dict:
    """Build a corpus of roughly *target_mb* megabytes and scan it."""
    with tempfile.TemporaryDirectory(prefix="radar-corpus-") as raw:
        root = Path(raw) / "corpus"
        root.mkdir()
        (root / "README.md").write_text("# corpus" + chr(10) * 50, encoding="utf-8")
        payload = LARGE_BODY * 10
        index = 0
        while True:
            (root / ("mod_%03d.py" % index)).write_text(payload, encoding="utf-8")
            index += 1
            size = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
            if size >= target_mb * 1024 * 1024 or index > 400:
                break
        actual = size / (1024 * 1024)
        row = measure(root, repeats)
        row["mb"] = round(actual, 2)
        return row


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Benchmark repo-radar.")
    parser.add_argument("--quick", action="store_true", help="single 2000-file scan")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--corpus-mb", type=float, default=5.0,
                        help="size of the single-corpus test (default 5 MB)")
    args = parser.parse_args(argv)
    sizes = [2000] if args.quick else [500, 2000, 5000]
    rows = []
    for size in sizes:
        with tempfile.TemporaryDirectory(prefix="radar-bench-") as raw:
            target = Path(raw) / "repo"
            build_tree(target, size)
            row = measure(target, args.repeats)
            row["requested_files"] = size
            rows.append(row)
            print("%5d requested -> %5d files, %8s lines, %7.1f ms median" % (
                size, row["files"], format(row["code_lines"], ","), row["median_ms"]))
            shutil.rmtree(target, ignore_errors=True)
    corpus = measure_corpus(args.corpus_mb, args.repeats)
    print("%.2f MB corpus -> %d files, %s lines, %.0f ms median" % (
        corpus["mb"], corpus["files"], format(corpus["code_lines"], ","),
        corpus["median_ms"]))
    RESULTS.write_text(json.dumps(
        {"rows": rows, "corpus": corpus, "python": platform.python_version(),
         "platform": platform.system()}, indent=2) + chr(10), encoding="utf-8")
    update_readme([*rows, {
        "files": corpus["files"], "code_lines": corpus["code_lines"],
        "median_ms": corpus["median_ms"], "best_ms": corpus["best_ms"],
        "findings": corpus["findings"]}])
    print(table(rows))
    print("wrote %s" % RESULTS)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
