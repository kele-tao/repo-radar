"""Precision rules: which files and lines the line-level rules are allowed to touch."""

from __future__ import annotations

from pathlib import Path

from repo_radar import findings
from repo_radar.findings import scan_files, scan_text
from repo_radar.walker import count_lines, iter_files, load_text


def _scan(tmp_path: Path):
    infos = iter_files(tmp_path)
    texts = {}
    languages = {}
    for info in infos:
        text = load_text(info)
        count_lines(text, info)
        texts[info.rel] = text
        languages[info.rel] = info.language
    return infos, texts, languages


def test_documentation_is_not_treated_as_code(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("Never ship verify=False.\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("eval(payload)\n", encoding="utf-8")
    infos, texts, languages = _scan(tmp_path)
    found = scan_files(infos, texts, languages, [])
    assert [f.rule for f in found] == []


def test_code_still_triggers_the_same_rule(tmp_path: Path) -> None:
    (tmp_path / "client.py").write_text("requests.get(url, verify=False)\n", encoding="utf-8")
    infos, texts, languages = _scan(tmp_path)
    found = scan_files(infos, texts, languages, [])
    assert any(f.rule == "RR005" for f in found)


def test_test_modules_are_exempt_from_line_rules(tmp_path: Path) -> None:
    fixture = 'PAYLOAD = "eval(input())"\nPASSWORD = "sup3rsecretvalue"\n'
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_rules.py").write_text(fixture, encoding="utf-8")
    (tmp_path / "lib.py").write_text(fixture, encoding="utf-8")
    infos, texts, languages = _scan(tmp_path)
    found = scan_files(infos, texts, languages, [])
    assert {f.path for f in found} == {"lib.py"}


def test_suppression_token_exempts_one_line() -> None:
    pattern = findings.SUPPRESS_TOKEN
    text = (
        'PATTERN = "verify=False"  # ' + pattern + '\n'
        'CALL = requests.get(url, verify=False)\n'
    )
    found = scan_text("client.py", text, "Python")
    lines = [f.line for f in found if f.rule == "RR005"]
    assert lines == [2]


def test_suppression_token_is_documented() -> None:
    doc = (Path(__file__).resolve().parents[1] / "docs" / "rules.md").read_text(encoding="utf-8")
    assert findings.SUPPRESS_TOKEN in doc


def test_rule_categories_exclude_prose_and_styles() -> None:
    assert "code" in findings.RULE_CATEGORIES
    assert "docs" not in findings.RULE_CATEGORIES
    assert "style" not in findings.RULE_CATEGORIES
    assert "markup" not in findings.RULE_CATEGORIES


def test_own_source_scans_clean() -> None:
    """The scanner must not report its own detection patterns as findings."""
    root = Path(__file__).resolve().parents[1] / "src"
    infos = iter_files(root)
    texts = {}
    languages = {}
    for info in infos:
        text = load_text(info)
        count_lines(text, info)
        texts[info.rel] = text
        languages[info.rel] = info.language
    found = scan_files(infos, texts, languages, [])
    assert found == []
