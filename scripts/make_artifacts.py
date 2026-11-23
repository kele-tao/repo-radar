"""Regenerate every committed artifact from the current source.

Runs the real CLI (never hand-written output) and the provided screenshot
helpers, then prints the size of each file so a reviewer can verify.

    python scripts/make_artifacts.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT.parent / ".tools"
PY = sys.executable
ARTIFACTS = [
    ("docs/dashboard.html", [PY, "-m", "repo_radar", "report", "examples/demo-repo",
                             "--out", "docs/dashboard.html", "--top", "10",
                             "--title", "repo-radar"]),
    ("docs/dashboard.png", [PY, str(TOOLS / "screenshot.py"), "--html",
                            "docs/dashboard.html", "--out", "docs/dashboard.png",
                            "--full-page"]),
    ("docs/screenshot.png", [PY, str(TOOLS / "term_screenshot.py"), "--cmd",
                             "python -m repo_radar scan examples/demo-repo --top 8 --colour",
                             "--out", "docs/screenshot.png", "--title",
                             "repo-radar scan", "--cwd", ".", "--max-lines", "46"]),
    ("benchmarks/results.json", [PY, "benchmarks/run.py"]),
]


def main() -> int:
    for target, command in ARTIFACTS:
        print("+", " ".join(command[1:]))
        proc = subprocess.run(command, cwd=str(ROOT), text=True,
                              capture_output=True, encoding="utf-8", errors="replace")
        if proc.returncode != 0:
            sys.stderr.write(proc.stdout + proc.stderr)
            return proc.returncode
        path = ROOT / target
        size = path.stat().st_size if path.exists() else 0
        print("  -> %s (%d bytes)" % (target, size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
