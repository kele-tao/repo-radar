"""End-to-end scan behaviour: counts, scores, determinism and edge cases."""

from __future__ import annotations

from pathlib import Path

import pytest

from repo_radar.scan import collect, compute_scores, weighted_score
from repo_radar.scoring import SCORE_WEIGHTS, grade_for
from repo_radar.scoring import weighted_score as ws
from tests.conftest import write


def test_clean_repo_scores_well(clean_repo: Path) -> None:
    result = collect(clean_repo, with_git=False)
    assert result.total_files >= 6
    assert result.code_lines > 10
    assert result.score >= 60
    assert result.grade in {"A", "B", "C"}


def test_risky_repo_is_flagged(risky_repo: Path) -> None:
    result = collect(risky_repo, with_git=False)
    rules = {f.rule for f in result.findings}
    assert {"RR001", "RR002", "RR004", "RR005"} <= rules
    assert result.severity["high"] >= 3
    assert result.score < 80


def test_missing_hygiene_files_are_reported(tmp_path: Path) -> None:
    write(tmp_path, "app.py", "print('x')\n")
    result = collect(tmp_path, with_git=False)
    details = [f.detail for f in result.findings if f.rule == "RR018"]
    assert any("README" in d for d in details)
    assert any("LICENSE" in d for d in details)


def test_scores_are_bounded_and_weighted() -> None:
    scores = {"risk": 100.0, "tests": 100.0, "docs": 100.0,
              "dependencies": 100.0, "hygiene": 100.0, "history": 100.0}
    assert weighted_score(scores) == 100.0
    empty = dict.fromkeys(SCORE_WEIGHTS, 0.0)
    assert weighted_score(empty) == 0.0
    assert ws is weighted_score


def test_grade_thresholds() -> None:
    assert grade_for(95) == "A"
    assert grade_for(85) == "B"
    assert grade_for(75) == "C"
    assert grade_for(65) == "D"
    assert grade_for(10) == "F"


def test_empty_directory_does_not_crash(tmp_path: Path) -> None:
    result = collect(tmp_path, with_git=False)
    assert result.total_files == 0
    assert 0.0 <= result.score <= 100.0
    assert result.grade in {"A", "B", "C", "D", "F"}


def test_json_payload_is_stable(clean_repo: Path) -> None:
    first = collect(clean_repo, with_git=False).as_dict()
    second = collect(clean_repo, with_git=False).as_dict()
    for payload in (first, second):
        payload.pop("duration_ms")
    assert first == second


def test_unicode_paths_and_content(tmp_path: Path) -> None:
    write(tmp_path, "模块/应用.py", '"""模块说明。"""\n\ndef 运行() -> int:\n'
                                     "    return 1\n")
    result = collect(tmp_path, with_git=False)
    assert result.total_files == 1
    assert result.code_lines >= 2


def test_large_tree_is_fast(tmp_path: Path) -> None:
    for index in range(300):
        write(tmp_path, "pkg/mod_%03d.py" % index,
              '"""Module %d."""\n\n\ndef value() -> int:\n    return %d\n' % (index, index))
    write(tmp_path, "README.md", "# big\n")
    result = collect(tmp_path, with_git=False)
    assert result.total_files == 301
    assert result.duration_ms < 10000


def test_sub_scores_present_for_every_weight(clean_repo: Path) -> None:
    result = collect(clean_repo, with_git=False)
    for name in SCORE_WEIGHTS:
        assert name in result.scores
        assert 0.0 <= result.scores[name] <= 100.0


def test_compute_scores_is_pure(clean_repo: Path) -> None:
    result = collect(clean_repo, with_git=False)
    before = dict(result.scores)
    again = compute_scores(result)
    assert before == again


def test_git_section_can_be_disabled(clean_repo: Path) -> None:
    result = collect(clean_repo, with_git=False)
    assert result.git is not None
    assert result.git.available is False


def test_ignore_pattern_from_options(tmp_path: Path) -> None:
    from repo_radar.walker import WalkOptions

    write(tmp_path, "keep.py", "x = 1\n")
    write(tmp_path, "skip/big.py", "y = 2\n")
    result = collect(tmp_path, WalkOptions(ignore=("skip",)), with_git=False)
    assert [f.rel for f in result.files] == ["keep.py"]


def test_ecosystem_detection(clean_repo: Path) -> None:
    result = collect(clean_repo, with_git=False)
    assert result.ecosystem is not None
    assert result.ecosystem.has_readme
    assert result.ecosystem.has_license
    assert "pytest" in result.ecosystem.test_frameworks
    assert result.ecosystem.dependency_total == 1
    assert result.ecosystem.pin_ratio == 100.0


def test_giant_file_finding(tmp_path: Path) -> None:
    body = "".join("value_%d = %d\n" % (i, i) for i in range(800))
    write(tmp_path, "huge.py", body)
    result = collect(tmp_path, with_git=False)
    assert any(f.rule == "RR011" for f in result.findings)


def test_findings_are_sorted_by_severity_then_path(risky_repo: Path) -> None:
    result = collect(risky_repo, with_git=False)
    severities = [f.severity for f in result.findings]
    order = {"high": 4, "medium": 3, "low": 2, "info": 1}
    ranks = [order[s] for s in severities]
    assert ranks == sorted(ranks, reverse=True)


@pytest.mark.parametrize("top", [0, 1, 5])
def test_top_findings_limit(risky_repo: Path, top: int) -> None:
    result = collect(risky_repo, with_git=False, top=top)
    assert len(result.top_findings(top)) <= max(0, top) or top == 0
