"""Git history collection, including the no-git and tiny-repo paths."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from repo_radar.gitinfo import GitInfo, collect_git, history_score
from tests.conftest import write


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True,
                   capture_output=True, text=True, encoding="utf-8")


@pytest.fixture
def repo_with_history(tmp_path: Path) -> Path:
    write(tmp_path, "app.py", "x = 1\n")
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.name", "Test User")
    git(tmp_path, "config", "user.email", "test@example.com")
    git(tmp_path, "config", "commit.gpgsign", "false")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "initial")
    write(tmp_path, "app.py", "x = 2\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "second")
    return tmp_path


def test_missing_git_directory_is_reported(tmp_path: Path) -> None:
    info = collect_git(tmp_path, {})
    assert info.available is False
    assert "git" in info.reason


def test_repository_history_is_read(repo_with_history: Path) -> None:
    info = collect_git(repo_with_history, {"app.py": 1})
    assert info.available is True
    assert info.commits == 2
    assert info.author_count == 1
    assert info.branch == "main"
    assert info.hotspots
    assert info.hotspots[0].rel == "app.py"
    assert info.hotspots[0].commits == 2


def test_hotspots_are_sorted_by_churn_score(repo_with_history: Path) -> None:
    write(repo_with_history, "small.py", "y = 1\n")
    git(repo_with_history, "add", "-A")
    git(repo_with_history, "commit", "-q", "-m", "add small")
    info = collect_git(repo_with_history, {"app.py": 1, "small.py": 500})
    scores = [c.score for c in info.hotspots]
    assert scores == sorted(scores, reverse=True)
    assert info.hotspots[0].rel == "small.py"


def test_dates_and_span_are_parsed(repo_with_history: Path) -> None:
    info = collect_git(repo_with_history, {})
    assert info.first_commit_date is not None
    assert info.last_commit_date is not None
    assert info.days_span >= 0


def test_uncommitted_changes_are_counted(repo_with_history: Path) -> None:
    write(repo_with_history, "dirty.py", "z = 1\n")
    info = collect_git(repo_with_history, {})
    assert info.uncommitted_changes >= 1


def test_git_info_serialisation() -> None:
    info = GitInfo(available=True, commits=3, branch="main")
    payload = info.as_dict()
    assert payload["commits"] == 3
    assert payload["available"] is True


def test_history_score_bands() -> None:
    assert history_score(GitInfo(available=False)) == 40.0
    healthy = GitInfo(available=True, commits=120, days_span=400,
                      authors=[("a", 60), ("b", 40)])
    assert history_score(healthy) > 60
    solo = GitInfo(available=True, commits=50, days_span=100, authors=[("a", 50)])
    assert history_score(solo) < history_score(healthy)


def test_top_author_share() -> None:
    info = GitInfo(available=True, commits=10, authors=[("a", 9), ("b", 1)])
    assert info.top_author_share == 90.0
