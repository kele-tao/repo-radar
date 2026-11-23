"""Git-aware history signals, collected through the git binary (no libgit2).

Everything degrades cleanly: no git installed, no .git directory, shallow clone
and detached HEAD all produce a partial section rather than a traceback.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

GIT_TIMEOUT = 20
MAX_HISTORY_COMMITS = 5000


@dataclass
class Churn:
    """How often a file changed and how big it is now."""

    rel: str
    commits: int
    loc: int = 0

    @property
    def score(self) -> float:
        """Churn x size: a file that is big and always changing is the hotspot."""
        return round(self.commits * (1.0 + (self.loc / 100.0) ** 0.5), 2)


@dataclass
class GitInfo:
    """Result of reading a repository's history."""

    available: bool = False
    reason: str = ""
    commits: int = 0
    authors: list[tuple[str, int]] = field(default_factory=list)
    branch: str = ""
    first_commit_date: str | None = None
    last_commit_date: str | None = None
    days_span: int = 0
    hotspots: list[Churn] = field(default_factory=list)
    commit_subjects: list[str] = field(default_factory=list)
    uncommitted_changes: int = 0

    @property
    def author_count(self) -> int:
        return len(self.authors)

    @property
    def top_author_share(self) -> float:
        if not self.authors or not self.commits:
            return 0.0
        return round(100.0 * self.authors[0][1] / max(1, sum(c for _, c in self.authors)), 1)

    def as_dict(self) -> dict:
        return {
            "available": self.available,
            "reason": self.reason,
            "commits": self.commits,
            "authors": [{"name": n, "commits": c} for n, c in self.authors],
            "branch": self.branch,
            "first_commit": self.first_commit_date,
            "last_commit": self.last_commit_date,
            "days_span": self.days_span,
            "uncommitted_changes": self.uncommitted_changes,
            "top_churn": [{"file": c.rel, "commits": c.commits, "loc": c.loc,
                           "score": c.score} for c in self.hotspots],
        }


def _run(root: Path, args: list[str]) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, timeout=GIT_TIMEOUT, check=False,
            env={"PATH": _path_env(), "GIT_TERMINAL_PROMPT": "0",
                 "LC_ALL": "C", "HOME": str(root)},
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", "replace")


def _path_env() -> str:
    import os
    return os.environ.get("PATH", "")


def collect_git(root: Path, loc_by_file: dict[str, int], top: int = 10,
                history: int = 200) -> GitInfo:
    """Read commits, authors, span and churn hotspots for *root*."""
    info = GitInfo()
    if not (root / ".git").exists():
        info.reason = "not a git repository"
        return info
    if _run(root, ["rev-parse", "--is-inside-work-tree"]) is None:
        info.reason = "git binary not found or repository unreadable"
        return info
    info.available = True
    info.branch = (_run(root, ["rev-parse", "--abbrev-ref", "HEAD"]) or "").strip()
    count_raw = _run(root, ["rev-list", "--count", "--all"])
    if count_raw and count_raw.strip().isdigit():
        info.commits = int(count_raw.strip())
    if info.commits == 0:
        info.reason = "repository has no commits yet"
        return info

    dates = _run(root, ["log", "--format=%aI|%cI", "-n", "1"]) or ""
    if dates.strip():
        first_line = dates.splitlines()[0]
        _authored, _, committed = first_line.partition("|")
        info.last_commit_date = committed[:10] or None
    oldest = _run(root, ["log", "--reverse", "--format=%aI"]) or ""
    if oldest.strip():
        info.first_commit_date = oldest.strip().splitlines()[0][:10]
        if info.first_commit_date and info.last_commit_date:
            from datetime import date
            try:
                a = date.fromisoformat(info.first_commit_date)
                b = date.fromisoformat(info.last_commit_date)
                info.days_span = max(0, (b - a).days)
            except ValueError:
                info.days_span = 0

    authors_raw = _run(root, ["shortlog", "-sne", "HEAD"]) or ""
    authors: list[tuple[str, int]] = []
    for line in authors_raw.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) != 2:
            continue
        try:
            number = int(parts[0].strip())
        except ValueError:
            continue
        name = parts[1].split("<")[0].strip() or parts[1].strip()
        authors.append((name, number))
    authors.sort(key=lambda a: (-a[1], a[0]))
    info.authors = authors

    subjects = _run(root, ["log", "--format=%s", "-n", "12"]) or ""
    info.commit_subjects = [s for s in subjects.splitlines() if s.strip()]

    churn_raw = _run(root, [
        "log", "--format=", "--name-only", "-n", str(MAX_HISTORY_COMMITS),
        "--no-renames", "--", ".",
    ]) or ""
    counts: dict[str, int] = {}
    for line in churn_raw.splitlines():
        rel = line.strip()
        if not rel:
            continue
        counts[rel] = counts.get(rel, 0) + 1
    churn = [Churn(rel=rel, commits=n, loc=loc_by_file.get(rel, 0))
             for rel, n in counts.items()]
    churn.sort(key=lambda c: (-c.score, c.rel))
    info.hotspots = churn[:top]

    status = _run(root, ["status", "--porcelain"]) or ""
    info.uncommitted_changes = len([line for line in status.splitlines() if line.strip()])
    _ = history
    return info


def history_score(git: GitInfo) -> float:
    """0-100 history-health sub-score (used by the composite radar score)."""
    if not git.available or git.commits == 0:
        return 40.0
    score = 55.0
    if git.commits >= 100:
        score += 10.0
    elif git.commits >= 20:
        score += 5.0
    if git.author_count >= 2:
        score += 5.0
    span_factor = 1.0
    if git.days_span >= 30:
        span_factor = 1.1
    score *= span_factor
    if git.top_author_share > 85 and git.commits > 20:
        score -= 12.0
    if git.uncommitted_changes > 20:
        score -= 5.0
    return max(0.0, min(100.0, round(score, 1)))
