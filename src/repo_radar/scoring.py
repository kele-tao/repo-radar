"""Scoring: six weighted sub-scores and the 0-100 health score.

The formulas are deliberately simple and documented so that a reader can
reproduce a score by hand from the JSON output. Every sub-score is 0-100.
"""

from __future__ import annotations

SCORE_WEIGHTS = {
    "risk": 30.0,
    "tests": 20.0,
    "docs": 15.0,
    "dependencies": 15.0,
    "hygiene": 10.0,
    "history": 10.0,
}

GRADES = ((90, "A"), (80, "B"), (70, "C"), (60, "D"), (0, "F"))

SUBSCORE_HINTS = {
    "risk": "inverse of severity-weighted findings, damped by code size",
    "tests": "test tree, framework detection, test/code ratio",
    "docs": "README size, docs/ presence, comment ratio, licence",
    "dependencies": "pin ratio, lockfile, manifest presence, count",
    "hygiene": "readme/licence/CI/hooks/docker + entry-point clarity",
    "history": "commit volume, authorship spread, uncommitted churn",
}


def grade_for(score: float) -> str:
    """Letter grade for a 0-100 score."""
    for threshold, letter in GRADES:
        if score >= threshold:
            return letter
    return "F"


def weighted_score(scores: dict[str, float]) -> float:
    """Weighted mean of the six sub-scores, rounded to one decimal."""
    total = sum(SCORE_WEIGHTS.values())
    acc = sum(scores.get(name, 0.0) * weight for name, weight in SCORE_WEIGHTS.items())
    return round(acc / total, 1)
