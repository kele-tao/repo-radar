"""Rebuild examples/demo-repo from the committed seed and history bundle.

Why a bundle: the demo repository must ship *with* a real git history, and a
nested '.git' directory cannot be committed inside this repository (git turns
the directory into a gitlink). Instead the history is committed as a git bundle
and materialised on demand:

    python examples/build_demo_repo.py          # rebuild bundle + attach history
    python examples/build_demo_repo.py --clean  # detach .git before committing

Both the tree and the commit timestamps are deterministic, so regenerating the
bundle twice gives the same object ids.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
DEMO = HERE / "demo-repo"
BUNDLE = HERE / "demo_history.bundle"
SEED = HERE / "demo_files.json"

AUTHORS = [
    ("Mira Chen", "mira@example.com"),
    ("Tomas Oliveira", "tomas@example.com"),
    ("Priya Raman", "priya@example.com"),
    ("Jonas Weber", "jonas@example.com"),
    ("Aiko Tanaka", "aiko@example.com"),
    ("Sam Okafor", "sam@example.com"),
]

# How many commits touch each file. pricing.py is the deliberate hotspot.
CHURN_WEIGHTS = {
    "src/pulse/pricing.py": 22,
    "src/pulse/app.py": 14,
    "src/pulse/store.py": 9,
    "README.md": 8,
    "src/pulse/report.py": 7,
    "tests/test_pricing.py": 7,
    "tests/test_store.py": 4,
    "web/src/app.js": 6,
    "web/src/cart.js": 4,
    "cmd/agent/main.go": 3,
    "docs/architecture.md": 3,
    "src/pulse/legacy_exporter.py": 2,
    "scripts/backfill.py": 2,
}

NEWLINE = chr(10)


def force_rmtree(path: Path) -> None:
    """Remove a tree even when git left read-only pack files behind (Windows)."""
    def on_error(func, target, _exc):
        try:
            os.chmod(target, 0o700)
            func(target)
        except OSError:
            pass

    if path.exists():
        shutil.rmtree(path, onexc=on_error)


def git(args: list[str], cwd: Path, env: dict | None = None) -> str:
    proc = subprocess.run(["git", *args], cwd=str(cwd), env=env, check=True,
                          capture_output=True, text=True, encoding="utf-8")
    return proc.stdout


def rewrite(path: Path, addition: str) -> None:
    text = path.read_text(encoding="utf-8")
    path.write_text(text + addition, encoding="utf-8")


def build_history(work: Path, files: dict[str, str]) -> int:
    git(["init", "-q", "-b", "main", str(work)], REPO_ROOT)
    git(["config", "user.name", AUTHORS[0][0]], work)
    git(["config", "user.email", AUTHORS[0][1]], work)
    git(["config", "commit.gpgsign", "false"], work)
    for path, content in files.items():
        target = work / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    env = dict(os.environ,
               GIT_AUTHOR_DATE="2024-01-05T10:00:00+00:00",
               GIT_COMMITTER_DATE="2024-01-05T10:00:00+00:00")
    git(["add", "-A"], work, env)
    git(["commit", "-q", "-m", "chore: initial import of pulse-api"], work, env)

    sequence: list[str] = []
    for path in sorted(CHURN_WEIGHTS):
        sequence.extend([path] * CHURN_WEIGHTS[path])

    for step, path in enumerate(sequence):
        name, email = AUTHORS[step % len(AUTHORS)]
        month = 2 + (step // 12) % 10
        day = 1 + step % 27
        stamp = "2024-%02d-%02dT09:%02d:00+00:00" % (month, day, step % 60)
        env = dict(os.environ, GIT_AUTHOR_NAME=name, GIT_AUTHOR_EMAIL=email,
                   GIT_COMMITTER_NAME=name, GIT_COMMITTER_EMAIL=email,
                   GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp)
        target = work / path
        if path.endswith(".py"):
            addition = NEWLINE + "# revision %d: %s" % (step + 2, name) + NEWLINE
        elif path.endswith(".md"):
            addition = NEWLINE + "Revision %d by %s." % (step + 2, name) + NEWLINE
        else:
            addition = NEWLINE
        rewrite(target, addition)
        git(["add", "-A"], work, env)
        git(["commit", "-q", "-m", "%s: touch %s" % (name.split()[0].lower(), path)],
            work, env)
    return len(sequence) + 1


def build_bundle(files: dict[str, str]) -> None:
    with tempfile.TemporaryDirectory(prefix="radar-demo-") as raw:
        work = Path(raw) / "demo-repo"
        work.mkdir()
        commits = build_history(work, files)
        if BUNDLE.exists():
            BUNDLE.unlink()
        git(["bundle", "create", str(BUNDLE), "--all"], work)
        print("wrote %s (%d commits, %d bytes)" % (BUNDLE, commits, BUNDLE.stat().st_size))


def materialise(files: dict[str, str]) -> None:
    """Write the seed tree, then attach the real history from the bundle.

    The tree is committed as ordinary files (so GitHub renders it); only the
    '.git' directory is rebuilt locally, which is why it stays out of git.
    """
    DEMO.mkdir(parents=True, exist_ok=True)
    for path, content in files.items():
        target = DEMO / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="radar-demo-git-") as raw:
        clone = Path(raw) / "clone"
        git(["clone", "-q", str(BUNDLE), str(clone)], REPO_ROOT)
        force_rmtree(DEMO / ".git")
        shutil.copytree(clone / ".git", DEMO / ".git")
    git(["remote", "remove", "origin"], DEMO)
    git(["reset", "-q", "--hard", "HEAD"], DEMO)
    print("materialised %s with %d commits" % (DEMO, commit_count()))


def commit_count() -> int:
    out = git(["rev-list", "--count", "HEAD"], DEMO)
    return int(out.strip() or 0)


def clean() -> None:
    """Drop the local .git so the tree can be committed as plain files."""
    if (DEMO / ".git").exists():
        force_rmtree(DEMO / ".git")
        print("removed %s/.git (history stays in %s)" % (DEMO.name, BUNDLE.name))
    else:
        print("no local git directory in %s" % DEMO)


def main(argv: list[str]) -> int:
    if "--clean" in argv:
        clean()
        return 0
    files = json.loads(SEED.read_text(encoding="utf-8"))
    if "--bundle-only" not in argv:
        DEMO.mkdir(parents=True, exist_ok=True)
    build_bundle(files)
    materialise(files)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
